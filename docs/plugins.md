# Kage Plugin Development Guide

This document explains how to create plugins for Kage.

## Plugin Structure

Plugins are stored in the `plugins/` directory:

```
plugins/
└── my_plugin/
    ├── plugin.yaml      # Plugin metadata
    └── my_plugin.py     # Plugin implementation
```

## Plugin Metadata (plugin.yaml)

```yaml
name: my_plugin
version: 1.0.0
description: A custom Kage plugin
author: Your Name

capabilities:
  - name: my_capability
    description: What this capability does
    parameters:
      target:
        type: string
        description: Target IP or domain
        required: true
      port:
        type: integer
        description: Port number
        required: false
        default: 80
    returns: string
    dangerous: false

required_tools:
  - nmap
  - curl

permissions:
  - network
  - filesystem_read
```

## Plugin Implementation

```python
"""My custom Kage plugin."""

from kage.plugins.base import KagePlugin, capability


class MyPlugin(KagePlugin):
    """Custom plugin for Kage."""

    @capability(
        name="my_capability",
        description="Performs a custom action",
        dangerous=False,
    )
    async def my_capability(self, target: str, port: int = 80) -> str:
        """Execute the capability.
        
        Args:
            target: Target IP or domain
            port: Port number (default: 80)
            
        Returns:
            Result string
        """
        # Use the provided executor for running commands
        result = await self.executor.run(f"curl -s http://{target}:{port}")
        
        return f"Result: {result.stdout}"

    @capability(
        name="analyze",
        description="Analyze results",
        dangerous=False,
    )
    def analyze(self, data: str) -> dict:
        """Analyze data synchronously."""
        return {"status": "analyzed", "data": data}
```

## Plugin Base Class

All plugins inherit from `KagePlugin`:

```python
class KagePlugin:
    """Base class for Kage plugins."""
    
    def __init__(self, context: PluginContext):
        self.context = context
        self.executor = context.executor
        self.session = context.session
        self.config = context.config
    
    async def initialize(self) -> None:
        """Called when plugin is loaded."""
        pass
    
    async def cleanup(self) -> None:
        """Called when plugin is unloaded."""
        pass
```

## Plugin Context

Plugins receive a context object with:

| Property | Description |
|----------|-------------|
| `executor` | Command executor for running tools |
| `session` | Current session data |
| `config` | Plugin configuration |
| `scope` | Current scope definition |
| `findings` | Findings manager |

## Capability Decorator

```python
from kage.plugins.base import capability

@capability(
    name="scan_ports",
    description="Scan ports on target",
    dangerous=True,  # Requires approval
    parameters={
        "target": {"type": "string", "required": True},
        "ports": {"type": "string", "default": "1-1000"},
    },
)
async def scan_ports(self, target: str, ports: str = "1-1000") -> dict:
    ...
```

## Security Sandbox

Plugins run in a restricted sandbox:

### Allowed Imports
- `json`, `re`, `datetime`, `typing`
- `ipaddress`, `urllib.parse`
- `collections`, `itertools`, `functools`

### Blocked Imports
- `subprocess`, `os.system`
- `socket` (direct access)
- `importlib`
- `eval`, `exec`

### Filesystem Access
- Read-only access to plugin directory
- No write access outside session data

## Example: Reconnaissance Plugin

```python
"""Reconnaissance plugin for Kage."""

from kage.plugins.base import KagePlugin, capability


class ReconPlugin(KagePlugin):
    """Reconnaissance capabilities."""

    @capability(
        name="port_scan",
        description="Scan ports using nmap",
        dangerous=True,
    )
    async def port_scan(self, target: str, options: str = "-sV") -> dict:
        """Run nmap port scan."""
        result = await self.executor.run(f"nmap {options} {target}")
        
        # Parse nmap output
        ports = self._parse_nmap(result.stdout)
        
        return {
            "target": target,
            "ports": ports,
            "raw_output": result.stdout,
        }

    @capability(
        name="dns_lookup",
        description="DNS lookup for domain",
        dangerous=False,
    )
    async def dns_lookup(self, domain: str) -> dict:
        """Perform DNS lookup."""
        result = await self.executor.run(f"dig +short {domain}")
        
        return {
            "domain": domain,
            "records": result.stdout.strip().split("\n"),
        }

    def _parse_nmap(self, output: str) -> list:
        """Parse nmap output for open ports."""
        ports = []
        for line in output.split("\n"):
            if "/tcp" in line and "open" in line:
                parts = line.split()
                ports.append({
                    "port": parts[0],
                    "state": parts[1],
                    "service": parts[2] if len(parts) > 2 else "unknown",
                })
        return ports
```

## Installing Plugins

```bash
# List available plugins
kage plugin list

# Install from directory
kage plugin install ./my_plugin

# Enable/disable plugins
kage plugin enable my_plugin
kage plugin disable my_plugin

# View plugin info
kage plugin info my_plugin
```

## Plugin Lifecycle

1. **Discovery**: Plugin manager scans `plugins/` directory
2. **Validation**: `plugin.yaml` is validated
3. **Loading**: Plugin module is imported in sandbox
4. **Initialization**: `initialize()` method called
5. **Registration**: Capabilities registered with AI
6. **Execution**: Capabilities called during chat
7. **Cleanup**: `cleanup()` called on exit

## Best Practices

1. **Validate all inputs** - Never trust user/AI input
2. **Handle errors gracefully** - Return meaningful error messages
3. **Log important actions** - Use the context logger
4. **Respect scope** - Only operate on in-scope targets
5. **Mark dangerous capabilities** - Set `dangerous=True` appropriately
6. **Document thoroughly** - Help users understand capabilities
