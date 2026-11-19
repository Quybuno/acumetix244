"""
User Authorization and Role-Based Access Control (RBAC) for Deep Review (Phase 3 - Task T3.12)

Implements:
1. User identity and permissions representation (UserContext).
2. Engine-specific permissions:
   - DAST (Acunetix): requires 'scan:create:acunetix' (restricted to ADMIN, SECURITY_LEAD, SECURITY_ENGINEER).
   - SAST (Fortify): requires 'scan:create:fortify'.
   - General view: requires 'scan:view'.
   - Cancellation: requires 'scan:cancel'.
3. Multi-tenant Project-Level Access Isolation:
   - Users can only create, view, or cancel scans within projects they belong to (unless ADMIN).
4. Strict enforcement: Returns HTTP 403 Forbidden with clear messages when unauthorized.
"""

from typing import Set, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from backend.models.scan import ScanJob

# Standard Deep Review Roles mapped to their permitted capabilities
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "ADMIN": {
        "*",
        "scan:create:acunetix",
        "scan:create:fortify",
        "scan:view",
        "scan:cancel"
    },
    "SECURITY_LEAD": {
        "scan:create:acunetix",
        "scan:create:fortify",
        "scan:view",
        "scan:cancel"
    },
    "SECURITY_ENGINEER": {
        "scan:create:acunetix",
        "scan:create:fortify",
        "scan:view",
        "scan:cancel"
    },
    "DEVELOPER": {
        "scan:create:fortify",
        "scan:view"
    },
    "AUDITOR": {
        "scan:view"
    },
    "VIEWER": {
        "scan:view"
    }
}

class AuthorizationError(Exception):
    """Raised when an operation is prohibited due to lack of permissions or project isolation."""
    def __init__(self, message: str, status_code: int = 403, error_code: str = "FORBIDDEN"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code

@dataclass
class UserContext:
    """Represents the authenticated caller and their security context."""
    user_id: str
    roles: List[str] = field(default_factory=list)
    projects: List[str] = field(default_factory=list)
    direct_permissions: Set[str] = field(default_factory=set)

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles or "*" in self.projects

    def has_project_access(self, project_id: str) -> bool:
        """Check if user is a member of the requested project or is a system admin."""
        if self.is_admin:
            return True
        if not project_id:
            return False
        return project_id in self.projects

    def has_permission(self, permission: str) -> bool:
        """Check if user has the specific permission via roles or direct grant."""
        if self.is_admin:
            return True
        if permission in self.direct_permissions:
            return True
        for role in self.roles:
            role_perms = ROLE_PERMISSIONS.get(role, set())
            if "*" in role_perms or permission in role_perms:
                return True
        return False

    @classmethod
    def from_headers(cls, headers: Optional[Dict[str, str]]) -> "UserContext":
        """
        Extract user context from standard Deep Review gateway headers:
        - X-User-Id: Username / Account ID
        - X-User-Roles: Comma-separated list of roles
        - X-User-Projects: Comma-separated list of authorized project IDs
        - X-User-Permissions: Comma-separated list of explicit permissions
        """
        if not headers:
            # Default to anonymous user with no permissions
            return cls(user_id="anonymous", roles=[], projects=[], direct_permissions=set())

        norm = {k.lower(): v for k, v in headers.items()}

        user_id = norm.get("x-user-id", "anonymous").strip()

        roles_raw = norm.get("x-user-roles", "")
        roles = [r.strip() for r in roles_raw.split(",") if r.strip()]

        projects_raw = norm.get("x-user-projects", "")
        projects = [p.strip() for p in projects_raw.split(",") if p.strip()]

        perms_raw = norm.get("x-user-permissions", "")
        perms = {p.strip() for p in perms_raw.split(",") if p.strip()}

        return cls(
            user_id=user_id,
            roles=roles,
            projects=projects,
            direct_permissions=perms
        )

class AuthorizationService:
    """
    Enforces authorization rules for scan operations.
    """

    def check_create_scan(
        self,
        user: UserContext,
        engine: str,
        project_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify if user is authorized to create a scan for a specific engine in a project.
        """
        # 1. Project-level membership check
        if not user.has_project_access(project_id):
            return False, f"User '{user.user_id}' does not have access to project '{project_id}'."

        # 2. Engine-specific capability check
        if engine == "acunetix":
            if not user.has_permission("scan:create:acunetix"):
                return False, (
                    f"Forbidden: User '{user.user_id}' (roles={user.roles}) lacks permission "
                    f"'scan:create:acunetix' required to launch Acunetix DAST scans. "
                    f"Acunetix scans require SECURITY_LEAD, SECURITY_ENGINEER, or ADMIN role."
                )
        elif engine == "fortify":
            if not user.has_permission("scan:create:fortify"):
                return False, (
                    f"Forbidden: User '{user.user_id}' lacks permission 'scan:create:fortify' "
                    f"to launch Fortify SAST scans."
                )
        else:
            return False, f"Forbidden: Unsupported scan engine '{engine}'."

        return True, None

    def check_view_scan(
        self,
        user: UserContext,
        scan: ScanJob
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify if user is authorized to view a scan and its detailed findings.
        """
        # 1. Permission check
        if not user.has_permission("scan:view"):
            return False, f"Forbidden: User '{user.user_id}' lacks 'scan:view' permission."

        # 2. Project boundary check
        if not user.has_project_access(scan.project_id):
            return False, (
                f"Forbidden: User '{user.user_id}' belongs to projects {user.projects} "
                f"and is not authorized to access scan '{scan.scan_id}' belonging to project '{scan.project_id}'."
            )

        return True, None

    def check_cancel_scan(
        self,
        user: UserContext,
        scan: ScanJob
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify if user is authorized to cancel an active scan.
        """
        # 1. Permission check
        if not user.has_permission("scan:cancel"):
            return False, (
                f"Forbidden: User '{user.user_id}' lacks 'scan:cancel' permission. "
                f"Only administrators, security engineers, or project leads can cancel scans."
            )

        # 2. Project boundary check
        if not user.has_project_access(scan.project_id):
            return False, (
                f"Forbidden: User '{user.user_id}' cannot cancel scan '{scan.scan_id}' "
                f"in unauthorized project '{scan.project_id}'."
            )

        return True, None

    def check_list_scans(
        self,
        user: UserContext,
        requested_project_id: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify if user is authorized to list scans for the requested project filter.
        """
        if not user.has_permission("scan:view"):
            return False, f"Forbidden: User '{user.user_id}' lacks 'scan:view' permission."

        if requested_project_id and not user.has_project_access(requested_project_id):
            return False, (
                f"Forbidden: User '{user.user_id}' cannot list scans for unauthorized project '{requested_project_id}'."
            )

        return True, None
