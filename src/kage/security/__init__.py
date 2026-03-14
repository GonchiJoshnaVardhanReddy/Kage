"""Security module for Kage."""

from kage.security.approval import ApprovalDecision, ApprovalResult, ApprovalWorkflow
from kage.security.audit import AuditLogger
from kage.security.output_parser import (
    parse_gobuster_output,
    parse_nikto_output,
    parse_nmap_output,
    parse_sqlmap_output,
    parse_tool_output,
)
from kage.security.safemode import (
    DangerLevel,
    SafeModeFilter,
    SafeModeResult,
    classify_command_category,
)
from kage.security.scope import ScopeValidationResult, ScopeValidator
from kage.security.tool_checker import (
    check_tool_installed,
    detect_installed_security_tools,
    get_install_suggestion,
)
from kage.security.tool_graph import (
    extend_graph_from_mcp_discovery,
    generate_workflow_plan,
    get_next_stage,
    get_stage_for_tool,
    get_tools_for_stage,
    register_tool,
    register_tools_for_stage,
)

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
    "extend_graph_from_mcp_discovery",
    "generate_workflow_plan",
    "get_next_stage",
    "get_stage_for_tool",
    "get_tools_for_stage",
    "register_tool",
    "register_tools_for_stage",
    "check_tool_installed",
    "detect_installed_security_tools",
    "get_install_suggestion",
    "parse_gobuster_output",
    "parse_nikto_output",
    "parse_nmap_output",
    "parse_sqlmap_output",
    "parse_tool_output",
]
