"""First-time setup wizard for Kage."""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from kage.ai.providers.ollama import OllamaProvider
from kage.ai.providers.openai import LMStudioProvider, OpenAIProvider
from kage.cli.ui.themes import KAGE_LOGO, KAGE_THEME
from kage.persistence.config import KageConfig, LLMConfig


EMBEDDING_MODEL_KEYWORDS = {"embed", "embedding", "nomic-embed", "bge", "e5", "gte"}


def _is_embedding_model(name: str) -> bool:
    """Check if a model name looks like an embedding model (not suitable for chat)."""
    lower = name.lower()
    return any(kw in lower for kw in EMBEDDING_MODEL_KEYWORDS)


async def _test_ollama_connection(base_url: str) -> tuple[bool, list[str]]:
    """Test Ollama connection and list chat-capable models."""
    provider = OllamaProvider(base_url=base_url)
    try:
        connected = await provider.check_connection()
        models = await provider.list_models() if connected else []
        # Filter out embedding models — they can't be used for chat
        models = [m for m in models if not _is_embedding_model(m)]
        return connected, models
    finally:
        await provider.close()


async def _test_lmstudio_connection(base_url: str) -> tuple[bool, list[str]]:
    """Test LM Studio connection and list models."""
    provider = LMStudioProvider(base_url=base_url)
    try:
        connected = await provider.check_connection()
        models = await provider.list_models() if connected else []
        return connected, models
    finally:
        await provider.close()


async def _test_openai_connection(base_url: str, api_key: str) -> tuple[bool, list[str]]:
    """Test OpenAI connection and list models."""
    provider = OpenAIProvider(base_url=base_url, api_key=api_key)
    try:
        connected = await provider.check_connection()
        models = await provider.list_models() if connected else []
        return connected, models
    finally:
        await provider.close()


def _run_async(coro):
    """Run async coroutine in sync context."""
    return asyncio.run(coro)


def run_setup_wizard(console: Console | None = None) -> KageConfig:
    """Run the first-time setup wizard."""
    if console is None:
        console = Console(theme=KAGE_THEME)

    config = KageConfig.load()

    # Welcome screen
    console.clear()
    console.print(KAGE_LOGO)
    console.print()
    console.print(
        Panel(
            "[info]Welcome to Kage setup wizard.[/info]\n\n"
            "This will help you configure the essential settings.\n"
            "You can change these later via [command]kage config[/command].",
            title="[panel.title]Setup Wizard[/panel.title]",
            border_style="panel.border",
        )
    )
    console.print()

    # Step 1: LLM Provider
    console.print("[header]Step 1: LLM Provider[/header]")
    console.print()

    provider_options = {
        "1": ("ollama", "Ollama (local, recommended for privacy)"),
        "2": ("openai", "OpenAI API (requires API key)"),
        "3": ("lmstudio", "LM Studio (local)"),
        "4": ("custom", "Custom OpenAI-compatible endpoint"),
    }

    for key, (_, desc) in provider_options.items():
        console.print(f"  [{key}] {desc}")

    console.print()
    choice = Prompt.ask(
        "[prompt]Select provider[/prompt]",
        choices=list(provider_options.keys()),
        default="1",
        console=console,
    )

    provider_name, _ = provider_options[choice]

    # Configure based on provider
    llm_config = LLMConfig(provider=provider_name)

    if provider_name == "ollama":
        llm_config.base_url = Prompt.ask(
            "[prompt]Ollama URL[/prompt]",
            default="http://localhost:11434",
            console=console,
        )

        # Test connection
        console.print()
        with console.status("[info]Testing connection to Ollama...[/info]"):
            connected, models = _run_async(_test_ollama_connection(llm_config.base_url))

        if not connected:
            console.print("[error]✗ Could not connect to Ollama![/error]")
            console.print("[muted]  Make sure Ollama is running: ollama serve[/muted]")
            console.print(f"[muted]  URL tested: {llm_config.base_url}[/muted]")
            console.print()
            if not Confirm.ask("[prompt]Continue anyway?[/prompt]", default=False, console=console):
                console.print(
                    "[warning]Setup cancelled. Start Ollama and run [command]kage setup[/command] again.[/warning]"
                )
                return config
            llm_config.model = Prompt.ask(
                "[prompt]Model name[/prompt]",
                default="llama3.1",
                console=console,
            )
        else:
            console.print("[success]✓ Connected to Ollama[/success]")
            if models:
                console.print(f"[info]  Found {len(models)} model(s)[/info]")
                console.print()
                console.print("[header]Available Models:[/header]")
                for i, model in enumerate(models[:10], 1):
                    console.print(f"  [{i}] {model}")
                if len(models) > 10:
                    console.print(f"  [muted]... and {len(models) - 10} more[/muted]")
                console.print()

                model_choice = Prompt.ask(
                    "[prompt]Enter model number or name[/prompt]",
                    default="1" if models else "llama3.1",
                    console=console,
                )
                # Check if user entered a number
                if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                    llm_config.model = models[int(model_choice) - 1]
                else:
                    llm_config.model = model_choice
            else:
                console.print(
                    "[warning]  No models found. Pull a model: ollama pull llama3.1[/warning]"
                )
                llm_config.model = Prompt.ask(
                    "[prompt]Model name[/prompt]",
                    default="llama3.1",
                    console=console,
                )

    elif provider_name == "openai":
        api_key = Prompt.ask(
            "[prompt]OpenAI API Key[/prompt]",
            password=True,
            console=console,
        )
        llm_config.api_key = api_key
        llm_config.base_url = "https://api.openai.com/v1"

        # Test connection
        console.print()
        with console.status("[info]Testing connection to OpenAI...[/info]"):
            connected, models = _run_async(_test_openai_connection(llm_config.base_url, api_key))

        if not connected:
            console.print("[error]✗ Could not connect to OpenAI![/error]")
            console.print("[muted]  Check your API key is valid[/muted]")
            console.print()
            if not Confirm.ask("[prompt]Continue anyway?[/prompt]", default=False, console=console):
                console.print("[warning]Setup cancelled.[/warning]")
                return config
        else:
            console.print("[success]✓ Connected to OpenAI[/success]")

        llm_config.model = Prompt.ask(
            "[prompt]Model name[/prompt]",
            default="gpt-4o-mini",
            console=console,
        )

    elif provider_name == "lmstudio":
        llm_config.base_url = Prompt.ask(
            "[prompt]LM Studio URL[/prompt]",
            default="http://localhost:1234/v1",
            console=console,
        )

        # Test connection
        console.print()
        with console.status("[info]Testing connection to LM Studio...[/info]"):
            connected, models = _run_async(_test_lmstudio_connection(llm_config.base_url))

        if not connected:
            console.print("[error]✗ Could not connect to LM Studio![/error]")
            console.print(
                "[muted]  Make sure LM Studio is running with the local server enabled.[/muted]"
            )
            console.print(f"[muted]  URL tested: {llm_config.base_url}[/muted]")
            console.print()
            if not Confirm.ask("[prompt]Continue anyway?[/prompt]", default=False, console=console):
                console.print(
                    "[warning]Setup cancelled. Start LM Studio server and run [command]kage setup[/command] again.[/warning]"
                )
                return config
            llm_config.model = Prompt.ask(
                "[prompt]Model name[/prompt]",
                default="local-model",
                console=console,
            )
        else:
            console.print("[success]✓ Connected to LM Studio[/success]")
            if models:
                console.print(f"[info]  Found {len(models)} model(s)[/info]")
                console.print()
                console.print("[header]Available Models:[/header]")
                for i, model in enumerate(models[:10], 1):
                    console.print(f"  [{i}] {model}")
                if len(models) > 10:
                    console.print(f"  [muted]... and {len(models) - 10} more[/muted]")
                console.print()

                model_choice = Prompt.ask(
                    "[prompt]Enter model number or name[/prompt]",
                    default="1" if models else "local-model",
                    console=console,
                )
                if model_choice.isdigit() and 1 <= int(model_choice) <= len(models):
                    llm_config.model = models[int(model_choice) - 1]
                else:
                    llm_config.model = model_choice
            else:
                console.print("[info]  LM Studio returns loaded model at runtime[/info]")
                llm_config.model = Prompt.ask(
                    "[prompt]Model name (or 'local-model')[/prompt]",
                    default="local-model",
                    console=console,
                )

    elif provider_name == "custom":
        llm_config.base_url = Prompt.ask(
            "[prompt]API Base URL[/prompt]",
            console=console,
        )
        llm_config.api_key = (
            Prompt.ask(
                "[prompt]API Key (leave empty if none)[/prompt]",
                password=True,
                default="",
                console=console,
            )
            or None
        )
        llm_config.model = Prompt.ask(
            "[prompt]Model name[/prompt]",
            console=console,
        )

    config.llm = llm_config
    console.print()

    # Step 2: Security Settings
    console.print("[header]Step 2: Security Settings[/header]")
    console.print()

    config.security.safe_mode = Confirm.ask(
        "[prompt]Enable Safe Mode? (blocks dangerous commands)[/prompt]",
        default=True,
        console=console,
    )

    config.security.require_approval = Confirm.ask(
        "[prompt]Require approval before executing commands?[/prompt]",
        default=True,
        console=console,
    )

    config.security.scope_enforcement = Confirm.ask(
        "[prompt]Enable scope enforcement? (warns about out-of-scope targets)[/prompt]",
        default=True,
        console=console,
    )

    console.print()

    # Step 3: Confirmation
    console.print("[header]Configuration Summary[/header]")
    console.print()

    summary = Text()
    summary.append("LLM Provider: ", style="subtitle")
    summary.append(f"{config.llm.provider}\n", style="info")
    summary.append("Model: ", style="subtitle")
    summary.append(f"{config.llm.model}\n", style="info")
    summary.append("Safe Mode: ", style="subtitle")
    summary.append(
        f"{'Enabled' if config.security.safe_mode else 'Disabled'}\n",
        style="safe" if config.security.safe_mode else "unsafe",
    )
    summary.append("Require Approval: ", style="subtitle")
    summary.append(f"{'Yes' if config.security.require_approval else 'No'}\n", style="info")
    summary.append("Scope Enforcement: ", style="subtitle")
    summary.append(
        f"{'Enabled' if config.security.scope_enforcement else 'Disabled'}", style="info"
    )

    console.print(
        Panel(summary, title="[panel.title]Summary[/panel.title]", border_style="panel.border")
    )
    console.print()

    if Confirm.ask("[prompt]Save this configuration?[/prompt]", default=True, console=console):
        config.first_run = False
        config.save()
        console.print()
        console.print("[success]Configuration saved![/success]")
        console.print(f"[muted]Config file: {config.get_config_path()}[/muted]")
    else:
        console.print()
        console.print(
            "[warning]Configuration not saved. Run [command]kage setup[/command] to try again.[/warning]"
        )

    console.print()
    console.print("[info]Run [command]kage chat[/command] to start a session.[/info]")

    return config
