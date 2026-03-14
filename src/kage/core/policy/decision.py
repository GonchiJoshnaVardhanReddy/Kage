"""Policy decision models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PolicyAction(str, Enum):
    """Supported policy outcomes."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PolicySeverity(str, Enum):
    """Severity for policy decisions."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PolicyDecision(BaseModel):
    """Normalized result from policy evaluation."""

    decision: PolicyAction
    reason: str
    rule_id: str
    severity: PolicySeverity = PolicySeverity.INFO
    requires_confirmation: bool = False
    sandbox_required: bool = False

    @classmethod
    def allow(cls, *, reason: str, rule_id: str = "policy.default_allow") -> PolicyDecision:
        return cls(
            decision=PolicyAction.ALLOW,
            reason=reason,
            rule_id=rule_id,
            severity=PolicySeverity.INFO,
            requires_confirmation=False,
            sandbox_required=False,
        )

    @classmethod
    def ask(
        cls,
        *,
        reason: str,
        rule_id: str,
        severity: PolicySeverity = PolicySeverity.WARNING,
        sandbox_required: bool = True,
    ) -> PolicyDecision:
        return cls(
            decision=PolicyAction.ASK,
            reason=reason,
            rule_id=rule_id,
            severity=severity,
            requires_confirmation=True,
            sandbox_required=sandbox_required,
        )

    @classmethod
    def deny(
        cls,
        *,
        reason: str,
        rule_id: str,
        severity: PolicySeverity = PolicySeverity.ERROR,
        sandbox_required: bool = True,
    ) -> PolicyDecision:
        return cls(
            decision=PolicyAction.DENY,
            reason=reason,
            rule_id=rule_id,
            severity=severity,
            requires_confirmation=False,
            sandbox_required=sandbox_required,
        )

