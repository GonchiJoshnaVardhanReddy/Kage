"""Interactive terminal UI runtime for Kage."""

from .diff import prompt_diff_approval, render_diff_panel
from .dino_animator import DinoAnimator
from .frame_renderer import render_layout
from .layout import (
    KeyboardAction,
    LayoutFrame,
    SplitLayoutConfig,
    map_keypress,
    render_split_layout,
)
from .palette import DEFAULT_SLASH_COMMANDS, SlashCommand, SlashCommandPalette
from .panels import KagePanelState, build_dinosaur_panel, build_kage_panel
from .renderer import BaseUIRenderer, UIMode, create_renderer
from .status import StatusBarState, build_status_state

__all__ = [
    "BaseUIRenderer",
    "DinoAnimator",
    "DEFAULT_SLASH_COMMANDS",
    "KeyboardAction",
    "KagePanelState",
    "LayoutFrame",
    "SlashCommand",
    "SlashCommandPalette",
    "SplitLayoutConfig",
    "StatusBarState",
    "UIMode",
    "build_dinosaur_panel",
    "build_kage_panel",
    "build_status_state",
    "create_renderer",
    "map_keypress",
    "prompt_diff_approval",
    "render_layout",
    "render_split_layout",
    "render_diff_panel",
]

