"""Policy rule abstractions and default rule implementations."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path

from .context import PolicyContext
from .decision import PolicyAction, PolicyDecision, PolicySeverity


@dataclass(slots=True)
class PolicyRule:
    """Base policy rule with priority and grouping metadata."""

    rule_id: str
    description: str
    priority: int = 100
    group: str = "default"

    def applies(self, _context: PolicyContext) -> bool:
        """Return True when this rule should evaluate."""
        return True

    def evaluate(self, _context: PolicyContext) -> PolicyDecision:
        """Produce a decision for the given context."""
        return PolicyDecision.allow(reason="No restriction", rule_id=self.rule_id)


@dataclass(slots=True)
class WorkspaceWriteRestrictionRule(PolicyRule):
    """Restrict file writes to workspace root."""

    rule_id: str = "policy.workspace_write_restriction"
    description: str = "Deny writes outside workspace root"
    priority: int = 10
    group: str = "filesystem"

    def applies(self, context: PolicyContext) -> bool:
        return bool(context.filesystem_path and context.tool_name.startswith("builtin.fs.write"))

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        assert context.filesystem_path is not None
        if context.workspace_root is None:
            return PolicyDecision.ask(
                reason="Workspace root unavailable for write check",
                rule_id=self.rule_id,
                severity=PolicySeverity.WARNING,
            )
        candidate = Path(context.filesystem_path).expanduser()
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (context.workspace_root / candidate).resolve(strict=False)
        )
        try:
            resolved.relative_to(context.workspace_root.resolve(strict=False))
        except ValueError:
            return PolicyDecision.deny(
                reason=f"Write path outside workspace: {resolved}",
                rule_id=self.rule_id,
                severity=PolicySeverity.ERROR,
            )
        return PolicyDecision.allow(reason="Write path in workspace", rule_id=self.rule_id)


@dataclass(slots=True)
class PluginTrustLevelRule(PolicyRule):
    """Enforce trust policy for plugin-origin executions."""

    rule_id: str = "policy.plugin_trust_enforcement"
    description: str = "Require confirmation for untrusted plugin sources"
    priority: int = 30
    group: str = "plugin"

    def applies(self, context: PolicyContext) -> bool:
        return bool(context.plugin_source) or context.tool_name.startswith("plugin.")

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        trusted = context.session_metadata.get("trusted_plugins", [])
        if not isinstance(trusted, list):
            trusted = []
        source = context.plugin_source or context.tool_name.split(".")[1]
        if source in trusted:
            return PolicyDecision.allow(reason="Trusted plugin source", rule_id=self.rule_id)
        return PolicyDecision.ask(
            reason=f"Plugin source not explicitly trusted: {source}",
            rule_id=self.rule_id,
            severity=PolicySeverity.WARNING,
        )


@dataclass(slots=True)
class MCPServerAllowlistRule(PolicyRule):
    """Restrict MCP tool execution to allowlisted servers."""

    rule_id: str = "policy.mcp_allowlist"
    description: str = "Deny MCP servers not present in allowlist"
    priority: int = 20
    group: str = "mcp"

    def applies(self, context: PolicyContext) -> bool:
        return bool(context.mcp_server) or context.tool_name.startswith("mcp.")

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        server = context.mcp_server
        if server is None and context.tool_name.startswith("mcp."):
            parts = context.tool_name.split(".")
            if len(parts) >= 3:
                server = parts[1]
        if server is None:
            return PolicyDecision.ask(
                reason="Unable to identify MCP server",
                rule_id=self.rule_id,
                severity=PolicySeverity.WARNING,
            )

        allowlist = context.session_metadata.get("allowed_mcp_servers", [])
        if not isinstance(allowlist, list):
            allowlist = []
        if not allowlist:
            return PolicyDecision.ask(
                reason="MCP allowlist not configured",
                rule_id=self.rule_id,
                severity=PolicySeverity.WARNING,
            )
        if allowlist and server not in allowlist:
            return PolicyDecision.deny(
                reason=f"MCP server not in allowlist: {server}",
                rule_id=self.rule_id,
                severity=PolicySeverity.ERROR,
            )
        return PolicyDecision.allow(reason="MCP server allowed", rule_id=self.rule_id)


@dataclass(slots=True)
class NetworkAccessValidationRule(PolicyRule):
    """Validate outbound network access targets."""

    rule_id: str = "policy.network_target_validation"
    description: str = "Deny invalid or loopback targets and ask for unknown domains"
    priority: int = 25
    group: str = "network"

    def applies(self, context: PolicyContext) -> bool:
        return context.network_target is not None

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        target = (context.network_target or "").strip()
        if not target:
            return PolicyDecision.ask(
                reason="Network target missing",
                rule_id=self.rule_id,
                severity=PolicySeverity.WARNING,
            )
        host = target.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_multicast or ip.is_unspecified:
                return PolicyDecision.deny(
                    reason=f"Disallowed network target: {host}",
                    rule_id=self.rule_id,
                    severity=PolicySeverity.ERROR,
                )
            return PolicyDecision.allow(reason="Valid IP network target", rule_id=self.rule_id)
        except ValueError:
            if "." not in host:
                return PolicyDecision.ask(
                    reason=f"Ambiguous network target: {host}",
                    rule_id=self.rule_id,
                    severity=PolicySeverity.WARNING,
                )
            return PolicyDecision.allow(reason="Domain network target accepted", rule_id=self.rule_id)


@dataclass(slots=True)
class AgentPrivilegeScopingRule(PolicyRule):
    """Enforce agent tool scope restrictions."""

    rule_id: str = "policy.agent_privilege_scoping"
    description: str = "Deny agent tool calls outside allowed scopes"
    priority: int = 15
    group: str = "agent"

    def applies(self, context: PolicyContext) -> bool:
        return context.agent_name is not None

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        allowed_scopes = context.metadata.get("agent_tool_access_scope")
        if not isinstance(allowed_scopes, list) or not allowed_scopes:
            return PolicyDecision.allow(reason="No explicit agent scope limits", rule_id=self.rule_id)
        if any(context.tool_name.startswith(scope) for scope in allowed_scopes):
            return PolicyDecision.allow(reason="Tool within agent scope", rule_id=self.rule_id)
        return PolicyDecision.deny(
            reason=f"Tool outside agent scope: {context.tool_name}",
            rule_id=self.rule_id,
            severity=PolicySeverity.ERROR,
        )


@dataclass(slots=True)
class DangerousToolConfirmationRule(PolicyRule):
    """Escalate dangerous tools to confirmation."""

    rule_id: str = "policy.dangerous_tool_confirmation"
    description: str = "Require confirmation for dangerous tools"
    priority: int = 40
    group: str = "tool"

    def applies(self, context: PolicyContext) -> bool:
        return context.dangerous or context.requires_approval

    def evaluate(self, _context: PolicyContext) -> PolicyDecision:
        return PolicyDecision.ask(
            reason="Dangerous or approval-required tool",
            rule_id=self.rule_id,
            severity=PolicySeverity.WARNING,
            sandbox_required=True,
        )


def default_policy_rules() -> list[PolicyRule]:
    """Return baseline rule set."""
    return [
        WorkspaceWriteRestrictionRule(),
        AgentPrivilegeScopingRule(),
        MCPServerAllowlistRule(),
        NetworkAccessValidationRule(),
        PluginTrustLevelRule(),
        DangerousToolConfirmationRule(),
    ]


def decision_weight(action: PolicyAction) -> int:
    """Conflict-resolution precedence (higher is stricter)."""
    return {
        PolicyAction.ALLOW: 0,
        PolicyAction.ASK: 1,
        PolicyAction.DENY: 2,
    }[action]

