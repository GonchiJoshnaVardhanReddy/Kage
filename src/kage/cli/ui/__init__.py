"""CLI UI components for Kage."""

from kage.cli.ui.panels import (
    create_command_panel,
    create_finding_panel,
    create_scope_panel,
    create_status_panel,
)
from kage.cli.ui.prompts import (
    clear_thinking,
    prompt_command_approval,
    prompt_first_run,
    prompt_safe_mode_warning,
    prompt_scope_warning,
    prompt_user_input,
    show_thinking,
)
from kage.cli.ui.themes import KAGE_LOGO, KAGE_LOGO_SMALL, KAGE_THEME

__all__ = [
    "KAGE_LOGO",
    "KAGE_LOGO_SMALL",
    "KAGE_THEME",
    "clear_thinking",
    "create_command_panel",
    "create_finding_panel",
    "create_scope_panel",
    "create_status_panel",
    "prompt_command_approval",
    "prompt_first_run",
    "prompt_safe_mode_warning",
    "prompt_scope_warning",
    "prompt_user_input",
    "show_thinking",
]
