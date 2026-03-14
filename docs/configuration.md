# Kage Configuration Guide

Kage stores configuration in `~/.kage/config.yaml`.

## Default Structure

```yaml
llm:
  provider: ollama
  model: llama3.1
  base_url: http://localhost:11434
  api_key: null
  temperature: 0.7
  max_tokens: 4096

security:
  safe_mode: true
  require_approval: true
  audit_enabled: true
  scope_enforcement: true

session:
  auto_save: true
  save_interval: 60

chat:
  slash_suggestion_boosts:
    pending_commands: 60
    pending_run: 55
    pending_save: 10
    findings: 45
    findings_export: 35
    status: 40
    scope_hint: 10
```

## Useful Commands

- `kage setup` – interactive setup
- `kage config --show` – print active config
- `kage config --edit` – edit config file
- `kage config --reset` – reset defaults
