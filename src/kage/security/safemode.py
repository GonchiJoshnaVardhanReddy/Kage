"""Safe mode filter for Kage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class DangerLevel(str, Enum):
    """Danger level classification."""

    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


@dataclass
class SafeModeResult:
    """Result of safe mode check."""

    allowed: bool
    danger_level: DangerLevel
    matched_rule: str | None = None
    reason: str | None = None
    suggestion: str | None = None


# Dangerous command patterns with explanations
DANGEROUS_PATTERNS: list[tuple[str, DangerLevel, str, str | None]] = [
    # System destruction
    (r"\brm\s+(-[rf]+\s+)?/\s*$", DangerLevel.BLOCKED, "Removes root filesystem", None),
    (r"\brm\s+-[rf]*\s+/\s*$", DangerLevel.BLOCKED, "Removes root filesystem", None),
    (r"\bmkfs\b", DangerLevel.BLOCKED, "Formats filesystem", None),
    (r"\bdd\s+if=.+\s+of=/dev/[sh]d", DangerLevel.BLOCKED, "Overwrites disk", None),
    (r">\s*/dev/[sh]d[a-z]", DangerLevel.BLOCKED, "Overwrites disk", None),
    (r":\(\)\s*{\s*:\s*\|\s*:\s*&\s*}\s*;", DangerLevel.BLOCKED, "Fork bomb", None),
    # Permission disasters
    (
        r"\bchmod\s+(-R\s+)?777\s+/",
        DangerLevel.BLOCKED,
        "Insecure permissions on system dirs",
        None,
    ),
    (r"\bchown\s+(-R\s+)?.+\s+/$", DangerLevel.BLOCKED, "Changes ownership of root", None),
    # Remote code execution risks
    (
        r"\bwget\s+.+\|\s*(ba)?sh",
        DangerLevel.BLOCKED,
        "Downloads and executes remote code",
        "Download first, inspect, then execute",
    ),
    (
        r"\bcurl\s+.+\|\s*(ba)?sh",
        DangerLevel.BLOCKED,
        "Downloads and executes remote code",
        "Download first, inspect, then execute",
    ),
    # DoS patterns
    (
        r"\b(hping3?|slowloris)\b.*--flood",
        DangerLevel.DANGEROUS,
        "Denial of Service attack",
        "Use rate-limited scanning instead",
    ),
    (
        r"\b(ab|siege|wrk)\s+.*-c\s*[5-9]\d{2,}",
        DangerLevel.DANGEROUS,
        "High-concurrency stress test",
        "Reduce concurrency",
    ),
    # Bruteforce without limits
    (
        r"\bhydra\b(?!.*-t\s*[1-4]\b)",
        DangerLevel.CAUTION,
        "Bruteforce without thread limit",
        "Add -t 4 to limit threads",
    ),
    (
        r"\bmedusa\b(?!.*-t\s*[1-4]\b)",
        DangerLevel.CAUTION,
        "Bruteforce without thread limit",
        "Add -t 4 to limit threads",
    ),
    # Aggressive scanning
    (
        r"\bnmap\b.*-T\s*5",
        DangerLevel.CAUTION,
        "Insanely aggressive scan timing",
        "Use -T4 or lower",
    ),
    (
        r"\bmasscan\b.*--rate\s*[1-9]\d{5,}",
        DangerLevel.DANGEROUS,
        "Extremely high scan rate",
        "Reduce rate to 10000 or lower",
    ),
    # Data exfiltration
    (r"\bnc\b.*-e\s*/bin/(ba)?sh", DangerLevel.DANGEROUS, "Reverse shell", None),
    (r"\bbash\s+-i\s+>&\s*/dev/tcp/", DangerLevel.DANGEROUS, "Reverse shell", None),
    # Privilege escalation attempts on host
    (r"\bsudo\s+su\s*$", DangerLevel.CAUTION, "Privilege escalation", None),
    (r"\bsudo\s+-i\s*$", DangerLevel.CAUTION, "Privilege escalation", None),
    # History/log tampering
    (r"\bhistory\s+-c", DangerLevel.CAUTION, "Clears command history", None),
    (r">\s*/var/log/", DangerLevel.DANGEROUS, "Clears system logs", None),
    (r"\brm\s+.*/var/log/", DangerLevel.DANGEROUS, "Removes system logs", None),
    # Network disruption
    (r"\barpspoof\b", DangerLevel.DANGEROUS, "ARP spoofing attack", None),
    (r"\bettercap\b.*arp\.spoof", DangerLevel.DANGEROUS, "ARP spoofing attack", None),
    (r"\bresponder\b", DangerLevel.CAUTION, "LLMNR/NBT-NS poisoning", None),
]

# Commands that are always safe
SAFE_COMMANDS: list[str] = [
    "whoami",
    "id",
    "pwd",
    "ls",
    "cat",
    "head",
    "tail",
    "grep",
    "find",
    "file",
    "strings",
    "xxd",
    "hexdump",
    "base64",
    "ping",
    "traceroute",
    "dig",
    "nslookup",
    "host",
    "whois",
    "curl -I",
    "curl --head",
    "wget --spider",
    "nmap -sn",
    "nmap -sP",  # Ping scans
    "searchsploit",
    "echo",
    "printf",
]


class SafeModeFilter:
    """Filters commands based on safe mode rules."""

    def __init__(
        self,
        enabled: bool = True,
        custom_blocked: list[str] | None = None,
        custom_allowed: list[str] | None = None,
    ) -> None:
        self.enabled = enabled
        self.custom_blocked = custom_blocked or []
        self.custom_allowed = custom_allowed or []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self._compiled_dangerous = [
            (re.compile(pattern, re.IGNORECASE), level, reason, suggestion)
            for pattern, level, reason, suggestion in DANGEROUS_PATTERNS
        ]

        self._compiled_blocked = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.custom_blocked
        ]

        self._compiled_allowed = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.custom_allowed
        ]

    def check(self, command: str) -> SafeModeResult:
        """Check if a command is allowed under safe mode.

        Returns SafeModeResult with allowed=True if command is safe to execute.
        """
        if not self.enabled:
            return SafeModeResult(
                allowed=True,
                danger_level=DangerLevel.SAFE,
                reason="Safe mode disabled",
            )

        command = command.strip()

        # Check custom allowed patterns first
        for pattern in self._compiled_allowed:
            if pattern.search(command):
                return SafeModeResult(
                    allowed=True,
                    danger_level=DangerLevel.SAFE,
                    reason="Matches allowed pattern",
                )

        # Check custom blocked patterns
        for pattern in self._compiled_blocked:
            if pattern.search(command):
                return SafeModeResult(
                    allowed=False,
                    danger_level=DangerLevel.BLOCKED,
                    matched_rule="custom_blocked",
                    reason="Blocked by custom rule",
                )

        # Check against safe commands
        for safe_cmd in SAFE_COMMANDS:
            if command.startswith(safe_cmd):
                return SafeModeResult(
                    allowed=True,
                    danger_level=DangerLevel.SAFE,
                )

        # Check dangerous patterns
        for pattern, level, reason, suggestion in self._compiled_dangerous:
            if pattern.search(command):
                # BLOCKED and DANGEROUS are both disallowed in safe mode
                allowed = level not in (
                    DangerLevel.BLOCKED,
                    DangerLevel.DANGEROUS,
                )
                return SafeModeResult(
                    allowed=allowed,
                    danger_level=level,
                    matched_rule=pattern.pattern,
                    reason=reason,
                    suggestion=suggestion,
                )

        # Default: allow with caution
        return SafeModeResult(
            allowed=True,
            danger_level=DangerLevel.SAFE,
        )

    def get_danger_level(self, command: str) -> DangerLevel:
        """Get just the danger level for a command."""
        return self.check(command).danger_level

    def is_allowed(self, command: str) -> bool:
        """Quick check if command is allowed."""
        return self.check(command).allowed


def classify_command_category(command: str) -> str:
    """Classify a command into a category."""
    command_lower = command.lower()

    categories = {
        "reconnaissance": ["nmap", "masscan", "ping", "traceroute", "dig", "nslookup", "whois"],
        "enumeration": ["gobuster", "dirb", "ffuf", "wfuzz", "nikto", "enum4linux"],
        "exploitation": ["sqlmap", "msfconsole", "metasploit", "searchsploit"],
        "bruteforce": ["hydra", "medusa", "john", "hashcat", "crackmapexec"],
        "network": ["nc", "netcat", "socat", "curl", "wget", "ssh", "scp"],
        "privilege_escalation": ["sudo", "su", "linpeas", "winpeas"],
        "post_exploitation": ["mimikatz", "bloodhound", "empire"],
        "utility": ["cat", "grep", "find", "ls", "pwd", "echo", "base64"],
    }

    for category, tools in categories.items():
        if any(tool in command_lower for tool in tools):
            return category

    return "other"
