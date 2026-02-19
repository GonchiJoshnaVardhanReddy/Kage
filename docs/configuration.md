# Kage Configuration Guide

This document explains how to configure Kage for your environment.

## Configuration File

Kage stores its configuration in `~/.config/kage/config.yaml`.

### Default Configuration

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

session:
  auto_save: true
  save_interval: 60

ui:
  theme: dark
  show_timestamps: true
```

## LLM Providers

### Ollama (Default)

```yaml
llm:
  provider: ollama
  model: llama3.1
  base_url: http://localhost:11434
```

Ollama runs locally and is the recommended provider for privacy. Install from [ollama.ai](https://ollama.ai).

### OpenAI

```yaml
llm:
  provider: openai
  model: gpt-4
  api_key: sk-your-api-key-here
```

Set your API key via environment variable:
```bash
export OPENAI_API_KEY=sk-your-api-key
```

### LM Studio

```yaml
llm:
  provider: lmstudio
  model: local-model
  base_url: http://localhost:1234/v1
```

### OpenAI-Compatible APIs

```yaml
llm:
  provider: openai_compat
  model: your-model
  base_url: https://api.provider.com/v1
  api_key: your-api-key
```

## Security Settings

### Safe Mode

Safe mode blocks dangerous commands:

```yaml
security:
  safe_mode: true
```

Blocked patterns include:
- `rm -rf /` and variants
- `dd` to disk devices
- Format commands
- Fork bombs
- Privilege escalation attempts

### Approval Workflow

Require user approval for all commands:

```yaml
security:
  require_approval: true
```

### Audit Logging

Enable tamper-evident audit logs:

```yaml
security:
  audit_enabled: true
```

Logs are stored in `~/.local/share/kage/audit/`.

## Session Settings

### Auto-Save

```yaml
session:
  auto_save: true
  save_interval: 60  # seconds
```

Sessions are stored in `~/.local/share/kage/sessions/`.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `KAGE_CONFIG` | Custom config file path |
| `OPENAI_API_KEY` | OpenAI API key |
| `OLLAMA_HOST` | Ollama server URL |
| `KAGE_SAFE_MODE` | Override safe mode (true/false) |

## CLI Overrides

Configuration can be overridden via CLI flags:

```bash
# Use specific provider
kage chat --provider openai --model gpt-4

# Disable safe mode (use with caution!)
kage chat --unsafe

# Use specific session
kage chat --session abc123
```

## First-Time Setup

Run the setup wizard for interactive configuration:

```bash
kage setup
```

This will:
1. Detect available LLM providers
2. Test connectivity
3. Configure security settings
4. Save configuration

## Configuration Validation

View current configuration:

```bash
kage config --show
```

Reset to defaults:

```bash
kage config --reset
```
