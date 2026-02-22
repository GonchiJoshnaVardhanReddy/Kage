<p align="center">
  <img src="docs/images/kage-logo.png" alt="Kage Logo" width="200"/>
</p>

<h1 align="center">Kage</h1>

<p align="center">
  <strong>AI-powered penetration testing CLI assistant</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#llm-setup">LLM Setup</a> •
  <a href="#usage">Usage</a> •
  <a href="#hack-mode">Hack Mode</a> •
  <a href="#configuration">Configuration</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"/>
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey.svg" alt="Platform"/>
</p>

---

Kage (影 - "shadow" in Japanese) is a terminal-based AI assistant for **bug bounty hunters**, **penetration testers**, **CTF players**, and **red teamers**. It helps discover vulnerabilities, analyze tool outputs, guide exploitation in authorized environments, and generate professional security reports.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **Multi-LLM Support** | Ollama, LM Studio, OpenAI, and any OpenAI-compatible API |
| 💬 **Interactive CLI** | Clean terminal interface with Rich formatting |
| 🔥 **Hack Mode** | Fully autonomous penetration testing |
| 🛡️ **Safe Mode** | Blocks dangerous commands (rm -rf, fork bombs, etc.) |
| 🎯 **Scope Enforcement** | Prevents accidental out-of-scope testing |
| ⚡ **Tool Execution** | Run security tools with approval workflow |
| 📝 **Session Management** | Save, resume, and replay testing sessions |
| 📊 **Report Generation** | Professional reports in Markdown, HTML, or PDF |
| 🔌 **Plugin System** | Extend capabilities with custom plugins |
| 🔗 **MCP Integration** | Connect to Model Context Protocol servers |

## 📋 Table of Contents

- [Installation](#-installation)
- [LLM Setup Guide](#-llm-setup-guide)
  - [Option 1: Ollama (Recommended)](#option-1-ollama-recommended-free--local)
  - [Option 2: LM Studio](#option-2-lm-studio-free--local)
  - [Option 3: OpenAI API](#option-3-openai-api-paid--cloud)
  - [Option 4: Other APIs](#option-4-other-apis)
- [Usage](#-usage)
- [Hack Mode](#-hack-mode)
- [Chat Commands](#-chat-commands)
- [Configuration](#-configuration)
- [Security Tools](#-recommended-security-tools)
- [License](#-license)

---

## 🚀 Installation

### One-Command Install (Recommended)

**Linux/macOS:**
```bash
git clone https://github.com/yourusername/kage.git
cd kage
chmod +x scripts/install.sh
./scripts/install.sh
```

**Windows (PowerShell as Administrator):**
```powershell
git clone https://github.com/yourusername/kage.git
cd kage
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\install.ps1
```

After installation, **restart your terminal** and type `kage` to start!

### Using Make

```bash
git clone https://github.com/yourusername/kage.git
cd kage

make setup        # Full install
make setup-dev    # Install with dev dependencies
make uninstall    # Uninstall
```

### Manual Install

```bash
git clone https://github.com/yourusername/kage.git
cd kage
pip install -e .
```

### Verify Installation

```bash
kage --version
kage --help
```

---

## 🧠 LLM Setup Guide

Kage needs a Large Language Model (LLM) to work. You have several options:

### How LLM Connections Work

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   ┌────────┐     HTTP Request      ┌─────────────────────┐     │
│   │  Kage  │ ───────────────────► │    LLM Server        │     │
│   │        │ ◄─────────────────── │  (Ollama/LM Studio)  │     │
│   └────────┘     AI Response       └─────────────────────┘     │
│                                                                 │
│   URL: http://localhost:11434                                   │
│         ▲         ▲       ▲                                     │
│         │         │       │                                     │
│      Protocol   Host    Port                                    │
│      (http)   (local)  (door number)                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Term | Meaning |
|------|---------|
| `localhost` | Your own computer |
| `127.0.0.1` | Same as localhost (IP address) |
| Port (`:11434`) | Like a door number - different services use different ports |
| `/v1` | API version path |

---

### Option 1: Ollama (Recommended) - FREE & Local

Ollama is the easiest way to run LLMs locally. Your data stays on your machine.

#### Step 1: Install Ollama

**Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**macOS:**
```bash
brew install ollama
# Or download from: https://ollama.com/download/mac
```

**Windows:**
Download installer from: https://ollama.com/download/windows

#### Step 2: Start Ollama Server

```bash
# Start the Ollama service
ollama serve
```

This starts the server at `http://localhost:11434`

#### Step 3: Download a Model

```bash
# Recommended models for security work:
ollama pull llama3.1        # Good balance of speed and quality
ollama pull llama3.1:70b    # Better quality (needs 48GB+ RAM)
ollama pull codellama       # Specialized for code
ollama pull mixtral         # Good for complex reasoning

# List downloaded models
ollama list
```

#### Step 4: Configure Kage

```bash
kage setup
# Select "Ollama" when prompted
# Or manually edit ~/.config/kage/config.yaml:
```

```yaml
llm:
  provider: ollama
  model: llama3.1
  base_url: http://localhost:11434
```

#### Step 5: Test Connection

```bash
# Test Ollama is working
curl http://localhost:11434/api/tags

# Start Kage
kage chat
```

---

### Option 2: LM Studio - FREE & Local

LM Studio provides a GUI for running local LLMs with an OpenAI-compatible API.

#### Step 1: Install LM Studio

Download from: https://lmstudio.ai/

Available for Windows, macOS, and Linux.

#### Step 2: Download a Model

1. Open LM Studio
2. Go to the **Search** tab (magnifying glass icon)
3. Search for models like:
   - `TheBloke/Llama-2-13B-chat-GGUF`
   - `TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF`
   - `TheBloke/CodeLlama-13B-Instruct-GGUF`
4. Click **Download**

#### Step 3: Start the Local Server

1. Go to the **Local Server** tab (↔ icon)
2. Select your downloaded model from the dropdown
3. Click **Start Server**
4. Note the URL shown (default: `http://localhost:1234/v1`)

```
┌─────────────────────────────────────────────────────┐
│  LM Studio - Local Server                           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Server Status: ● Running                           │
│  URL: http://localhost:1234/v1                      │
│                                                     │
│  Model: TheBloke/Llama-2-13B-chat-GGUF             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### Step 4: Configure Kage

In Kage chat, type `/model` or edit config:

```yaml
llm:
  provider: lmstudio
  model: local-model          # LM Studio ignores this, uses loaded model
  base_url: http://localhost:1234/v1
```

#### Step 5: Test Connection

```bash
# Test LM Studio API
curl http://localhost:1234/v1/models

# Start Kage
kage chat
```

---

### Option 3: OpenAI API - Paid & Cloud

Use OpenAI's GPT models (GPT-4, GPT-3.5-turbo).

#### Step 1: Get API Key

1. Go to https://platform.openai.com/
2. Sign up or log in
3. Go to **API Keys** section
4. Click **Create new secret key**
5. Copy the key (starts with `sk-...`)

#### Step 2: Configure Kage

```bash
kage setup
# Select "OpenAI" and enter your API key
```

Or edit config manually:

```yaml
llm:
  provider: openai
  model: gpt-4                    # or gpt-3.5-turbo (cheaper)
  base_url: https://api.openai.com/v1
  api_key: sk-your-api-key-here   # Keep this secret!
```

#### Step 3: Set via Environment (More Secure)

```bash
# Linux/macOS
export OPENAI_API_KEY="sk-your-api-key-here"

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-your-api-key-here"

# Then in config.yaml, omit api_key - Kage will use environment variable
```

#### Pricing Note

OpenAI charges per token. Approximate costs:
- GPT-3.5-turbo: ~$0.002 per 1K tokens
- GPT-4: ~$0.03 per 1K tokens
- GPT-4-turbo: ~$0.01 per 1K tokens

---

### Option 4: Other APIs

Kage works with any OpenAI-compatible API:

#### Anthropic Claude (via proxy)

```yaml
llm:
  provider: anthropic
  model: claude-3-sonnet
  base_url: https://api.anthropic.com/v1
  api_key: your-anthropic-key
```

#### Groq (Fast & Free tier available)

```yaml
llm:
  provider: groq
  model: llama3-70b-8192
  base_url: https://api.groq.com/openai/v1
  api_key: your-groq-key
```

#### Together AI

```yaml
llm:
  provider: together
  model: meta-llama/Llama-3-70b-chat-hf
  base_url: https://api.together.xyz/v1
  api_key: your-together-key
```

#### Local AI (Self-hosted)

```yaml
llm:
  provider: localai
  model: gpt-3.5-turbo
  base_url: http://localhost:8080/v1
```

---

## 💻 Usage

### First-Time Setup

```bash
kage setup
```

This wizard helps you:
- Choose your LLM provider
- Configure API keys
- Set security preferences

### Start Interactive Session

```bash
# Basic chat
kage chat

# With target scope
kage chat --scope 10.10.10.0/24

# With specific provider
kage chat --provider ollama --model llama3.1

# Resume previous session
kage session resume abc123
```

### Example Session

```
kage> Scan 10.10.10.1 for open ports

KAGE: I'll help you scan for open ports. Here's the command:

  $ nmap -sV -sC 10.10.10.1

  This performs a service version scan with default scripts.

1 command(s) suggested. Use /commands to view, /run to execute.

kage> /run
$ nmap -sV -sC 10.10.10.1
Running...
PORT   STATE SERVICE VERSION
22/tcp open  ssh     OpenSSH 8.2
80/tcp open  http    Apache 2.4.41
Completed (exit: 0)

kage> What vulnerabilities should I check for Apache 2.4.41?
```

---

## 🔥 Hack Mode

Fully autonomous penetration testing - Kage plans, executes, and reports automatically.

### Launch Hack Mode

```bash
# From command line
kage hack 10.10.10.1

# With additional scope
kage hack example.com --scope api.example.com

# Skip warning (authorized testing only!)
kage hack 192.168.1.1 -y

# From chat
kage> /hacker
```

### Hack Mode Phases

```
┌─────────────────────────────────────────────────────────────┐
│                    HACK MODE WORKFLOW                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. PLANNING      AI creates attack strategy                │
│         ↓                                                   │
│  2. RECON         Port scanning, DNS enum, OSINT           │
│         ↓                                                   │
│  3. ENUMERATION   Service fingerprinting, vuln scanning    │
│         ↓                                                   │
│  4. EXPLOITATION  Test & exploit discovered vulns          │
│         ↓                                                   │
│  5. REPORTING     Generate detailed pentest report         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Output

Hack mode generates:
- Detailed HTML/PDF report
- List of all commands executed
- Discovered vulnerabilities with severity ratings
- Remediation recommendations

⚠️ **WARNING**: Hack mode disables safety restrictions. Only use on systems you have **written authorization** to test!

---

## 📝 Chat Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/exit` | End session |
| `/clear` | Clear screen |
| `/model` | Change LLM provider/model |
| `/hacker` | Enter autonomous hack mode |
| `/scope` | Show current target scope |
| `/safe` | Toggle safe mode on/off |
| `/findings` | List discovered vulnerabilities |
| `/history` | Show command history |
| `/status` | Show session status |
| `/commands` | Show pending commands |
| `/run` | Execute pending commands |
| `/save` | Save current session |
| `/export [path]` | Export session to file |

---

## ⚙️ Configuration

Configuration file: `~/.config/kage/config.yaml`

```yaml
# LLM Provider Settings
llm:
  provider: ollama              # ollama, lmstudio, openai, or custom
  model: llama3.1               # Model name
  base_url: http://localhost:11434
  api_key: null                 # Required for OpenAI/cloud providers
  temperature: 0.7              # Creativity (0.0 - 1.0)
  max_tokens: 4096              # Max response length

# Security Settings
security:
  safe_mode: true               # Block dangerous commands
  require_approval: true        # Ask before running commands
  scope_enforcement: true       # Prevent out-of-scope testing

# Session Settings
session:
  auto_save: true
  save_interval: 60
  directory: ~/.local/share/kage/sessions

# MCP Server Settings
mcp:
  enabled: true
  auto_discover: true
  docker_enabled: true
  servers: []

# Hack Mode Settings
hack_mode:
  enabled: true
  auto_report: true
  report_format: html           # markdown, html, or pdf
```

---

## 🔧 Recommended Security Tools

Kage works best with these tools installed:

| Category | Tools |
|----------|-------|
| **Reconnaissance** | `nmap`, `masscan`, `whois`, `dig` |
| **Web Enumeration** | `gobuster`, `ffuf`, `nikto`, `dirb` |
| **Vulnerability Scanning** | `nuclei`, `nmap --script=vuln` |
| **Exploitation** | `sqlmap`, `searchsploit`, `metasploit` |
| **Password Attacks** | `hydra`, `john`, `hashcat` |
| **Network** | `curl`, `wget`, `nc`, `socat` |

### Install on Kali/Parrot Linux

Most tools come pre-installed. For others:

```bash
sudo apt update
sudo apt install nmap gobuster nikto sqlmap hydra
```

### Install on Ubuntu/Debian

```bash
sudo apt install nmap nikto hydra
go install github.com/OJ/gobuster/v3@latest
go install github.com/ffuf/ffuf/v2@latest
pip install sqlmap
```

---

## 📁 Project Structure

```
kage/
├── src/kage/
│   ├── ai/              # LLM providers (Ollama, OpenAI, etc.)
│   ├── cli/             # CLI commands and UI
│   ├── core/            # Core models, hack mode engine
│   ├── executor/        # Command execution
│   ├── mcp/             # MCP protocol integration
│   ├── persistence/     # Config and session storage
│   ├── plugins/         # Plugin system
│   ├── reporting/       # Report generation
│   └── security/        # Safe mode, scope validation
├── scripts/             # Installation scripts
├── templates/           # Report templates
├── tests/               # Test suite
└── docs/                # Documentation
```

---

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines first.

```bash
# Clone and install dev dependencies
git clone https://github.com/yourusername/kage.git
cd kage
make setup-dev

# Run tests
make test

# Run linter
make lint
```

---

## 📜 License

MIT License - see [LICENSE](LICENSE) for details.

---

## ⚠️ Disclaimer

**This tool is intended for authorized security testing only.**

- Always obtain written permission before testing any system
- Only test systems you own or have explicit authorization to test
- Unauthorized access to computer systems is illegal
- The developers are not responsible for misuse of this tool

**Use responsibly. Hack ethically.**

---

<p align="center">
  <strong>Made with ❤️ for the security community</strong>
</p>
