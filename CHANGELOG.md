# Changelog

All notable changes to Kage will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.2.0] - 2026-03-07

### 🔒 Security Fixes

- **Shell injection prevention** — Executor now uses explicit shell invocation (`['/bin/bash', '-c', cmd]`) with `shell=False` instead of `shell=True`. PowerShell uses `-EncodedCommand` with base64-encoded UTF-16LE to prevent quote escaping attacks.
- **Safe mode DANGEROUS bypass fixed** — Commands classified as `DANGEROUS` now always require user confirmation, even when `require_approval=False`. Previously, disabling approval would auto-approve dangerous commands.
- **Scope DNS resolution** — Domain scope validation now resolves DNS to check if resolved IPs fall within scoped CIDRs, preventing bypass via domain names.
- **CIDR validation hardened** — Scope validation now checks the full network range using `subnet_of()` instead of only the base IP address.
- **Atomic session writes** — Session persistence uses temp file + `os.replace()` + `fsync()` to prevent data corruption on crash.
- **Audit hash determinism** — Audit log entries now use `json.dumps(sort_keys=True)` for deterministic hash computation, ensuring tamper detection works correctly.
- **Plugin sandbox enforcement** — Plugin manager now uses `PluginSandbox.load_module_from_file()` instead of standard `importlib`, enforcing the `RestrictedImporter` at runtime.
- **Dangerous capability enforcement** — Plugin capabilities marked as `dangerous=True` now require explicit user approval before execution.

### ✨ New Features

- **File operations** — New slash commands: `/read`, `/write`, `/edit`, `/create`, `/ls` for file manipulation directly from the chat interface.
- **Startup animation** — Animated ASCII art banner with glitch effect on launch, showing Kage identity and connected LLM info.
- **AI identity branding** — Kage introduces itself as "I am Kage" when asked, mentioning the connected LLM provider and model.
- **Tab completion** — Slash commands now support tab completion via readline (Linux/macOS).
- **Auto-reconnect** — Automatic LLM reconnection with 3 retries and exponential backoff on connection loss.
- **Session import** — New `/import <path>` command to load sessions from JSON files.
- **Finding deduplication** — `FindingsManager.deduplicate()` removes duplicate findings based on title + target + severity.
- **PDF report export** — `ReportEngine.render_pdf()` generates PDF reports via WeasyPrint (`pip install kage[pdf]`).
- **SSH executor** — Remote command execution over SSH with key/password authentication.
- **Docker executor** — Command execution inside Docker containers.
- **WSL executor** — Windows Subsystem for Linux command execution.
- **`@capability` decorator** — Simplified plugin capability registration with automatic discovery.

### 🔧 Improvements

- **Empty first chat fix** — Fixed bug where the first message always returned empty. Root cause: stale httpx `AsyncClient` across `asyncio.run()` event loops.
- **Python 3.10–3.14 support** — Replaced all `datetime.utcnow()` calls with timezone-aware utility function. Added Python 3.13/3.14 classifiers.
- **Structured error logging** — Replaced 10+ bare `except Exception: pass` patterns with `logger.debug/warning` calls across providers, persistence, and conversation modules.
- **Async config I/O** — Added `KageConfig.aload()` and `asave()` async methods using `asyncio.to_thread()`.
- **Config error logging** — YAML parse errors are now logged instead of silently falling back to defaults.
- **Audit logging for scope/safe-mode** — Scope changes and safe mode toggles are now recorded in the audit trail.
- **macOS readline compatibility** — Tab completion detects libedit (macOS) vs GNU readline and uses the correct key binding.
- **Kali/Ubuntu install guide** — README documents virtual environment setup for PEP 668 externally-managed environments.
- **Code cleanup** — Removed unused imports, ran ruff format/fix across all files.

### 🧪 Tests

- **75 new tests** — Total test count increased from 59 to 134, covering:
  - Security approval workflow (15 tests)
  - Plugin capabilities and sandbox (11 tests)
  - All executors including SSH/Docker/WSL (25 tests)
  - Persistence atomic writes and config loading (13 tests)
  - Finding deduplication and stats (11 tests)

---

## [0.1.0] - Initial Release

### Features

- Interactive chat with AI-powered penetration testing guidance
- Multi-LLM support (Ollama, OpenAI, LM Studio)
- Hack Mode — fully autonomous penetration testing
- Safe mode with dangerous command blocking
- Scope enforcement for authorized testing
- Command execution with approval workflow
- Session management (save/load/resume)
- Report generation (Markdown, HTML)
- Plugin system with sandboxed execution
- Audit logging with hash chain for tamper detection
