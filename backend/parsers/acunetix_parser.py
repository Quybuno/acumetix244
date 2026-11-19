"""
Acunetix Report Parser for Deep Review Backend (Phase 3 - Task T3.7)

Transforms raw Acunetix scan results and JSON samples into a standardized UnifiedReport.
Supports:
1. Normalizing Acunetix severity levels (0-4 / strings) to unified 5-tier standard
   (CRITICAL, HIGH, MEDIUM, LOW, INFO).
2. Extracting affected locations (affects_url), attack parameters (affects_detail),
   CWE IDs, CVE IDs, CVSS scores (cvss_score, cvss3, cvss4).
3. Extracting description, remediation (recommendation), technical details,
   impact, and HTTP request/response proofs.
4. Aggregating scan metrics (locations crawled, requests sent, duration) and
   coverage warnings (e.g. LOW_COVERAGE, LOGIN_FAILED).
5. Robust error handling: Malformed or unparseable payloads raise ParseException
   (error_code='PARSE_FAILED') without crashing the backend process.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class ParseException(Exception):
    """Raised when scan report data fails schema validation or cannot be parsed."""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.error_code = "PARSE_FAILED"

    def __str__(self) -> str:
        if self.details:
            return f"PARSE_FAILED: {self.message} ({self.details})"
        return f"PARSE_FAILED: {self.message}"

@dataclass
class UnifiedFinding:
    """Standardized vulnerability finding format across all scanning engines."""
    id: str
    title: str
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'
    target_url: str
    attack_parameter: Optional[str] = None
    cwe_id: Optional[str] = None
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss3: Optional[str] = None
    cvss4: Optional[str] = None
    confidence: Optional[int] = None
    description: Optional[str] = None
    details: Optional[str] = None
    impact: Optional[str] = None
    remediation: Optional[str] = None
    http_request: Optional[str] = None
    http_response: Optional[str] = None
    references: List[Dict[str, str]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    raw_details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class UnifiedReport:
    """Standardized scan report format for Deep Review."""
    engine: str = "acunetix"
    scan_id: str = "unknown"
    target_url: Optional[str] = None
    status: str = "COMPLETED"
    summary: Dict[str, Any] = field(default_factory=lambda: {
        "total_findings": 0,
        "severity_breakdown": {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0
        }
    })
    findings: List[UnifiedFinding] = field(default_factory=list)
    scan_metrics: Dict[str, Any] = field(default_factory=lambda: {
        "locations_crawled": 0,
        "requests_sent": 0,
        "duration_seconds": 0.0
    })
    coverage_warnings: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=get_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["findings"] = [f.to_dict() if isinstance(f, UnifiedFinding) else f for f in self.findings]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedReport":
        findings_data = data.get("findings", [])
        findings = []
        for f in findings_data:
            if isinstance(f, dict):
                findings.append(UnifiedFinding(**f))
            else:
                findings.append(f)

        return cls(
            engine=data.get("engine", "acunetix"),
            scan_id=data.get("scan_id", "unknown"),
            target_url=data.get("target_url"),
            status=data.get("status", "COMPLETED"),
            summary=data.get("summary", {}),
            findings=findings,
            scan_metrics=data.get("scan_metrics", {}),
            coverage_warnings=data.get("coverage_warnings", []),
            created_at=data.get("created_at", get_utc_now_iso())
        )

class AcunetixReportParser:
    """
    Parser for Acunetix vulnerability JSON reports.
    Converts Acunetix raw API responses or webhook payloads into UnifiedReport.
    """

    SEVERITY_MAPPING = {
        4: "CRITICAL",
        "4": "CRITICAL",
        "critical": "CRITICAL",
        3: "HIGH",
        "3": "HIGH",
        "high": "HIGH",
        2: "MEDIUM",
        "2": "MEDIUM",
        "medium": "MEDIUM",
        1: "LOW",
        "1": "LOW",
        "low": "LOW",
        0: "INFO",
        "0": "INFO",
        "info": "INFO",
        "informational": "INFO"
    }

    CWE_REGEX = re.compile(r"\bCWE-(\d+)\b", re.IGNORECASE)
    CVE_REGEX = re.compile(r"\bCVE-(\d{4}-\d+)\b", re.IGNORECASE)

    def parse(
        self,
        raw_data: Union[str, bytes, Dict[str, Any], List[Any]],
        scan_id: Optional[str] = None
    ) -> UnifiedReport:
        """
        Parse raw Acunetix data into a UnifiedReport.
        Accepts:
            - JSON string or bytes
            - Dict (webhook payload, API response with 'vulnerabilities', or single vuln detail)
            - List of vulnerability dicts
        Raises:
            ParseException (with error_code='PARSE_FAILED') if input is malformed or invalid.
        """
        if raw_data is None:
            raise ParseException("Payload cannot be None")

        # 1. Deserialize if raw bytes or string
        payload = self._deserialize(raw_data)

        # 2. Extract top-level metadata and vulnerability list
        target_url = None
        status = "COMPLETED"
        report_scan_id = scan_id or "unknown"
        metrics = {
            "locations_crawled": 0,
            "requests_sent": 0,
            "duration_seconds": 0.0
        }
        coverage_warnings: List[str] = []
        raw_vulns: List[Dict[str, Any]] = []

        if isinstance(payload, list):
            # Payload is a list of vulnerabilities directly
            raw_vulns = payload
        elif isinstance(payload, dict):
            # Check if this is a single vulnerability detail object (T0.7 critical detail)
            if ("vt_name" in payload or "vuln_id" in payload) and "vulnerabilities" not in payload:
                raw_vulns = [payload]
                target_url = payload.get("affects_url")
            else:
                # Top-level container
                report_scan_id = payload.get("scan_id") or scan_id or "unknown"
                target_url = payload.get("target_url")
                status = payload.get("status", "COMPLETED")

                # Extract coverage warnings
                if "coverage_warnings" in payload and isinstance(payload["coverage_warnings"], list):
                    coverage_warnings.extend(payload["coverage_warnings"])

                health_details = payload.get("health_details") or {}
                if health_details.get("reasons"):
                    reasons = health_details.get("reasons")
                    if isinstance(reasons, list):
                        for r in reasons:
                            if r not in coverage_warnings:
                                coverage_warnings.append(r)
                    elif isinstance(reasons, str) and reasons not in coverage_warnings:
                        coverage_warnings.append(reasons)

                # Extract statistics / metrics
                stats = payload.get("statistics") or {}
                if isinstance(stats, dict):
                    metrics["locations_crawled"] = (
                        stats.get("locations_crawled")
                        or stats.get("scanned_urls")
                        or stats.get("crawled_urls")
                        or health_details.get("locations")
                        or 0
                    )
                    metrics["requests_sent"] = stats.get("requests") or stats.get("request_count") or 0
                    metrics["duration_seconds"] = float(stats.get("duration") or 0.0)

                timings = payload.get("timings") or {}
                if isinstance(timings, dict) and "total_duration_seconds" in timings:
                    metrics["duration_seconds"] = float(timings["total_duration_seconds"])

                # Extract vulnerabilities list
                vuln_container = payload.get("vulnerabilities")
                if vuln_container is not None:
                    if not isinstance(vuln_container, list):
                        raise ParseException(
                            "Field 'vulnerabilities' must be a list",
                            details=f"Got {type(vuln_container).__name__}"
                        )
                    raw_vulns = vuln_container
                else:
                    # Payload might be empty or missing vulnerabilities key
                    raw_vulns = []
        else:
            raise ParseException(
                f"Unexpected payload type: {type(payload).__name__}",
                details="Expected JSON object, array, or string"
            )

        # 3. Parse and standardize each vulnerability finding
        findings: List[UnifiedFinding] = []
        severity_counts = {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0
        }

        loc_ids = set()

        for idx, item in enumerate(raw_vulns):
            if not isinstance(item, dict):
                raise ParseException(
                    f"Invalid vulnerability record at index {idx}",
                    details=f"Expected dict, got {type(item).__name__}"
                )
            try:
                finding = self._parse_finding(item, default_target_url=target_url)
                findings.append(finding)
                severity_counts[finding.severity] += 1
                if item.get("loc_id"):
                    loc_ids.add(item["loc_id"])
            except Exception as e:
                raise ParseException(
                    f"Failed to parse vulnerability at index {idx}: {str(e)}",
                    details=f"Item keys: {list(item.keys()) if isinstance(item, dict) else 'non-dict'}"
                )

        # Fallback for locations_crawled if not provided in statistics
        if metrics["locations_crawled"] == 0 and loc_ids:
            metrics["locations_crawled"] = len(loc_ids)

        # 4. Construct UnifiedReport
        summary = {
            "total_findings": len(findings),
            "severity_breakdown": severity_counts
        }

        return UnifiedReport(
            engine="acunetix",
            scan_id=report_scan_id,
            target_url=target_url,
            status=status,
            summary=summary,
            findings=findings,
            scan_metrics=metrics,
            coverage_warnings=coverage_warnings,
            created_at=get_utc_now_iso()
        )

    def _deserialize(self, raw_data: Union[str, bytes, Any]) -> Any:
        """Safely deserialize raw string or bytes to Python structure."""
        if isinstance(raw_data, bytes):
            try:
                text = raw_data.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ParseException("Payload decoding failed: not valid UTF-8", details=str(e))
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise ParseException("Malformed JSON payload", details=str(e))
        elif isinstance(raw_data, str):
            clean_str = raw_data.strip()
            if not clean_str:
                raise ParseException("Payload string is empty")
            try:
                return json.loads(clean_str)
            except json.JSONDecodeError as e:
                raise ParseException("Malformed JSON payload", details=str(e))
        return raw_data

    def _normalize_severity(self, raw_val: Any) -> str:
        """Map Acunetix severity (0-4 or string) to standardized 5-tier severity."""
        if raw_val is None:
            raise ValueError("Vulnerability missing severity level")

        # Convert to string lowercase for lookup
        lookup_key = raw_val
        if isinstance(raw_val, str):
            lookup_key = raw_val.strip().lower()

        normalized = self.SEVERITY_MAPPING.get(lookup_key)
        if normalized:
            return normalized

        # Try int conversion
        try:
            int_val = int(raw_val)
            normalized = self.SEVERITY_MAPPING.get(int_val)
            if normalized:
                return normalized
        except (ValueError, TypeError):
            pass

        raise ValueError(f"Unknown or unsupported severity level: '{raw_val}'")

    def _extract_cwe(self, tags: List[str], explicit_cwe: Optional[str] = None) -> Optional[str]:
        """Extract standardized CWE identifier (e.g. 'CWE-89')."""
        if explicit_cwe:
            match = self.CWE_REGEX.search(str(explicit_cwe))
            if match:
                return f"CWE-{match.group(1)}"
            return explicit_cwe

        for tag in tags:
            match = self.CWE_REGEX.search(str(tag))
            if match:
                return f"CWE-{match.group(1)}"
        return None

    def _extract_cve(self, tags: List[str], explicit_cve: Optional[str] = None) -> Optional[str]:
        """Extract standardized CVE identifier (e.g. 'CVE-2023-1234')."""
        if explicit_cve:
            match = self.CVE_REGEX.search(str(explicit_cve))
            if match:
                return f"CVE-{match.group(1).upper()}"
            return explicit_cve

        for tag in tags:
            match = self.CVE_REGEX.search(str(tag))
            if match:
                return f"CVE-{match.group(1).upper()}"
        return None

    def _extract_cvss_score(self, item: Dict[str, Any]) -> Optional[float]:
        """Extract highest available CVSS numerical score."""
        for key in ["cvss_score", "cvss4_score", "cvss3_score", "cvss2_score"]:
            val = item.get(key)
            if val is not None:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
        return None

    def _parse_finding(
        self,
        item: Dict[str, Any],
        default_target_url: Optional[str] = None
    ) -> UnifiedFinding:
        """Parse single vulnerability item into UnifiedFinding."""
        # 1. Identifier
        finding_id = (
            str(item.get("vuln_id") or "")
            or str(item.get("target_vuln_id") or "")
            or str(item.get("vt_id") or "")
        )
        if not finding_id:
            # Fallback identifier
            finding_id = f"acx-{hash(str(item.get('vt_name', '')) + str(item.get('affects_url', '')))}"

        # 2. Title
        title = item.get("vt_name") or item.get("name") or item.get("title")
        if not title:
            raise ValueError("Vulnerability missing required title/name field ('vt_name' or 'name')")

        # 3. Severity
        raw_sev = item.get("severity")
        severity = self._normalize_severity(raw_sev)

        # 4. Location and parameter
        affects_url = item.get("affects_url") or item.get("target_url") or default_target_url or ""
        affects_detail = item.get("affects_detail")
        if affects_detail is not None:
            affects_detail = str(affects_detail)

        # 5. Tags, CWE, CVE
        tags_raw = item.get("tags") or []
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        cwe_id = self._extract_cwe(tags, item.get("cwe_id") or item.get("cwe"))
        cve_id = self._extract_cve(tags, item.get("cve_id") or item.get("cve"))

        # 6. CVSS
        cvss_score = self._extract_cvss_score(item)
        cvss3 = item.get("cvss3")
        cvss4 = item.get("cvss4")

        # 7. Confidence & Source
        confidence = item.get("confidence")
        if confidence is not None:
            try:
                confidence = int(confidence)
            except (ValueError, TypeError):
                confidence = None

        source = item.get("source")

        # 8. Descriptions and proofs
        description = item.get("description")
        details = item.get("details")
        impact = item.get("impact")
        remediation = item.get("recommendation") or item.get("remediation")

        # 9. Request / Response
        http_request = item.get("request")
        http_response = None
        if "response" in item and item["response"] is not None:
            http_response = str(item["response"])
        elif item.get("response_info"):
            http_response = f"Response available in Acunetix (loc_id={item.get('loc_id')})"

        # 10. References
        references_raw = item.get("references") or []
        references = []
        if isinstance(references_raw, list):
            for ref in references_raw:
                if isinstance(ref, dict):
                    references.append({
                        "href": str(ref.get("href", "")),
                        "rel": str(ref.get("rel", ""))
                    })
                elif isinstance(ref, str):
                    references.append({
                        "href": ref,
                        "rel": ref
                    })

        return UnifiedFinding(
            id=finding_id,
            title=title,
            severity=severity,
            target_url=affects_url,
            attack_parameter=affects_detail,
            cwe_id=cwe_id,
            cve_id=cve_id,
            cvss_score=cvss_score,
            cvss3=cvss3,
            cvss4=cvss4,
            confidence=confidence,
            description=description,
            details=details,
            impact=impact,
            remediation=remediation,
            http_request=http_request,
            http_response=http_response,
            references=references,
            tags=tags,
            source=source,
            raw_details=item
        )
