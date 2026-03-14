"""Intent detection engine for Kage.

Classifies user input into one of four categories:
- CHAT: Questions, explanations, general conversation
- DEVELOPMENT: Coding, scripting, building, file operations
- SYSTEM: System administration, package management, OS tasks
- SECURITY: Penetration testing, security scanning, exploitation
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """User request intent categories."""

    CHAT = "chat"
    DEVELOPMENT = "development"
    SYSTEM = "system"
    SECURITY = "security"


class IntentResult(BaseModel):
    """Result of intent classification."""

    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)
    reasoning: str = ""


# Security tools used for security intent detection
SECURITY_TOOLS: set[str] = {
    "nmap", "sqlmap", "nikto", "hydra", "gobuster", "dirb", "dirbuster",
    "wpscan", "msfconsole", "metasploit", "msfvenom", "enum4linux",
    "john", "hashcat", "aircrack-ng", "responder", "crackmapexec",
    "burpsuite", "nuclei", "subfinder", "amass", "ffuf", "feroxbuster",
    "whatweb", "wfuzz", "masscan", "rustscan", "netcat", "nc",
    "wireshark", "tshark", "tcpdump", "ettercap", "bettercap",
    "searchsploit", "exploitdb", "smbclient", "rpcclient", "impacket",
    "bloodhound", "mimikatz", "powershell-empire", "covenant",
    "chisel", "ligolo", "proxychains", "socat", "netdiscover",
    "arpspoof", "dnsspoof", "sslstrip", "beef", "zaproxy", "zap",
    "openvas", "nessus", "lynis", "testssl", "sslscan",
    "theharvester", "recon-ng", "maltego", "shodan", "censys",
    "fierce", "dnsrecon", "dig", "whois", "traceroute",
}

# Security action keywords (verbs/phrases)
_SECURITY_ACTIONS: set[str] = {
    "scan", "exploit", "enumerate", "pentest", "brute", "bruteforce",
    "crack", "fuzz", "sniff", "spoof", "intercept", "pivot",
    "escalate", "privilege", "reverse shell", "payload", "inject",
    "sql injection", "xss", "csrf", "rce", "lfi", "rfi",
    "vulnerability", "vulnerabilities", "cve", "cvss",
    "port scan", "service scan", "directory scan", "subdomain",
    "recon", "reconnaissance", "footprint", "osint",
    "post-exploitation", "lateral movement", "exfiltrate",
    "ctf", "challenge", "capture the flag", "enumerate domain",
}

# Development keywords
_DEV_KEYWORDS: set[str] = {
    "code", "script", "function", "class", "module", "package",
    "create", "write", "build", "compile", "debug", "refactor",
    "test", "unittest", "pytest", "api", "endpoint", "route",
    "database", "schema", "migration", "orm",
    "frontend", "backend", "server", "client", "app",
    "html", "css", "javascript", "typescript", "react", "vue",
    "flask", "django", "fastapi", "express", "spring",
    "git commit", "git push", "git pull", "git branch",
    "deploy", "dockerfile", "docker-compose", "kubernetes",
}

# Development tool commands
_DEV_TOOLS: set[str] = {
    "python", "python3", "pip", "pip3", "node", "npm", "npx", "yarn",
    "go", "cargo", "rustc", "javac", "java", "mvn", "gradle",
    "gcc", "g++", "make", "cmake", "dotnet", "ruby", "gem",
    "git", "docker", "docker-compose", "kubectl",
    "code", "vim", "nano", "emacs",
}

# System administration keywords
_SYSTEM_KEYWORDS: set[str] = {
    "install", "update", "upgrade", "remove", "uninstall",
    "service", "daemon", "process", "restart", "enable", "disable",
    "firewall", "iptables", "ufw", "network", "interface",
    "disk", "partition", "mount", "filesystem",
    "user", "group", "permission", "chmod", "chown",
    "cron", "systemctl", "journalctl",
    "ssh", "scp", "rsync", "wget", "curl",
}

# System tool commands
_SYSTEM_TOOLS: set[str] = {
    "apt", "apt-get", "yum", "dnf", "pacman", "brew",
    "systemctl", "service", "journalctl",
    "ls", "cd", "cp", "mv", "rm", "mkdir", "cat", "grep", "find",
    "ps", "top", "htop", "kill", "df", "du", "free",
    "ifconfig", "ip", "ping", "netstat", "ss",
    "tar", "zip", "unzip", "gzip",
    "chmod", "chown", "chgrp",
    "useradd", "userdel", "passwd",
    "crontab", "at",
}

# Chat indicators (questions / explanations)
_CHAT_PATTERNS: list[str] = [
    r"^(what|how|why|when|where|which|who)\b",
    r"^(explain|describe|tell me|teach|define|clarify)\b",
    r"^(is|are|was|were|can|could|should|would|do|does|did)\b.*\?",
    r"^(help me understand|i don'?t understand|what does .* mean)",
    r"^(difference between|compare|versus|vs\.?)\b",
    r"^(list|summarize|summary|overview|introduction)\b",
    r"\?$",  # Ends with question mark
]


def _extract_command_token(text: str) -> str | None:
    """Extract the first command/tool token from user input."""
    text = text.strip().lower()

    # Direct command: "nmap 192.168.1.1"
    first_word = text.split()[0] if text.split() else ""
    if first_word in SECURITY_TOOLS | _DEV_TOOLS | _SYSTEM_TOOLS:
        return first_word

    # "run nmap", "execute nmap", "use nmap"
    run_match = re.match(r"^(?:run|execute|use|start|launch|open)\s+(\S+)", text)
    if run_match:
        return run_match.group(1)

    return None


def _count_keyword_matches(text: str, keywords: set[str]) -> list[str]:
    """Count how many keywords from a set appear in the text."""
    text_lower = text.lower()
    matches = []
    for kw in keywords:
        if kw in text_lower:
            matches.append(kw)
    return matches


def classify_intent(user_input: str) -> IntentResult:
    """Classify user input into an intent category.

    Uses a hybrid approach:
    1. Check for explicit tool/command references (high confidence)
    2. Check for domain-specific keywords (medium confidence)
    3. Check for chat patterns (fallback)

    For ambiguous cases, returns low confidence so the AI can be asked.
    """
    text = user_input.strip()
    text_lower = text.lower()

    if not text:
        return IntentResult(intent=Intent.CHAT, confidence=1.0, reasoning="Empty input")

    # --- Stage 1: Explicit tool detection (highest confidence) ---

    cmd_token = _extract_command_token(text)

    if cmd_token and cmd_token in SECURITY_TOOLS:
        return IntentResult(
            intent=Intent.SECURITY,
            confidence=0.95,
            matched_keywords=[cmd_token],
            reasoning=f"Security tool detected: {cmd_token}",
        )

    if cmd_token and cmd_token in _DEV_TOOLS:
        return IntentResult(
            intent=Intent.DEVELOPMENT,
            confidence=0.90,
            matched_keywords=[cmd_token],
            reasoning=f"Development tool detected: {cmd_token}",
        )

    if cmd_token and cmd_token in _SYSTEM_TOOLS:
        return IntentResult(
            intent=Intent.SYSTEM,
            confidence=0.90,
            matched_keywords=[cmd_token],
            reasoning=f"System tool detected: {cmd_token}",
        )

    # --- Stage 2: Chat pattern detection (questions override keywords) ---
    # Questions like "what is SQL injection?" are chat even if they contain
    # security keywords — the user is asking for an explanation, not a command.

    is_question = any(re.search(p, text_lower) for p in _CHAT_PATTERNS)

    # --- Stage 3: Keyword-based scoring ---

    security_matches = _count_keyword_matches(text_lower, _SECURITY_ACTIONS)
    dev_matches = _count_keyword_matches(text_lower, _DEV_KEYWORDS)
    system_matches = _count_keyword_matches(text_lower, _SYSTEM_KEYWORDS)

    # Check for target-like patterns (IPs, domains with security context)
    has_target = bool(re.search(
        r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|[\w-]+\.\w{2,})\b", text
    ))
    if has_target and security_matches:
        security_matches.append("target_detected")

    scores = {
        Intent.SECURITY: len(security_matches),
        Intent.DEVELOPMENT: len(dev_matches),
        Intent.SYSTEM: len(system_matches),
    }

    max_score = max(scores.values())

    # If it's clearly a question and keyword matches are weak, prefer chat
    if is_question and max_score <= 2:
        return IntentResult(
            intent=Intent.CHAT,
            confidence=0.85,
            matched_keywords=[],
            reasoning="Chat pattern detected (question/explanation)",
        )

    if max_score >= 2:
        best_intent = max(scores, key=scores.get)  # type: ignore[arg-type]
        all_matches = {
            Intent.SECURITY: security_matches,
            Intent.DEVELOPMENT: dev_matches,
            Intent.SYSTEM: system_matches,
        }
        # Even with strong keywords, questions reduce confidence
        conf = min(0.85, 0.6 + max_score * 0.1)
        if is_question:
            conf = max(0.5, conf - 0.2)
        return IntentResult(
            intent=best_intent,
            confidence=conf,
            matched_keywords=all_matches[best_intent],
            reasoning=f"Multiple keyword matches for {best_intent.value}",
        )

    if max_score == 1:
        best_intent = max(scores, key=scores.get)  # type: ignore[arg-type]
        all_matches = {
            Intent.SECURITY: security_matches,
            Intent.DEVELOPMENT: dev_matches,
            Intent.SYSTEM: system_matches,
        }
        return IntentResult(
            intent=best_intent,
            confidence=0.6,
            matched_keywords=all_matches[best_intent],
            reasoning=f"Single keyword match for {best_intent.value}",
        )

    # --- Stage 4: Chat fallback ---

    if is_question:
        return IntentResult(
            intent=Intent.CHAT,
            confidence=0.85,
            matched_keywords=[],
            reasoning="Chat pattern detected (question/explanation)",
        )

    # --- Stage 5: Default to chat with low confidence (AI should classify) ---

    return IntentResult(
        intent=Intent.CHAT,
        confidence=0.4,
        matched_keywords=[],
        reasoning="No strong signals detected — may need AI classification",
    )


def needs_ai_classification(result: IntentResult) -> bool:
    """Check if the intent result is uncertain enough to need AI classification."""
    return result.confidence < 0.6
