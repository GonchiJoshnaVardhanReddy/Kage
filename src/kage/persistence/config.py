"""Configuration management for Kage."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    env_dir = os.environ.get("KAGE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("APPDATA", "~"))
    else:  # Linux/macOS
        base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config"))
    
    return base.expanduser() / "kage"


def get_data_dir() -> Path:
    """Get the data directory path."""
    env_dir = os.environ.get("KAGE_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("LOCALAPPDATA", "~"))
    else:  # Linux/macOS
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
    dangerous_commands: list[str] = Field(default_factory=lambda: [
        "rm -rf",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
        "> /dev/sda",
        "chmod -R 777 /",
        "wget.*|.*sh",
        "curl.*|.*bash",
    ])


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
    
    first_run: bool = True

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        return get_config_dir() / "config.yaml"

    @classmethod
    def load(cls) -> "KageConfig":
        """Load configuration from file."""
        config_path = cls.get_config_path()
        
        if not config_path.exists():
            return cls()
        
        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        except Exception:
            return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = self.model_dump(mode="json")
        
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def update(self, **kwargs: Any) -> None:
        """Update configuration values and save."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.save()
