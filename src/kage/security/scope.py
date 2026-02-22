"""Scope validation for Kage."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from kage.core.models import Scope


@dataclass
class ScopeValidationResult:
    """Result of scope validation."""

    in_scope: bool
    target_checked: str
    matched_scope: str | None = None
    reason: str | None = None


class ScopeValidator:
    """Validates targets against defined scope."""

    def __init__(self, scope: Scope) -> None:
        self.scope = scope
        self._compiled_patterns: list[tuple[str, Any]] = []
        self._compile_scope()

    def _compile_scope(self) -> None:
        """Pre-compile scope patterns for efficient matching."""
        for target in self.scope.targets:
            if target.target_type == "ip":
                try:
                    ip = ipaddress.ip_address(target.value)
                    self._compiled_patterns.append(("ip", ip, target.value))
                except ValueError:
                    pass

            elif target.target_type == "cidr":
                try:
                    network = ipaddress.ip_network(target.value, strict=False)
                    self._compiled_patterns.append(("cidr", network, target.value))
                except ValueError:
                    pass

            elif target.target_type == "domain":
                # Create regex for domain matching (including subdomains)
                pattern = self._domain_to_regex(target.value)
                self._compiled_patterns.append(("domain", pattern, target.value))

            elif target.target_type == "url":
                parsed = urlparse(target.value)
                if parsed.netloc:
                    pattern = self._domain_to_regex(parsed.netloc)
                    self._compiled_patterns.append(("domain", pattern, target.value))

    def _domain_to_regex(self, domain: str) -> re.Pattern:
        """Convert domain to regex pattern that matches subdomains."""
        # Escape dots and create pattern
        escaped = re.escape(domain)
        # Match exact domain or any subdomain
        pattern = f"^(.*\\.)?{escaped}$"
        return re.compile(pattern, re.IGNORECASE)

    def check_ip(self, ip_str: str) -> ScopeValidationResult:
        """Check if an IP address is in scope."""
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return ScopeValidationResult(
                in_scope=False,
                target_checked=ip_str,
                reason="Invalid IP address",
            )

        # Check against exclusions first
        for excluded in self.scope.excluded:
            try:
                if ip == ipaddress.ip_address(excluded):
                    return ScopeValidationResult(
                        in_scope=False,
                        target_checked=ip_str,
                        reason=f"Explicitly excluded: {excluded}",
                    )
                if ip in ipaddress.ip_network(excluded, strict=False):
                    return ScopeValidationResult(
                        in_scope=False,
                        target_checked=ip_str,
                        reason=f"In excluded network: {excluded}",
                    )
            except ValueError:
                pass

        # Check against scope
        for pattern_type, pattern, original in self._compiled_patterns:
            if pattern_type == "ip" and ip == pattern or pattern_type == "cidr" and ip in pattern:
                return ScopeValidationResult(
                    in_scope=True,
                    target_checked=ip_str,
                    matched_scope=original,
                )

        return ScopeValidationResult(
            in_scope=False,
            target_checked=ip_str,
            reason="Not in defined scope",
        )

    def check_domain(self, domain: str) -> ScopeValidationResult:
        """Check if a domain is in scope."""
        # Normalize domain
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]

        # Check exclusions
        for excluded in self.scope.excluded:
            if domain == excluded.lower() or domain.endswith(f".{excluded.lower()}"):
                return ScopeValidationResult(
                    in_scope=False,
                    target_checked=domain,
                    reason=f"Explicitly excluded: {excluded}",
                )

        # Check against scope
        for pattern_type, pattern, original in self._compiled_patterns:
            if pattern_type == "domain" and pattern.match(domain):
                return ScopeValidationResult(
                    in_scope=True,
                    target_checked=domain,
                    matched_scope=original,
                )

        return ScopeValidationResult(
            in_scope=False,
            target_checked=domain,
            reason="Not in defined scope",
        )

    def check_url(self, url: str) -> ScopeValidationResult:
        """Check if a URL's host is in scope."""
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path.split("/")[0]

        # Remove port if present
        if ":" in host:
            host = host.split(":")[0]

        # Try as IP first
        try:
            ipaddress.ip_address(host)
            return self.check_ip(host)
        except ValueError:
            return self.check_domain(host)

    def extract_targets_from_command(self, command: str) -> list[str]:
        """Extract potential targets from a command string."""
        targets = []

        # IP address pattern
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        targets.extend(re.findall(ip_pattern, command))

        # CIDR pattern
        cidr_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b"
        targets.extend(re.findall(cidr_pattern, command))

        # Domain pattern (simplified)
        domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
        for match in re.findall(domain_pattern, command):
            # Filter out common false positives
            if not match.endswith((".txt", ".xml", ".json", ".py", ".sh")):
                targets.append(match)

        # URL pattern
        url_pattern = r"https?://[^\s]+"
        for match in re.findall(url_pattern, command):
            parsed = urlparse(match)
            if parsed.netloc:
                targets.append(parsed.netloc)

        return list(set(targets))

    def validate_command(self, command: str) -> tuple[bool, list[ScopeValidationResult]]:
        """Validate all targets in a command against scope.
        
        Returns:
            Tuple of (all_in_scope, list of validation results)
        """
        if not self.scope.targets:
            # No scope defined - allow everything
            return True, []

        targets = self.extract_targets_from_command(command)
        results = []
        all_in_scope = True

        for target in targets:
            try:
                ipaddress.ip_address(target)
                result = self.check_ip(target)
            except ValueError:
                if "/" in target:
                    # CIDR - check base IP
                    result = self.check_ip(target.split("/")[0])
                else:
                    result = self.check_domain(target)

            results.append(result)
            if not result.in_scope:
                all_in_scope = False

        return all_in_scope, results


def resolve_domain_to_ip(domain: str) -> str | None:
    """Resolve a domain to its IP address."""
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None
