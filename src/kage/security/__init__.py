"""Security module for Kage."""

from kage.security.approval import ApprovalDecision, ApprovalResult, ApprovalWorkflow
from kage.security.audit import AuditLogger
from kage.security.safemode import (
    DangerLevel,
    SafeModeFilter,
    SafeModeResult,
    classify_command_category,
)
from kage.security.scope import ScopeValidationResult, ScopeValidator

__all__ = [
    "ApprovalDecision",
    "ApprovalResult",
    "ApprovalWorkflow",
    "AuditLogger",
    "DangerLevel",
    "SafeModeFilter",
    "SafeModeResult",
    "ScopeValidationResult",
    "ScopeValidator",
    "classify_command_category",
]
