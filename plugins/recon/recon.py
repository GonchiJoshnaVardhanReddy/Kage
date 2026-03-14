"""Reconnaissance plugin for Kage."""

from kage.plugins.base import BasePlugin, CapabilityParameter


class ReconPlugin(BasePlugin):
    """Basic reconnaissance capabilities."""

    @property
    def name(self) -> str:
        return "recon"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Basic reconnaissance capabilities for target enumeration"

    @property
    def category(self) -> str:
        return "reconnaissance"

    @property
    def required_tools(self) -> list[str]:
        return ["nmap", "dig", "whois"]

    def setup(self) -> None:
        """Register reconnaissance capabilities."""
        
        # Port scan capability
        self.register_capability(
            name="port_scan",
            description="Perform a port scan on a target IP or hostname",
            handler=self._port_scan,
            parameters=[
                CapabilityParameter(
                    name="target",
                    description="Target IP address or hostname",
                    param_type="string",
                    required=True,
                ),
                CapabilityParameter(
                    name="ports",
                    description="Port range to scan (e.g., '1-1000', '22,80,443')",
                    param_type="string",
                    required=False,
                    default="1-1000",
                ),
                CapabilityParameter(
                    name="scan_type",
                    description="Scan type: quick, full, stealth",
                    param_type="string",
                    required=False,
                    default="quick",
                ),
            ],
            dangerous=False,
            requires_approval=True,
            category="reconnaissance",
        )

        # DNS lookup capability
        self.register_capability(
            name="dns_lookup",
            description="Perform DNS lookup on a domain",
            handler=self._dns_lookup,
            parameters=[
                CapabilityParameter(
                    name="domain",
                    description="Domain name to lookup",
                    param_type="string",
                    required=True,
                ),
                CapabilityParameter(
                    name="record_type",
                    description="DNS record type (A, AAAA, MX, NS, TXT)",
                    param_type="string",
                    required=False,
                    default="A",
                ),
            ],
            dangerous=False,
            requires_approval=False,
            category="reconnaissance",
        )

        # WHOIS lookup capability
        self.register_capability(
            name="whois_lookup",
            description="Perform WHOIS lookup on a domain or IP",
            handler=self._whois_lookup,
            parameters=[
                CapabilityParameter(
                    name="target",
                    description="Domain or IP address",
                    param_type="string",
                    required=True,
                ),
            ],
            dangerous=False,
            requires_approval=False,
            category="reconnaissance",
        )

    def recon_scan(self, target: str) -> dict[str, str]:
        """Example manifest-declared plugin tool executor."""
        return {"status": "ok", "target": target}

    def _port_scan(
        self,
        target: str,
        ports: str = "1-1000",
        scan_type: str = "quick",
    ) -> dict:
        """Generate nmap command for port scanning."""
        # Build nmap command based on scan type
        scan_flags = {
            "quick": "-T4 -F",
            "full": "-T4 -p- -sV",
            "stealth": "-sS -T2",
        }
        
        flags = scan_flags.get(scan_type, scan_flags["quick"])
        
        if scan_type != "full":
            flags += f" -p {ports}"
        
        command = f"nmap {flags} {target}"
        
        return {
            "type": "command_suggestion",
            "command": command,
            "description": f"{scan_type.capitalize()} port scan on {target}",
            "requires_approval": True,
        }

    def _dns_lookup(self, domain: str, record_type: str = "A") -> dict:
        """Generate dig command for DNS lookup."""
        command = f"dig +short {domain} {record_type.upper()}"
        
        return {
            "type": "command_suggestion",
            "command": command,
            "description": f"DNS {record_type.upper()} lookup for {domain}",
            "requires_approval": False,
        }

    def _whois_lookup(self, target: str) -> dict:
        """Generate whois command."""
        command = f"whois {target}"
        
        return {
            "type": "command_suggestion",
            "command": command,
            "description": f"WHOIS lookup for {target}",
            "requires_approval": False,
        }


# For direct instantiation
Plugin = ReconPlugin
