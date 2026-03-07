"""Unit tests for findings management."""

from kage.core.models import Finding, Session, Severity
from kage.reporting.findings import FindingsManager, FindingStats


def _make_finding(
    title: str, severity: Severity = Severity.HIGH, target: str | None = None
) -> Finding:
    """Helper to create a finding quickly."""
    return Finding(title=title, severity=severity, description="desc", target=target)


class TestFindingsManagerDeduplicate:
    """FindingsManager.deduplicate removes duplicate findings."""

    def test_removes_exact_dupes(self):
        """Findings with same title+target+severity are de-duplicated."""
        session = Session()
        session.findings = [
            _make_finding("SQLi", Severity.CRITICAL, "example.com"),
            _make_finding("SQLi", Severity.CRITICAL, "example.com"),
            _make_finding("SQLi", Severity.CRITICAL, "example.com"),
        ]
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 2
        assert len(session.findings) == 1

    def test_preserves_unique_findings(self):
        """Unique findings are never removed."""
        session = Session()
        session.findings = [
            _make_finding("SQLi", Severity.CRITICAL, "a.com"),
            _make_finding("XSS", Severity.HIGH, "a.com"),
            _make_finding("SQLi", Severity.CRITICAL, "b.com"),
        ]
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 0
        assert len(session.findings) == 3

    def test_case_insensitive_title(self):
        """Deduplication is case-insensitive on title."""
        session = Session()
        session.findings = [
            _make_finding("SQL Injection", Severity.HIGH, "x.com"),
            _make_finding("sql injection", Severity.HIGH, "x.com"),
        ]
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 1
        assert len(session.findings) == 1

    def test_different_severity_not_deduped(self):
        """Same title+target but different severity are distinct."""
        session = Session()
        session.findings = [
            _make_finding("Info Disclosure", Severity.LOW, "x.com"),
            _make_finding("Info Disclosure", Severity.HIGH, "x.com"),
        ]
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 0
        assert len(session.findings) == 2

    def test_different_target_not_deduped(self):
        """Same title+severity but different target are distinct."""
        session = Session()
        session.findings = [
            _make_finding("XSS", Severity.MEDIUM, "a.com"),
            _make_finding("XSS", Severity.MEDIUM, "b.com"),
        ]
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 0
        assert len(session.findings) == 2

    def test_empty_findings(self):
        """No findings means nothing to deduplicate."""
        session = Session()
        mgr = FindingsManager(session)
        removed = mgr.deduplicate()
        assert removed == 0

    def test_updates_session_findings(self):
        """After dedup, session.findings is the same list object."""
        session = Session()
        session.findings = [
            _make_finding("A", Severity.LOW),
            _make_finding("A", Severity.LOW),
        ]
        mgr = FindingsManager(session)
        mgr.deduplicate()
        assert len(session.findings) == 1


class TestFindingStats:
    """FindingStats computes correct statistics."""

    def test_counts_by_severity(self):
        """Stats correctly count each severity level."""
        findings = [
            _make_finding("a", Severity.CRITICAL),
            _make_finding("b", Severity.HIGH),
            _make_finding("c", Severity.HIGH),
            _make_finding("d", Severity.MEDIUM),
            _make_finding("e", Severity.LOW),
            _make_finding("f", Severity.INFO),
        ]
        stats = FindingStats(findings)
        assert stats.total == 6
        assert stats.critical == 1
        assert stats.high == 2
        assert stats.medium == 1
        assert stats.low == 1
        assert stats.info == 1

    def test_risk_rating_critical(self):
        """Risk rating is CRITICAL when criticals exist."""
        stats = FindingStats([_make_finding("x", Severity.CRITICAL)])
        assert stats.risk_rating == "CRITICAL"

    def test_risk_rating_informational(self):
        """Risk rating is INFORMATIONAL for info-only findings."""
        stats = FindingStats([_make_finding("x", Severity.INFO)])
        assert stats.risk_rating == "INFORMATIONAL"

    def test_empty_stats(self):
        """Empty findings produce zero counts."""
        stats = FindingStats([])
        assert stats.total == 0
        assert stats.risk_score == 0
        assert stats.risk_rating == "INFORMATIONAL"
