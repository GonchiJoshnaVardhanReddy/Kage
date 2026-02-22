# Troubleshooting Guide

## Common Issues and Solutions

### LLM Connection Issues

#### "Could not connect to Ollama"

**Problem:** Kage can't connect to Ollama server.

**Solutions:**

1. **Check if Ollama is running:**
   ```bash
   # Check if Ollama service is active
   curl http://localhost:11434/api/tags
   
   # If not, start it:
   ollama serve
   ```

2. **Check firewall settings:**
   - Windows: Allow Ollama through Windows Firewall
   - Linux: `sudo ufw allow 11434`

3. **Verify port is not in use:**
   ```bash
   # Linux/macOS
   lsof -i :11434
   
   # Windows
   netstat -ano | findstr 11434
   ```

---

#### "Could not connect to LM Studio"

**Problem:** LM Studio server not responding.

**Solutions:**

1. **Start the local server:**
   - Open LM Studio
   - Go to **Local Server** tab (↔ icon)
   - Click **Start Server**
   - Ensure it shows "Running" status

2. **Check the port:**
   - Default is `http://localhost:1234/v1`
   - If you changed it, update Kage config accordingly

3. **Load a model first:**
   - You must have a model loaded before starting the server
   - Go to **Chat** tab and load a model

---

#### "OpenAI API key invalid"

**Problem:** Authentication error with OpenAI.

**Solutions:**

1. **Check your API key:**
   - Go to https://platform.openai.com/api-keys
   - Create a new key if needed
   - Keys start with `sk-`

2. **Check for billing issues:**
   - OpenAI requires a payment method
   - Go to https://platform.openai.com/account/billing

3. **Use environment variable (more secure):**
   ```bash
   export OPENAI_API_KEY="sk-your-key-here"
   ```

---

### Installation Issues

#### "kage: command not found"

**Problem:** After installation, `kage` command doesn't work.

**Solutions:**

1. **Restart your terminal:**
   - Close and reopen your terminal window
   - Or run: `source ~/.bashrc` (Linux) / `source ~/.zshrc` (macOS)

2. **Check PATH:**
   ```bash
   # Check if kage is in PATH
   which kage
   
   # Add to PATH manually (Linux/macOS)
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. **Windows users:**
   - Restart PowerShell as Administrator
   - Or run: `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","User")`

---

#### "Python 3.10+ required"

**Problem:** Python version too old.

**Solutions:**

1. **Install Python 3.10+:**
   - Download from https://python.org/downloads/
   - Or use pyenv: `pyenv install 3.11.0`

2. **Check version:**
   ```bash
   python --version
   python3 --version
   ```

---

### Runtime Issues

#### "Safe mode blocked command"

**Problem:** Kage refuses to run your command.

**Solutions:**

1. **Check if command is dangerous:**
   - Safe mode blocks commands like `rm -rf /`, fork bombs, etc.
   - This is intentional for safety

2. **Disable safe mode (use with caution):**
   ```bash
   kage chat --unsafe
   # Or in chat: /safe
   ```

---

#### "Target out of scope"

**Problem:** Kage won't run commands against a target.

**Solutions:**

1. **Add target to scope:**
   ```bash
   kage chat --scope 10.10.10.0/24
   ```

2. **Disable scope enforcement (testing only):**
   ```yaml
   # In config.yaml
   security:
     scope_enforcement: false
   ```

---

### Performance Issues

#### "LLM responses are slow"

**Solutions:**

1. **Use a smaller model:**
   - `llama3.1` instead of `llama3.1:70b`
   - Smaller models = faster responses

2. **Check system resources:**
   - LLMs need significant RAM
   - 7B models: ~8GB RAM
   - 13B models: ~16GB RAM
   - 70B models: ~48GB RAM

3. **Use GPU acceleration:**
   - Ollama automatically uses GPU if available
   - Ensure CUDA/ROCm drivers are installed

---

## Getting Help

If you're still having issues:

1. **Check the logs:**
   ```bash
   # Kage logs location
   ~/.local/share/kage/logs/
   ```

2. **Run with debug mode:**
   ```bash
   KAGE_DEBUG=1 kage chat
   ```

3. **Open an issue:**
   - Go to: https://github.com/yourusername/kage/issues
   - Include:
     - Your OS and version
     - Python version
     - LLM provider and model
     - Full error message
     - Steps to reproduce
