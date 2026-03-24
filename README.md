# Kage

AI-powered penetration testing CLI assistant and modular AI orchestration runtime.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![CLI](https://img.shields.io/badge/interface-CLI-7A52F4.svg)](#6-cli-usage-guide)
[![Local-first](https://img.shields.io/badge/runtime-local--first-2EA043.svg)](#1-project-overview)
[![MCP Ready](https://img.shields.io/badge/tools-MCP%20ready-0A7EA4.svg)](#9-tool-system)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](#20-license--contribution)
[![Lint: ruff](https://img.shields.io/badge/lint-ruff-46A35E.svg)](#20-license--contribution)
[![Types: mypy](https://img.shields.io/badge/types-mypy-2A6DB0.svg)](#20-license--contribution)
[![CI](https://github.com/GonchiJoshnaVardhanReddy/Kage/actions/workflows/ci.yml/badge.svg)](https://github.com/GonchiJoshnaVardhanReddy/Kage/actions/workflows/ci.yml)

> **Security Notice**  
> Kage is for authorized security testing only. You are responsible for legal scope, written permission, and safe operation.

---

## Operator Quick Reference

Install and launch:

```bash
.\scripts\install.ps1 -Dev
pip install -e ".[dev]"
kage launch
kage chat
```

Install and launch:
```bash
.\scripts\uninstall.ps1 -Yes
```
Provider quick config (`~/.kage/config.yaml`):

```yaml
llm:
  provider: ollama   # ollama | lmstudio | openai | custom
  model: llama3
  base_url: http://localhost:11434
```

High-value commands:

```bash
kage setup
kage session list
kage report generate --session <session_id> --format markdown
kage plugin list
```

In-chat essentials:

```text
/tools list
/workflows list
/trace last
/prompt inspect
/memory inspect
```

---

## Table of Contents

- [1) Project Overview](#1-project-overview)
- [2) Key Features](#2-key-features)
- [3) Installation](#3-installation)
- [4) Provider Setup](#4-provider-setup)
- [5) Quick Start](#5-quick-start)
- [6) CLI Usage Guide](#6-cli-usage-guide)
- [7) Workflow Templates](#7-workflow-templates)
- [8) Plugin System](#8-plugin-system)
- [9) Tool System](#9-tool-system)
- [10) Middleware System](#10-middleware-system)
- [11) Policy Engine](#11-policy-engine)
- [12) Memory Compaction](#12-memory-compaction)
- [13) Observability & Trace System](#13-observability--trace-system)
- [14) UI/UX Features](#14-uiux-features)
- [15) Configuration](#15-configuration)
- [16) Development Guide](#16-development-guide)
- [17) Architecture Diagram (Text)](#17-architecture-diagram-text)
- [18) Troubleshooting](#18-troubleshooting)
- [19) Roadmap](#19-roadmap)
- [20) License & Contribution](#20-license--contribution)

---

## 1) Project Overview

Kage is an **AI workflow runtime CLI** for security engineering and operator-in-the-loop automation. It combines agent orchestration, schema-driven tools, policy controls, execution traces, and modular prompt/memory systems in one local-first runtime.

Kage is designed as:

- an AI workflow runtime CLI
- a plugin-extensible orchestration engine
- an agent-based automation platform
- a local-first LLM-compatible system (Ollama, LM Studio, OpenAI-compatible APIs)

### What Kage is built to do

- Turn high-level goals into structured agent/tool workflows
- Execute actions with strict policy/approval boundaries
- Keep a replayable execution trail for audit/debug
- Support extensibility via plugins, workflows, middleware, and MCP tools

### Example workflows

- Recon pipeline: plan -> parallel enumeration -> report synthesis
- Assisted remediation: inspect files -> propose edit -> diff approval -> apply
- Sessionized investigations: preserve context, compact memory, resume later

### Architecture philosophy

- **Composable runtime layers** over monoliths
- **Schema-first contracts** for tools, plugins, workflows
- **Observability-first execution** for diagnosis and replay
- **Safety by default** via policy + approvals + scope controls
- **Local-first operation** with optional external provider integration

---

## 2) Key Features

- **Agent orchestration runtime** (`AgentOrchestrator`) with stepwise execution and pipeline lifecycle events
- **Parallel scheduling** via parallel agent groups and merge semantics
- **Schema-driven ToolRegistry** with strict argument validation and deterministic registration order
- **Plugin system** for capabilities, ToolRegistry tools, middleware, and workflows
- **Workflow templates** (YAML) with required tools/middleware and parallel steps
- **Prompt-Layer Compiler** (`PromptCompiler`) with budget-aware layer assembly
- **Prompt middleware API** (`before_compile`, `after_compile`) with deterministic priority ordering
- **Policy engine** (`allow | ask | deny`) with per-tool decisions and trace events
- **Memory compaction engine** for transcript summarization into semantic memory blocks
- **Execution trace pipeline** (structured runtime events + export to JSON/JSONL)
- **Claude-style interactive terminal UX** with streaming, status bar, diagnostics panels, and command palette

---

## 3) Installation

### Requirements

- Python **3.10+**
- `pip`

### Install from source (recommended)

```bash
git clone https://github.com/kage-security/kage.git
cd kage
pip install -e .
```

### Editable development install

```bash
pip install -e ".[dev]"
```

### PyPI-style install (example)

```bash
pip install kage-cli
```

### Run Kage

```bash
kage --help
kage launch
```

### Notes

- Package metadata currently publishes project name as `kage`.
- If using source checkout, prefer editable install for fastest iteration.

---

## 4) Provider Setup

Kage stores config in `~/.kage/config.yaml` (override with `KAGE_CONFIG_DIR`).

### Ollama

```yaml
llm:
  provider: ollama
  model: llama3
  base_url: http://localhost:11434
  api_key: null
```

### LM Studio

```yaml
llm:
  provider: lmstudio
  model: your-model-name
  base_url: http://localhost:1234/v1
  api_key: lmstudio
```

### OpenAI-compatible API

Use `provider: custom` for OpenAI-compatible endpoints:

```yaml
llm:
  provider: custom
  model: gpt-4o-mini
  base_url: http://localhost:1234/v1
  api_key: lmstudio
```

Or native OpenAI:

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
```

### Quick provider bootstrap

```bash
kage launch
kage launch lmstudio
kage launch openai --url https://api.openai.com/v1
```

---

## 5) Quick Start

Start chat runtime:

```bash
kage chat
```

Inside chat:

```text
/tools list
/workflows list
/trace last
/prompt inspect
/plugins list
```

Workflow command (current chat-mode preview registration):

```text
/run workflow recon_scan
```

CLI-style example (target-state UX):

```bash
kage run recon_scan example.com
```

### What happens internally

1. Prompt layers compile through `PromptCompiler` (with middleware hooks)
2. Agent pipeline state updates through orchestrator/scheduler
3. Tool calls are validated, policy-evaluated, and optionally approval-gated
4. Runtime events are recorded into session trace
5. Memory compaction may summarize transcript into reusable blocks

---

## 6) CLI Usage Guide

### Core commands

```bash
kage launch
kage setup
kage chat --ui rich
kage chat --ui debug
kage hack <target>
```

### Session commands

```bash
kage session list
kage session resume <session_id>
kage session export <session_id> --output session.md
kage session delete <session_id>
```

### Report commands

```bash
kage report generate --session <session_id> --format markdown
kage report list
kage report view --output report.html
```

### Plugin management

```bash
kage plugin list
kage plugin info recon
kage plugin validate plugins/recon
kage plugin load recon
kage plugin create my_plugin --output plugins
```

### Chat slash commands

```text
/help
/status
/safe
/save <name>
/load <name>
/run workflow <name>
/tools list
/workflows list
/memory inspect
/trace last
/trace debug
/trace export
/prompt inspect
/plugins list
/ui dino on
/ui dino off
```

---

## 7) Workflow Templates

Kage workflows are YAML-defined templates that map to agent pipelines.

### Template schema concepts

- `name`
- `description`
- `pipeline` (sequential and `parallel` blocks)
- `required_tools`
- `required_middleware`
- `policy_overrides`
- `default_parameters`

### Example `recon_scan.yaml`

```yaml
name: recon_scan
description: Recon workflow with planning and parallel enumeration
required_tools:
  - builtin.session.note
required_middleware:
  - recon_context_injector
default_parameters:
  target: example.com
pipeline:
  - PlannerAgent
  - parallel:
      - ReconAgent
      - EnumAgent
  - ReporterAgent
```

### Execution

```bash
kage chat
```

```text
/run workflow recon_scan
```

Target CLI form:

```bash
kage run recon_scan example.com
```

> **Current state:** workflow execution is currently surfaced in chat as `/run workflow <name>` (preview path).

---

## 8) Plugin System

Plugins provide modular runtime extension points for:

- capability declarations
- ToolRegistry-bound tools
- prompt middleware declarations
- workflow declarations

### Example plugin layout

```text
plugins/
  recon/
    plugin.yaml
    recon.py
    workflows/
      recon_scan.yaml
```

### `plugin.yaml` highlights

- Metadata: `name`, `version`, `description`, `entry_point`, `plugin_class`
- Tool declarations: `tools[]`
- Middleware declarations: `middleware[]`
- Workflow declarations: `workflows[]`
- Security hints: `allowed_imports`, `network_access`, `file_access`

### Example tool declaration snippet

```yaml
tools:
  - name: scan
    description: Scan target for open services
    parameters:
      target:
        type: string
        required: true
    executor: recon_scan
    dangerous: false
    requires_approval: true
```

This becomes `plugin.recon.scan` in ToolRegistry namespace.

---

## 9) Tool System

Kage routes tool execution through a schema-driven `ToolRegistry`.

### Tool sources

- **Builtin tools**: `builtin.*` (e.g. `builtin.shell.run`, `builtin.fs.read`)
- **Plugin tools**: `plugin.<plugin>.<tool>`
- **MCP tools**: `mcp.<server>.<tool>`

### Example tool names

- `plugin.recon.scan`
- `mcp.nmap.scan`

### Tool execution lifecycle

1. Lookup tool schema
2. Validate JSON-schema arguments
3. Evaluate policy (`allow | ask | deny`)
4. Execute bound executor
5. Emit trace events:
   - `tool_selected`
   - `tool_executed`
   - `tool_completed`
   - `tool_failed`

---

## 10) Middleware System

Prompt middleware extends compilation lifecycle through two hooks:

- `before_compile(context)`
- `after_compile(compiled_prompt)`

### Middleware API shape

```python
class PromptMiddleware(Protocol):
    name: str
    priority: int
    def before_compile(self, context: PromptContext) -> list[PromptLayer] | None: ...
    def after_compile(self, compiled_prompt: CompiledPrompt) -> CompiledPrompt: ...
```

### How middleware modifies context

`before_compile(context)` can:

- mutate runtime metadata (`context.metadata`)
- inject prompt layers dynamically
- enrich reasoning context with plugin/workflow artifacts

`after_compile(prompt)` can:

- rewrite assembled prompt text
- apply final normalizations/guardrails
- preserve deterministic ordering via middleware priority

---

## 11) Policy Engine

Kage uses a policy graph evaluation model through `PolicyEngine`.

### Decision model

- `allow`: execute directly
- `ask`: require explicit approval
- `deny`: block execution

### Typical control surfaces

- workspace/file access restrictions
- network target restrictions
- dangerous-tool gating
- plugin and MCP trust boundaries
- agent tool-access scope constraints

### Enforcement flow (simplified)

```text
Tool Plan -> PolicyContext -> PolicyEngine.evaluate()
                    |
                    +-> allow -> execute
                    +-> ask   -> approval workflow -> execute/abort
                    +-> deny  -> fail fast
```

Policy outcomes are emitted as `policy_decision` trace events.

---

## 12) Memory Compaction

Long sessions are compacted into semantic `MemoryBlock` objects.

### Memory block structure

- `summary`
- `entities[]`
- `artifacts[]`
- `confidence_score`
- `source_turn_ids[]`
- `timestamp_range`
- `metadata`

### Why compaction exists

- reduce context length pressure
- preserve important workflow facts
- enable semantic memory reuse across turns

### Example output

```text
block_id: 6ac5...
summary: Open ports detected on example.com: 22, 80, 443
entities: [example.com, ssh, http, https]
artifacts: [nmap_scan_result]
confidence_score: 0.84
source_turn_ids: [12, 13, 14]
```

---

## 13) Observability & Trace System

Kage emits structured trace events across:

- prompt compilation
- middleware lifecycle
- workflow execution
- agent/parallel step scheduling
- tool selection/execution
- policy decisions
- memory compaction

### Trace export

```python
from kage.core.observability import export_json, export_jsonl

json_blob = export_json(session.trace)
jsonl_blob = export_jsonl(session.trace)
```

### Useful diagnostics commands

```text
/trace last
/trace debug
/trace export
/prompt inspect
```

---

## 14) UI/UX Features

Kage provides a rich terminal experience inspired by modern interactive AI CLIs.

### Highlights

- streaming token output
- cinematic split-layout runtime paneling
- workflow progress and parallel-agent state views
- tool preview and policy decision panels
- diff approval panels for file edits
- slash-command palette with fuzzy matching
- status bar with provider/model/workflow/memory/policy/session
- optional dinosaur companion panel (`/ui dino on|off`)

### UI modes

```bash
kage chat --ui plain
kage chat --ui rich
kage chat --ui debug
kage chat --ui json
```

---

## 15) Configuration

Default config path:

- `~/.kage/config.yaml`

Environment overrides:

- `KAGE_CONFIG_DIR`
- `KAGE_DATA_DIR`

### Example `config.yaml`

```yaml
llm:
  provider: ollama
  model: llama3.1
  base_url: http://localhost:11434
  api_key: null
  temperature: 0.7
  max_tokens: 4096
  timeout: 120

security:
  safe_mode: true
  require_approval: true
  audit_enabled: true
  scope_enforcement: true

ui:
  theme: dark
  dino_enabled: true

session:
  auto_save: true
  save_interval: 60
  max_history: 1000

mcp_servers:
  - name: nmap
    transport: stdio
    command: nmap-mcp
    args: []
    timeout: 30.0
```

---

## 16) Development Guide

### Repository structure (high-level)

```text
src/kage/
  ai/                # LLM provider abstraction + provider implementations
  cli/               # Typer commands, chat loop, setup wizard
  core/
    agents/          # Agent interfaces, pipeline, scheduler, orchestrator
    prompt/          # Prompt layers, compiler, middleware registry
    tools/           # Tool models, registry, builtin tools, MCP adapter
    workflows/       # Workflow schema/template/loader/executor
    policy/          # Policy context/decision/rules/engine
    memory/          # Memory blocks, compactor, store/retriever
    observability/   # Trace events/recorder/export
  executor/          # local/ssh/docker/wsl execution adapters
  plugins/           # plugin runtime + schema/sandbox
  security/          # safe mode, scope, approval, audit
  persistence/       # config + session persistence
  reporting/         # report templating/export
  ui/                # rich renderer, panels, palette, diff/status views
```

### Add a new ToolRegistry tool

1. Define `ToolSchema` (name, description, JSON parameter schema)
2. Bind executor via `ToolExecutorBinding`
3. Set permissions (`dangerous`, `requires_approval`, scopes/tags)
4. Register into `ToolRegistry`

### Add a workflow template

1. Create YAML matching `WorkflowTemplateSchema`
2. Add pipeline (including optional `parallel` blocks)
3. Load/register via workflow loader/registry path

### Add middleware

1. Implement middleware protocol hooks
2. Register with `MiddlewareRegistry` (priority-aware ordering)
3. Optionally expose through plugin manifest middleware list

### Add/extend agents

1. Implement `BaseAgent` contract
2. Return structured `AgentResult` (tool calls + output)
3. Include agent in workflow template/pipeline mapping

---

## 17) Architecture Diagram (Text)

```text
User / CLI Input
    |
    v
PromptCompiler + MiddlewareRegistry
    |
    v
AgentOrchestrator (sequential + parallel scheduler)
    |
    +--> ToolRegistry --------------------+
    |                                     |
    |                                     v
    |                               PolicyEngine
    |                            (allow / ask / deny)
    |
    +--> WorkflowExecutor / Templates
    |
    +--> MemoryCompactor -> MemoryStore/Retriever
    |
    +--> TraceRecorder -> SessionTrace -> export_json/jsonl
    |
    v
UI Renderer (streaming, status bar, palette, diagnostics)
```

---

## 18) Troubleshooting

### Ollama connection errors

- Ensure Ollama server is running: `ollama serve`
- Verify URL: `http://localhost:11434`
- Confirm models exist: `ollama list`

### LM Studio API mismatch

- Ensure local API server is enabled
- Use base URL with `/v1`: `http://localhost:1234/v1`
- Use provider `lmstudio` (or `custom` for compatible endpoints)

### OpenAI-compatible request issues

- Verify `base_url` and model name
- Ensure API key expectations match your backend
- Prefer `provider: custom` for non-native OpenAI services

### Tool schema parsing failures

- Validate plugin tool names are local identifiers in manifest (`scan`, not `plugin.recon.scan`)
- Ensure parameters are valid schema objects/type descriptors
- Set `additionalProperties` expectations appropriately

### Plugin loading failures

- Validate first: `kage plugin validate plugins/<name>`
- Confirm `plugin.yaml`, `entry_point`, `plugin_class`
- Review sandbox/import restrictions in plugin metadata

### MCP tool registration problems

- Ensure unique server namespace (`mcp.<server>.*`)
- Verify transport-specific fields:
  - `stdio` -> `command`
  - `http/sse` -> `url`
- Confirm server output is valid MCP JSON-RPC shape

---

## 19) Roadmap

Planned and emerging directions:

- richer capability registry and tool introspection metadata
- distributed/multi-node agent execution
- plugin/workflow marketplace support
- advanced UI dashboards and trace replay views
- deeper policy simulation / what-if tooling

---

## 20) License & Contribution

### License

Kage is released under the MIT License. See [`LICENSE`](LICENSE).

### Contributing

1. Fork repository and create a focused branch
2. Keep changes typed, tested, and scoped
3. Run quality gates before opening a PR

```bash
pip install -e ".[dev]"
ruff check src/ tests/
mypy src/kage/
pytest tests/ -v
```

Coverage run:

```bash
pytest tests/ -v --cov=src/kage --cov-report=html
```

If running tests without editable install:

```powershell
$env:PYTHONPATH="src"
python -m pytest tests/ -q
```

---

If you want, I can also generate a shorter operator-focused quick reference section (install + provider config + command cheatsheet) at the top of this README.
