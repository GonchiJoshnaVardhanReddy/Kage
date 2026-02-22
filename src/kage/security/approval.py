"""Command approval workflow for Kage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from kage.core.models import Command, CommandStatus
from kage.security.audit import AuditLogger
from kage.security.safemode import DangerLevel, SafeModeFilter, SafeModeResult
from kage.security.scope import ScopeValidationResult, ScopeValidator

if TYPE_CHECKING:
    from kage.core.models import Scope


class ApprovalDecision(str, Enum):
    """Decision for command approval."""

    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass
class ApprovalResult:
    """Result of the approval workflow."""

    decision: ApprovalDecision
    command: Command
    safe_mode_result: SafeModeResult | None = None
    scope_results: list[ScopeValidationResult] | None = None
    reason: str | None = None
    warnings: list[str] | None = None


class ApprovalWorkflow:
    """Manages the command approval workflow."""

    def __init__(
        self,
        scope: Scope,
        safe_mode_enabled: bool = True,
        require_approval: bool = True,
        scope_enforcement: bool = True,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.scope_validator = ScopeValidator(scope)
        self.safe_mode_filter = SafeModeFilter(enabled=safe_mode_enabled)
        self.require_approval = require_approval
        self.scope_enforcement = scope_enforcement
        self.audit_logger = audit_logger

    async def evaluate(self, command: Command) -> ApprovalResult:
        """Evaluate a command through the approval workflow.
        
        Returns ApprovalResult with decision and any warnings/blocks.
        """
        warnings = []

        # Step 1: Safe mode check
        safe_result = self.safe_mode_filter.check(command.command)

        if safe_result.danger_level == DangerLevel.BLOCKED:
            if self.audit_logger:
                await self.audit_logger.log_safe_mode_block(
                    command.command,
                    safe_result.reason or "Blocked by safe mode",
                    overridden=False,
                )

            return ApprovalResult(
                decision=ApprovalDecision.BLOCKED,
                command=command,
                safe_mode_result=safe_result,
                reason=safe_result.reason,
            )

        if safe_result.danger_level == DangerLevel.DANGEROUS:
            warnings.append(f"⚠ DANGEROUS: {safe_result.reason}")
            if safe_result.suggestion:
                warnings.append(f"  Suggestion: {safe_result.suggestion}")

        if safe_result.danger_level == DangerLevel.CAUTION:
            warnings.append(f"⚡ CAUTION: {safe_result.reason}")
            if safe_result.suggestion:
                warnings.append(f"  Suggestion: {safe_result.suggestion}")

        # Step 2: Scope check
        scope_results = []
        if self.scope_enforcement and self.scope_validator.scope.targets:
            in_scope, scope_results = self.scope_validator.validate_command(command.command)

            for result in scope_results:
                if not result.in_scope:
                    warnings.append(
                        f"🎯 OUT OF SCOPE: {result.target_checked} - {result.reason}"
                    )

                    if self.audit_logger:
                        await self.audit_logger.log_scope_violation(
                            command.command,
                            result.target_checked,
                            "warning_shown",
                        )

        # Step 3: Determine decision
        if warnings and self.require_approval:
            return ApprovalResult(
                decision=ApprovalDecision.NEEDS_CONFIRMATION,
                command=command,
                safe_mode_result=safe_result,
                scope_results=scope_results,
                warnings=warnings,
            )

        if self.require_approval:
            return ApprovalResult(
                decision=ApprovalDecision.NEEDS_CONFIRMATION,
                command=command,
                safe_mode_result=safe_result,
                scope_results=scope_results,
            )

        # Auto-approve if no approval required and no issues
        return ApprovalResult(
            decision=ApprovalDecision.APPROVED,
            command=command,
            safe_mode_result=safe_result,
            scope_results=scope_results,
        )

    async def approve(self, command: Command, by: str = "user") -> None:
        """Mark a command as approved."""
        command.status = CommandStatus.APPROVED
        command.approved_by = by

        if self.audit_logger:
            await self.audit_logger.log_command_approved(command.command, by)

    async def reject(self, command: Command, reason: str | None = None) -> None:
        """Mark a command as rejected."""
        command.status = CommandStatus.REJECTED

        if self.audit_logger:
            await self.audit_logger.log_command_rejected(command.command, reason)

    def update_safe_mode(self, enabled: bool) -> None:
        """Update safe mode setting."""
        self.safe_mode_filter.enabled = enabled

    def update_scope(self, scope: Scope) -> None:
        """Update the scope validator."""
        self.scope_validator = ScopeValidator(scope)
