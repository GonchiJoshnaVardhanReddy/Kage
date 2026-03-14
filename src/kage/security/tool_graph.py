"""Tool capability graph for security workflow planning."""

from __future__ import annotations

from collections.abc import Iterable

# Ordered stages used for multi-step workflow progression.
STAGE_ORDER: list[str] = [
    "reconnaissance",
    "web_enumeration",
    "vulnerability_scanning",
    "sql_injection_testing",
    "password_attacks",
    "exploitation",
    "post_exploitation",
]

# Canonical stage aliases.
_STAGE_ALIASES: dict[str, str] = {
    "recon": "reconnaissance",
    "enum": "web_enumeration",
    "enumeration": "web_enumeration",
    "vuln_scanning": "vulnerability_scanning",
    "vulnerability_scan": "vulnerability_scanning",
    "sqli": "sql_injection_testing",
    "password": "password_attacks",
    "post_exploit": "post_exploitation",
}

# Built-in graph.
_TOOL_GRAPH: dict[str, list[str]] = {
    "reconnaissance": ["nmap", "dnsrecon", "amass", "theharvester"],
    "web_enumeration": ["gobuster", "dirb", "ffuf"],
    "vulnerability_scanning": ["nikto", "nuclei", "wpscan"],
    "sql_injection_testing": ["sqlmap"],
    "password_attacks": ["hydra", "hashcat", "john"],
    "exploitation": ["metasploit", "searchsploit"],
    "post_exploitation": ["empire", "powersploit"],
}


def _normalize_stage(stage: str) -> str:
    key = stage.strip().lower().replace(" ", "_").replace("-", "_")
    return _STAGE_ALIASES.get(key, key)


def _normalize_tool_name(tool_name: str) -> str:
    return tool_name.strip().lower()


def _ensure_stage(stage: str) -> str:
    normalized = _normalize_stage(stage)
    if normalized not in _TOOL_GRAPH:
        _TOOL_GRAPH[normalized] = []
        STAGE_ORDER.append(normalized)
    return normalized


def get_tools_for_stage(stage: str) -> list[str]:
    """Return recommended tools for a workflow stage."""
    normalized = _normalize_stage(stage)
    return list(_TOOL_GRAPH.get(normalized, []))


def get_stage_for_tool(tool_name: str) -> str | None:
    """Return the security stage for a tool, or None if unknown."""
    normalized_tool = _normalize_tool_name(tool_name)
    for stage in STAGE_ORDER:
        if normalized_tool in _TOOL_GRAPH.get(stage, []):
            return stage
    return None


def get_next_stage(stage: str) -> str | None:
    """Return the next stage in workflow order."""
    normalized = _normalize_stage(stage)
    if normalized not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(normalized)
    if idx + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[idx + 1]


def register_tool(stage: str, tool_name: str) -> None:
    """Add a tool to a stage dynamically."""
    normalized_stage = _ensure_stage(stage)
    normalized_tool = _normalize_tool_name(tool_name)
    if normalized_tool and normalized_tool not in _TOOL_GRAPH[normalized_stage]:
        _TOOL_GRAPH[normalized_stage].append(normalized_tool)


def register_tools_for_stage(stage: str, tools: Iterable[str]) -> None:
    """Add multiple tools to a stage dynamically."""
    for tool in tools:
        register_tool(stage, tool)


def generate_workflow_plan(user_request: str) -> list[tuple[str, str]]:
    """Generate a stage/tool workflow plan from a user request."""
    text = user_request.lower()

    if any(term in text for term in ("scan", "recon", "enumerate", "vulnerability", "web")):
        preferred = [
            ("reconnaissance", "nmap"),
            ("web_enumeration", "gobuster"),
            ("vulnerability_scanning", "nikto"),
        ]
    elif any(term in text for term in ("sql injection", "sqli", "sqlmap")):
        preferred = [
            ("reconnaissance", "nmap"),
            ("sql_injection_testing", "sqlmap"),
        ]
    else:
        preferred = [("reconnaissance", "nmap")]

    plan: list[tuple[str, str]] = []
    for stage, fallback_tool in preferred:
        tools = get_tools_for_stage(stage)
        selected = fallback_tool if fallback_tool in tools else (tools[0] if tools else fallback_tool)
        plan.append((stage, selected))
    return plan

