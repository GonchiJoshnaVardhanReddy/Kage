# Kage

AI-powered penetration testing CLI assistant for authorized security assessments.

## Quick Start

```bash
# 1. Install Kage
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage && pip install -e .

# 2. Make sure Ollama is running (or LM Studio)
ollama serve                    # In another terminal
ollama pull <model-name>        # Download any compatible model

# 3. Launch!
kage launch
```

That's it! Kage will auto-detect Ollama, find your models, and start chatting.

---

## 🚀 Installation

### One-Command Install

**Linux/macOS:**
```bash
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage
chmod +x scripts/install.sh
./scripts/install.sh
```

**Windows (PowerShell as Administrator):**
```powershell
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\install.ps1
```

After installation, **restart your terminal** and type `kage` to start!

### Using Make

```bash
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage

make setup        # Full install
make setup-dev    # Install with dev dependencies
make uninstall    # Uninstall
```

### Manual Install

```bash
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage
pip install -e .
```

### Install on Kali/Ubuntu (Externally-Managed Environment)

Modern Kali and Ubuntu systems use PEP 668 which prevents `pip install` system-wide.
Use a virtual environment instead:

```bash
git clone https://github.com/GonchiJoshnaVardhanReddy/kage.git
cd kage

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Kage
pip install -e .

# Run Kage (venv must be active)
kage
```

> **Tip:** Add `source ~/kage/.venv/bin/activate` to your `~/.bashrc` or `~/.zshrc` so Kage is always available.

Alternatively, use **pipx** for automatic venv management:

```bash
sudo apt install pipx
pipx install -e ./kage
```

### Verify Installation

```bash
kage --version
kage --help
```

### Supported Platforms

| Platform | Python | Status |
|----------|--------|--------|
| **Kali Linux** | 3.10–3.14 | ✅ Tested (use venv) python3 -m venv venv, source venv/bin/activate |
| **Ubuntu/Debian** | 3.10–3.14 | ✅ Tested |
| **Parrot OS** | 3.10–3.14 | ✅ Tested |
| **Arch Linux** | 3.10–3.14 | ✅ Compatible |
| **Fedora/RHEL** | 3.10–3.14 | ✅ Compatible |
| **macOS** | 3.10–3.14 | ✅ Compatible |
| **Windows** | 3.10–3.14 | ✅ Compatible (PowerShell) |
| **WSL** | 3.10–3.14 | ✅ Compatible |

> **Note:** On Kali and newer Ubuntu/Debian, use a virtual environment (`python3 -m venv .venv`) due to PEP 668.

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

### Option 1: Ollama - FREE & Local

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
# Pull any model available in your Ollama library
ollama pull <model-name>

# List downloaded models
ollama list
```

#### Step 4: Configure Kage

**Quick Launch:**
```bash
# Auto-detect and start immediately
kage launch

# This will:
# ✓ Connect to Ollama
# ✓ List your models
# ✓ Pick the first one
# ✓ Start chatting
```

**Or use Setup Wizard:**
```bash
kage setup
kage chat
```

## Core Commands

- `kage chat` — interactive session
- `kage hack` — autonomous hack mode
- `kage report generate` — export report from a session
- `kage session list` — list saved sessions

## Notes

- Kage executes security tooling locally through its local execution engine.
- Use only with explicit authorization.
