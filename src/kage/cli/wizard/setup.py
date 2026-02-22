"""First-time setup wizard for Kage."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from kage.cli.ui.themes import KAGE_LOGO, KAGE_THEME
from kage.persistence.config import KageConfig, LLMConfig


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
        llm_config.model = Prompt.ask(
            "[prompt]Model name[/prompt]",
            default="local-model",
            console=console,
        )

    elif provider_name == "custom":
        llm_config.base_url = Prompt.ask(
            "[prompt]API Base URL[/prompt]",
            console=console,
        )
        llm_config.api_key = Prompt.ask(
            "[prompt]API Key (leave empty if none)[/prompt]",
            password=True,
            default="",
            console=console,
        ) or None
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
    summary.append(f"{'Enabled' if config.security.safe_mode else 'Disabled'}\n",
                   style="safe" if config.security.safe_mode else "unsafe")
    summary.append("Require Approval: ", style="subtitle")
    summary.append(f"{'Yes' if config.security.require_approval else 'No'}\n", style="info")
    summary.append("Scope Enforcement: ", style="subtitle")
    summary.append(f"{'Enabled' if config.security.scope_enforcement else 'Disabled'}", style="info")

    console.print(Panel(summary, title="[panel.title]Summary[/panel.title]", border_style="panel.border"))
    console.print()

    if Confirm.ask("[prompt]Save this configuration?[/prompt]", default=True, console=console):
        config.first_run = False
        config.save()
        console.print()
        console.print("[success]Configuration saved![/success]")
        console.print(f"[muted]Config file: {config.get_config_path()}[/muted]")
    else:
        console.print()
        console.print("[warning]Configuration not saved. Run [command]kage setup[/command] to try again.[/warning]")

    console.print()
    console.print("[info]Run [command]kage chat[/command] to start a session.[/info]")

    return config
