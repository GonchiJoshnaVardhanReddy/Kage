"""Response parsers for AI output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedCommand:
    """A command extracted from AI response."""

    command: str
    description: str | None = None


@dataclass
class ParsedFinding:
    """A finding extracted from AI response."""

    title: str
    severity: str
    description: str
    evidence: str | None = None
    impact: str | None = None
    remediation: str | None = None


@dataclass
class ParsedResponse:
    """Parsed AI response containing text, commands, and findings."""

    text: str
    commands: list[ParsedCommand]
    findings: list[ParsedFinding]
    raw: str


# Regex patterns for command extraction
COMMAND_BLOCK_PATTERN = re.compile(
    r"```command(?::description=([^\n]*))?\n(.*?)```",
    re.DOTALL,
)

# Alternative patterns for shell/bash blocks that look like commands
SHELL_BLOCK_PATTERN = re.compile(
    r"```(?:shell|bash|sh|zsh|cmd|powershell)?\n(.*?)```",
    re.DOTALL,
)

# Pattern for inline commands ($ prefix)
INLINE_COMMAND_PATTERN = re.compile(r"^\$ (.+)$", re.MULTILINE)

# JSON block pattern for findings
JSON_BLOCK_PATTERN = re.compile(r"```json\n(.*?)```", re.DOTALL)


def parse_response(response: str) -> ParsedResponse:
    """Parse an AI response to extract commands and findings."""
    commands: list[ParsedCommand] = []
    findings: list[ParsedFinding] = []
    text = response

    # Extract explicit command blocks
    for match in COMMAND_BLOCK_PATTERN.finditer(response):
        description = match.group(1)
        command = match.group(2).strip()
        if command:
            commands.append(ParsedCommand(command=command, description=description))
        # Remove from text
        text = text.replace(match.group(0), "")

    # Extract JSON blocks for findings
    for match in JSON_BLOCK_PATTERN.finditer(response):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                for item in data:
                    if _looks_like_finding(item):
                        findings.append(
                            ParsedFinding(
                                title=item.get("title", "Unknown"),
                                severity=item.get("severity", "info"),
                                description=item.get("description", ""),
                                evidence=item.get("evidence"),
                                impact=item.get("impact"),
                                remediation=item.get("remediation"),
                            )
                        )
        except json.JSONDecodeError:
            pass

    # Clean up text
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    return ParsedResponse(
        text=text,
        commands=commands,
        findings=findings,
        raw=response,
    )


def _looks_like_finding(item: dict[str, Any]) -> bool:
    """Check if a dict looks like a security finding."""
    required = {"title", "severity"}
    return required.issubset(item.keys())


def extract_commands_simple(text: str) -> list[str]:
    """Simple command extraction from text - gets commands in code blocks."""
    commands = []

    # Match any code block
    for match in re.finditer(r"```[\w]*\n(.*?)```", text, re.DOTALL):
        content = match.group(1).strip()
        # Check if it looks like a command (single line, starts with common prefixes)
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if line and _looks_like_command(line):
                # Remove common prefixes
                if line.startswith("$ ") or line.startswith("# "):
                    line = line[2:]
                commands.append(line)

    return commands


def _looks_like_command(line: str) -> bool:
    """Heuristic to determine if a line looks like a shell command."""
    # Common command prefixes
    command_starters = [
        "nmap",
        "nikto",
        "gobuster",
        "dirb",
        "ffuf",
        "wfuzz",
        "sqlmap",
        "hydra",
        "john",
        "hashcat",
        "metasploit",
        "msfconsole",
        "curl",
        "wget",
        "nc",
        "netcat",
        "ssh",
        "scp",
        "ftp",
        "grep",
        "cat",
        "ls",
        "cd",
        "pwd",
        "find",
        "locate",
        "python",
        "python3",
        "ruby",
        "perl",
        "php",
        "sudo",
        "su",
        "chmod",
        "chown",
        "mkdir",
        "rm",
        "ping",
        "traceroute",
        "dig",
        "nslookup",
        "host",
        "whois",
        "tcpdump",
        "wireshark",
        "tshark",
        "searchsploit",
        "msfvenom",
        "exploit",
        "$",
        "#",
    ]

    line_lower = line.lower()
    return any(line_lower.startswith(cmd) for cmd in command_starters)


def parse_tool_output_for_findings(
    _tool: str,
    _output: str,
    ai_analysis: str | None = None,
) -> list[ParsedFinding]:
    """Parse tool output and AI analysis to extract findings."""
    findings = []

    # If AI provided analysis, parse it
    if ai_analysis:
        parsed = parse_response(ai_analysis)
        findings.extend(parsed.findings)

    # Tool-specific parsing can be added here
    # For now, rely on AI analysis

    return findings
