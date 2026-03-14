"""Configuration management for Kage."""

from __future__ import annotations

import logging
import os
from asyncio import to_thread
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    env_dir = os.environ.get("KAGE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    return Path("~/.kage").expanduser()


def get_data_dir() -> Path:
    """Get the data directory path."""
    env_dir = os.environ.get("KAGE_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", "~"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share"))

    return base.expanduser() / "kage"


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "ollama"
    model: str = "llama3.1"
    base_url: str = "http://localhost:11434"
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120


class SecurityConfig(BaseModel):
    """Security-related configuration."""

    safe_mode: bool = True
    require_approval: bool = True
    audit_enabled: bool = True
    scope_enforcement: bool = True
    dangerous_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",
            "> /dev/sda",
            "chmod -R 777 /",
            "wget.*|.*sh",
            "curl.*|.*bash",
        ]
    )


class SessionConfig(BaseModel):
    """Session configuration."""

    auto_save: bool = True
    save_interval: int = 60
    max_history: int = 1000
    directory: str = ""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.directory:
            self.directory = str(get_data_dir() / "sessions")


class UIConfig(BaseModel):
    """UI configuration."""

    theme: str = "dark"
    show_timestamps: bool = True
    show_command_output: bool = True
    max_output_lines: int = 100
    markdown_code_theme: str = "monokai"


class SlashSuggestionBoostsConfig(BaseModel):
    """Context-aware slash suggestion boost weights."""

    pending_commands: int = 60
    pending_run: int = 55
    pending_save: int = 10
    findings: int = 45
    findings_export: int = 35
    status: int = 40
    scope_hint: int = 10


class ChatConfig(BaseModel):
    """Chat session UX and ranking settings."""

    slash_suggestion_boosts: SlashSuggestionBoostsConfig = Field(
        default_factory=SlashSuggestionBoostsConfig
    )


class MCPServerConfig(BaseModel):
    """One MCP server configuration."""

    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    timeout: float = 30.0
    env: dict[str, str] = Field(default_factory=dict)


class HackModeConfig(BaseModel):
    """Hack mode configuration."""

    enabled: bool = True
    auto_report: bool = True
    report_format: str = "html"
    max_concurrent_tasks: int = 5
    default_timeout: int = 3600
    phases: list[str] = Field(
        default_factory=lambda: [
            "planning",
            "recon",
            "enumeration",
            "exploitation",
            "reporting",
        ]
    )


class KageConfig(BaseSettings):
    """Main configuration for Kage."""

    model_config = SettingsConfigDict(
        env_prefix="KAGE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    hack_mode: HackModeConfig = Field(default_factory=HackModeConfig)

    first_run: bool = True

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        return get_config_dir() / "config.yaml"

    @classmethod
    def load(cls) -> KageConfig:
        """Load configuration from file."""
        config_path = cls.get_config_path()

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        except yaml.YAMLError as e:
            logger.error("Failed to parse config %s: %s — using defaults", config_path, e)
            return cls()
        except Exception as e:
            logger.error("Failed to load config %s: %s — using defaults", config_path, e)
            return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def update(self, **kwargs: Any) -> None:
        """Update configuration values and save."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.save()

    @classmethod
    async def aload(cls) -> KageConfig:
        """Async version of load — runs I/O in a thread."""
        return await to_thread(cls.load)

    async def asave(self) -> None:
        """Async version of save — runs I/O in a thread."""
        await to_thread(self.save)
