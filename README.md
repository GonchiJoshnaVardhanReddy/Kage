# Kage

**AI-powered penetration testing CLI assistant**

Kage is a terminal-based AI assistant for bug bounty hunters, penetration testers, CTF players, and red teamers. It helps discover vulnerabilities, analyze tool outputs, guide exploitation in authorized environments, and generate professional security reports.

## Features

- **Interactive CLI** - Clean, structured terminal interface
- **Multi-LLM Support** - Ollama, OpenAI, LM Studio, and OpenAI-compatible APIs
- **Tool Execution** - Execute security tools with approval workflow
- **Safe Mode** - Optional restriction mode for dangerous operations
- **Scope Enforcement** - Prevent accidental out-of-scope testing
- **Session Management** - Persist and replay sessions
- **Plugin System** - Extend capabilities with custom plugins
- **Report Generation** - Professional reports in MD/HTML/PDF

## Installation

```bash
# From PyPI (when published)
pip install kage

# From source
git clone https://github.com/kage-security/kage.git
cd kage
pip install -e .
```

## Quick Start

```bash
# First-time setup
kage setup

# Start interactive session
kage chat

# Start session with target scope
kage chat --scope 10.10.10.0/24

# Resume previous session
kage session resume <session-id>

# Generate report
kage report generate --format html
```

## Configuration

Configuration file location: `~/.config/kage/config.yaml`

```yaml
llm:
  provider: ollama
  model: llama3.1
  base_url: http://localhost:11434

security:
  safe_mode: true
  require_approval: true

session:
  auto_save: true
  directory: ~/.local/share/kage/sessions
```

## Requirements

- Python 3.10+
- Linux (primary), Windows/WSL (supported)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Disclaimer

This tool is intended for authorized security testing only. Users are responsible for ensuring they have proper authorization before testing any systems. Unauthorized access to computer systems is illegal.
