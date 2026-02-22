"""Finding management and analysis for Kage reports."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from kage.core.models import Finding, Session, Severity


class FindingStats:
    """Statistics about findings in a session."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        self._compute_stats()

    def _compute_stats(self) -> None:
        """Compute statistics from findings."""
        self.total = len(self.findings)

        # Count by severity
        severity_counts = Counter(f.severity for f in self.findings)
        self.critical = severity_counts.get(Severity.CRITICAL, 0)
        self.high = severity_counts.get(Severity.HIGH, 0)
        self.medium = severity_counts.get(Severity.MEDIUM, 0)
        self.low = severity_counts.get(Severity.LOW, 0)
        self.info = severity_counts.get(Severity.INFO, 0)

        # Verified vs unverified
        self.verified = sum(1 for f in self.findings if f.verified)
        self.unverified = self.total - self.verified

        # Auto-detected vs manual
        self.auto_detected = sum(1 for f in self.findings if f.auto_detected)
        self.manual = self.total - self.auto_detected

        # Calculate overall risk score (weighted)
        weights = {
            Severity.CRITICAL: 10,
            Severity.HIGH: 7,
            Severity.MEDIUM: 4,
            Severity.LOW: 1,
            Severity.INFO: 0,
        }
        self.risk_score = sum(weights.get(f.severity, 0) for f in self.findings)

        # Risk rating
        if self.critical > 0:
            self.risk_rating = "CRITICAL"
        elif self.high > 0:
            self.risk_rating = "HIGH"
        elif self.medium > 0:
            self.risk_rating = "MEDIUM"
        elif self.low > 0:
            self.risk_rating = "LOW"
        else:
            self.risk_rating = "INFORMATIONAL"

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total": self.total,
            "by_severity": {
                "critical": self.critical,
                "high": self.high,
                "medium": self.medium,
                "low": self.low,
                "info": self.info,
            },
            "verified": self.verified,
            "unverified": self.unverified,
            "auto_detected": self.auto_detected,
            "manual": self.manual,
            "risk_score": self.risk_score,
            "risk_rating": self.risk_rating,
        }


def sort_findings_by_severity(findings: list[Finding]) -> list[Finding]:
    """Sort findings by severity (critical first)."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    return sorted(findings, key=lambda f: severity_order.get(f.severity, 5))


def group_findings_by_severity(
    findings: list[Finding],
) -> dict[str, list[Finding]]:
    """Group findings by severity level."""
    grouped: dict[str, list[Finding]] = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": [],
        "info": [],
    }

    for finding in findings:
        grouped[finding.severity.value].append(finding)

    return grouped


def group_findings_by_target(
    findings: list[Finding],
) -> dict[str, list[Finding]]:
    """Group findings by target."""
    grouped: dict[str, list[Finding]] = {}

    for finding in findings:
        target = finding.target or "Unknown"
        if target not in grouped:
            grouped[target] = []
        grouped[target].append(finding)

    return grouped


class ReportData:
    """Data structure for report generation."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.stats = FindingStats(session.findings)
        self.findings_by_severity = group_findings_by_severity(session.findings)
        self.findings_sorted = sort_findings_by_severity(session.findings)
        self.generated_at = datetime.utcnow()

    def to_context(self) -> dict[str, Any]:
        """Convert to Jinja2 template context."""
        return {
            # Session info
            "session_id": self.session.id,
            "session_name": self.session.name or f"Session {self.session.id[:8]}",
            "created_at": self.session.created_at,
            "updated_at": self.session.updated_at,
            "generated_at": self.generated_at,

            # Scope
            "scope": self.session.scope,
            "targets": self.session.scope.targets,
            "excluded": self.session.scope.excluded,

            # Findings
            "findings": self.findings_sorted,
            "findings_by_severity": self.findings_by_severity,
            "stats": self.stats.to_dict(),

            # Commands
            "commands": self.session.commands,
            "command_count": len(self.session.commands),

            # Metadata
            "safe_mode": self.session.safe_mode,
            "environment": self.session.environment.value,
        }
