"""
Deep Review Authorization Package (Phase 3 - Task T3.12)
Provides Role-Based Access Control (RBAC) and Project-Level isolation.
"""

from backend.auth.authorization import (
    UserContext,
    AuthorizationService,
    AuthorizationError,
    ROLE_PERMISSIONS
)

__all__ = [
    "UserContext",
    "AuthorizationService",
    "AuthorizationError",
    "ROLE_PERMISSIONS"
]
