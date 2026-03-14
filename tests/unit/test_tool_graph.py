"""Tests for security tool capability graph."""

from kage.security.tool_graph import (
    generate_workflow_plan,
    get_next_stage,
    get_stage_for_tool,
    get_tools_for_stage,
    register_tool,
    register_tools_for_stage,
)


def test_get_tools_for_stage_known_stage() -> None:
    tools = get_tools_for_stage("reconnaissance")
    assert "nmap" in tools


def test_get_tools_for_stage_alias() -> None:
    tools = get_tools_for_stage("recon")
    assert "nmap" in tools


def test_get_stage_for_tool() -> None:
    assert get_stage_for_tool("sqlmap") == "sql_injection_testing"


def test_get_next_stage() -> None:
    assert get_next_stage("reconnaissance") == "web_enumeration"
    assert get_next_stage("post_exploitation") is None


def test_dynamic_register_tool() -> None:
    register_tool("web_enumeration", "feroxbuster")
    assert "feroxbuster" in get_tools_for_stage("web_enumeration")
    assert get_stage_for_tool("feroxbuster") == "web_enumeration"


def test_dynamic_register_multiple_tools() -> None:
    register_tools_for_stage("reconnaissance", ["customreconx", "newsqltool"])
    assert get_stage_for_tool("customreconx") == "reconnaissance"
    assert get_stage_for_tool("newsqltool") == "reconnaissance"


def test_generate_workflow_plan_scan_request() -> None:
    plan = generate_workflow_plan("scan example.com")
    assert plan == [
        ("reconnaissance", "nmap"),
        ("web_enumeration", "gobuster"),
        ("vulnerability_scanning", "nikto"),
    ]
