"""Schema models for declarative workflow templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ParallelStepSchema(BaseModel):
    """Parallel workflow step schema."""

    parallel: list[str] = Field(default_factory=list)

    @field_validator("parallel")
    @classmethod
    def _validate_parallel(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not normalized:
            raise ValueError("parallel step must contain at least one agent name")
        return normalized


class WorkflowTemplateSchema(BaseModel):
    """YAML-backed schema for one workflow template."""

    name: str
    description: str = ""
    pipeline: list[str | ParallelStepSchema] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_middleware: list[str] = Field(default_factory=list)
    policy_overrides: dict[str, Any] = Field(default_factory=dict)
    default_parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workflow name cannot be empty")
        return normalized

    @field_validator("pipeline")
    @classmethod
    def _validate_pipeline(cls, value: list[str | ParallelStepSchema]) -> list[str | ParallelStepSchema]:
        if not value:
            raise ValueError("workflow pipeline must contain at least one step")
        return value

    @classmethod
    def from_yaml(cls, path: Path) -> WorkflowTemplateSchema:
        """Load and validate workflow schema from YAML file."""
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        return cls(**raw)

