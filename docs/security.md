# Kage Security Guide

This document details the security features and best practices for using Kage.

## Security Philosophy

Kage is designed with defense-in-depth, providing multiple layers of protection:

1. **Scope Enforcement** - Prevent out-of-scope testing
2. **Safe Mode** - Block dangerous commands
3. **User Approval** - Human review before execution
4. **Audit Logging** - Tamper-evident activity logging

## Scope Enforcement

### Defining Scope

```bash
# Start session with scope
kage chat --scope 192.168.1.0/24

# Multiple targets
kage chat --scope 192.168.1.0/24,example.com
```

### Scope Configuration

```yaml
# In session or via CLI
scope:
  targets:
    - type: cidr
      value: 192.168.1.0/24
    - type: domain
      value: example.com
      include_subdomains: true
    - type: ip
      value: 10.0.0.1
  excluded:
    - 192.168.1.1       # Gateway
    - admin.example.com  # Admin panel
```

### Scope Validation

All commands are checked for:
- IP addresses and CIDR ranges
- Domain names and URLs
- Hostnames

Commands targeting out-of-scope systems are **blocked**.

## Safe Mode

Safe mode blocks dangerous command patterns.

### Blocked Commands

| Pattern | Reason |
|---------|--------|
| `rm -rf /` | Filesystem destruction |
| `rm -rf /*` | Filesystem destruction |
| `dd if=* of=/dev/*` | Disk destruction |
| `mkfs.*` | Filesystem formatting |
| `:(){ :\|:& };:` | Fork bomb |
| `> /etc/passwd` | System file overwrite |
| `chmod -R 777 /` | Permission destruction |

### Blocked Flags

- `-rf` with paths containing `/` or `*`
- `--no-preserve-root`
- `-delete` with broad paths

### Warnings (Not Blocked)

- Reverse shell patterns
- Data exfiltration commands
- Privilege escalation attempts

### Disabling Safe Mode

```bash
# CLI flag (use with extreme caution!)
kage chat --unsafe

# Per-session
# Type: /unsafe to toggle
```

⚠️ **Warning**: Only disable safe mode when absolutely necessary and you fully understand the risks.

## User Approval Workflow

When a command is proposed:

```
┌──────────────────────────────────────────────────┐
│ 🔧 Proposed Command                              │
├──────────────────────────────────────────────────┤
│ nmap -sV -sC 192.168.1.0/24                     │
│                                                  │
│ Description: Port scan with version detection    │
│ Target: 192.168.1.0/24 ✓ (in scope)             │
│ Risk: Low                                        │
├──────────────────────────────────────────────────┤
│ [A]pprove  [R]eject  [E]dit  [?]Explain         │
└──────────────────────────────────────────────────┘
```

### Options

- **Approve (a)**: Execute the command
- **Reject (r)**: Skip the command
- **Edit (e)**: Modify before execution
- **Explain (?)**: Ask AI for more details

## Audit Logging

### Log Structure

```json
{
  "id": "uuid",
  "timestamp": "2024-01-15T10:30:00Z",
  "session_id": "session-uuid",
  "action": "command_executed",
  "details": {
    "command": "nmap -sV target",
    "exit_code": 0,
    "approved_by": "user"
  },
  "previous_hash": "sha256...",
  "entry_hash": "sha256..."
}
```

### Hash Chain

Each entry contains:
- Hash of the previous entry
- Hash of the current entry's content

This creates a tamper-evident chain. Modifications to any entry break the chain.

### Verifying Audit Logs

```bash
# Verify audit log integrity
kage audit verify

# Export audit log
kage audit export --format json -o audit.json
```

## Plugin Sandboxing

Plugins run in a restricted environment:

### Import Restrictions

**Allowed:**
- Standard library (json, re, datetime, etc.)
- Network parsing (ipaddress, urllib.parse)
- Data structures (collections, itertools)

**Blocked:**
- subprocess, os.system
- socket (direct)
- importlib
- builtins (eval, exec, compile)

### Capability Permissions

```yaml
capabilities:
  - name: scan
    dangerous: true  # Requires approval
    permissions:
      - network        # Can make network requests
      - filesystem_read  # Can read files
```

## Credential Handling

### Best Practices

1. **Never store credentials in sessions**
2. **Use environment variables for API keys**
3. **Credentials are scrubbed from audit logs**

### Environment Variables

```bash
export OPENAI_API_KEY=sk-...
export KAGE_API_KEY=...  # For remote services
```

### Credential Scrubbing

The following patterns are automatically scrubbed from logs:
- API keys (`sk-*`, `api-*`)
- Passwords in URLs
- Authorization headers
- Private keys

## Network Security

### Preventing Exfiltration

Kage warns about patterns that could exfiltrate data:

- `nc -e` (netcat with execute)
- `bash -i >& /dev/tcp/`
- `curl/wget` to non-scope URLs
- Base64-encoded command execution

### Proxy Support

```yaml
network:
  proxy: http://proxy:8080
  verify_ssl: true
```

## Incident Response

### If Scope is Breached

1. **Stop immediately**: Press Ctrl+C
2. **Review audit log**: `kage audit export`
3. **Document incident**: Include session ID, timestamps
4. **Contact appropriate parties**: System owners, legal

### Session Forensics

```bash
# Export session for review
kage session export <id> -o incident_session.json

# Export audit log
kage audit export --session <id> -o incident_audit.json
```

## Security Checklist

Before starting an engagement:

- [ ] Verify written authorization
- [ ] Define precise scope boundaries
- [ ] Enable safe mode
- [ ] Enable audit logging
- [ ] Test scope enforcement
- [ ] Review blocked command list
- [ ] Configure excluded targets
- [ ] Set up secure LLM provider

## Reporting Security Issues

Found a security vulnerability in Kage?

1. **Do not** open a public issue
2. Email security details to: security@kage-security.org
3. Include: Description, reproduction steps, impact assessment
4. Allow 90 days for fix before disclosure

## Legal Disclaimer

Kage is intended for **authorized security testing only**. Users are responsible for:

- Obtaining proper written authorization
- Ensuring compliance with applicable laws
- Limiting testing to defined scope
- Reporting findings responsibly

Unauthorized access to computer systems is **illegal**. The Kage team assumes no liability for misuse.
