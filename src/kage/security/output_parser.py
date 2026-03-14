"""Security tool output parsing engine."""

from __future__ import annotations

import re
from typing import Any


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def parse_nmap_output(output: str) -> dict[str, Any]:
    """Parse nmap output and extract ports/services/versions."""
    ports: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^\s*(\d+)\/([a-zA-Z]+)\s+(\S+)\s+(\S+)(?:\s+(.*))?$",
        flags=re.MULTILINE,
    )
    for match in pattern.finditer(output):
        port = int(match.group(1))
        protocol = match.group(2).lower()
        state = match.group(3).lower()
        service = match.group(4).lower()
        version = (match.group(5) or "").strip()
        ports.append(
            {
                "port": port,
                "protocol": protocol,
                "state": state,
                "service": service,
                "version": version or None,
            }
        )

    open_ports = [p["port"] for p in ports if p["state"] == "open"]
    services = _dedupe_keep_order([p["service"] for p in ports if p["state"] == "open"])
    return {"ports": ports, "open_ports": open_ports, "services": services}


def parse_gobuster_output(output: str) -> dict[str, Any]:
    """Parse gobuster output and extract discovered directories."""
    directories: list[str] = []

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Common gobuster format: /admin (Status: 301) [Size: 0]
        match = re.match(r"^(/[^\s]+)", stripped)
        if match:
            directories.append(match.group(1))
            continue

        # Alternate format: Found: /admin
        found_match = re.search(r"(?:Found:|Discovered:)\s*(/[^\s]+)", stripped, flags=re.I)
        if found_match:
            directories.append(found_match.group(1))

    return {"directories": _dedupe_keep_order(directories)}


def parse_nikto_output(output: str) -> dict[str, Any]:
    """Parse nikto output and extract findings/target data."""
    findings: list[str] = []

    host_match = re.search(r"Target Host:\s*([^\s]+)", output, flags=re.I)
    port_match = re.search(r"Target Port:\s*(\d+)", output, flags=re.I)

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("+"):
            continue
        if "Target Host:" in stripped or "Target Port:" in stripped:
            continue
        findings.append(stripped.lstrip("+").strip())

    return {
        "target": {
            "host": host_match.group(1) if host_match else None,
            "port": int(port_match.group(1)) if port_match else None,
        },
        "findings": findings,
        "vulnerabilities_detected": len(findings) > 0,
    }


def parse_sqlmap_output(output: str) -> dict[str, Any]:
    """Parse sqlmap output and extract vulnerability indicators."""
    vulnerable = bool(
        re.search(
            r"(parameter.+injectable|is vulnerable|sqlmap resumed the following injection point)",
            output,
            flags=re.I,
        )
    )

    dbms_match = re.search(r"back-end DBMS:\s*([^\n\r]+)", output, flags=re.I)
    dbms = dbms_match.group(1).strip() if dbms_match else None

    parameters = re.findall(r"Parameter:\s*([^\s]+)", output, flags=re.I)
    parameters += re.findall(r"parameter ['\"]?([a-zA-Z0-9_]+)['\"]?", output, flags=re.I)

    db_names = re.findall(r"\[\*\]\s*([a-zA-Z0-9_]+)", output)
    table_names = re.findall(r"\|\s*([a-zA-Z0-9_]+)\s*\|", output)

    return {
        "vulnerable": vulnerable,
        "dbms": dbms,
        "parameters": _dedupe_keep_order([p.lower() for p in parameters]),
        "databases": _dedupe_keep_order(db_names),
        "tables": _dedupe_keep_order(table_names),
    }


_PARSER_MAP = {
    "nmap": parse_nmap_output,
    "gobuster": parse_gobuster_output,
    "nikto": parse_nikto_output,
    "sqlmap": parse_sqlmap_output,
}


def parse_tool_output(tool_name: str, raw_output: str) -> dict[str, Any]:
    """Parse tool output into structured results."""
    normalized = tool_name.strip().lower()
    parser = _PARSER_MAP.get(normalized)
    if not parser:
        return {"tool": normalized, "supported": False, "parsed": None}
    parsed = parser(raw_output)
    return {"tool": normalized, "supported": True, "parsed": parsed}

