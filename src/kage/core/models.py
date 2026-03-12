"""Core data models for Kage."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from kage.utils import utcnow


class Severity(str, Enum):
    """CVSS v3.1 severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ExecutionEnvironment(str, Enum):
    """Supported execution environments."""

    LOCAL = "local"
    SSH = "ssh"
    DOCKER = "docker"
    WSL = "wsl"
    KALI_MCP = "kali_mcp"


class CommandStatus(str, Enum):
    """Command execution status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class MessageRole(str, Enum):
    """Conversation message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """A single conversation message."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Command(BaseModel):
    """A command to be executed."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command: str
    description: str | None = None
    environment: ExecutionEnvironment = ExecutionEnvironment.LOCAL
    status: CommandStatus = CommandStatus.PENDING
    working_dir: str | None = None
    timeout: int = 300
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    approved_by: str | None = None


class Finding(BaseModel):
    """A security finding."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    severity: Severity
    description: str
    impact: str | None = None
    remediation: str | None = None
    cvss_score: float | None = None
    cvss_vector: str | None = None
    cwe_id: str | None = None
    evidence: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    target: str | None = None
    discovered_at: datetime = Field(default_factory=utcnow)
    auto_detected: bool = False
    verified: bool = False


class Target(BaseModel):
    """A target within scope."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    value: str
    target_type: str  # ip, cidr, domain, url
    notes: str | None = None
    added_at: datetime = Field(default_factory=utcnow)


class Scope(BaseModel):
    """Testing scope definition."""

    targets: list[Target] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Session(BaseModel):
    """A penetration testing session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    scope: Scope = Field(default_factory=Scope)
    messages: list[Message] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    safe_mode: bool = True
    environment: ExecutionEnvironment = ExecutionEnvironment.LOCAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEntry(BaseModel):
    """A single audit log entry with hash chain."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=utcnow)
    session_id: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str | None = None
    entry_hash: str | None = None

    def compute_hash(self) -> str:
        """Compute hash for this entry."""
        # Use json.dumps with sort_keys for deterministic dict serialization
        details_str = json.dumps(self.details, sort_keys=True, default=str)
        data = f"{self.timestamp.isoformat()}|{self.session_id}|{self.action}|{details_str}|{self.previous_hash or ''}"
        return hashlib.sha256(data.encode()).hexdigest()

    def finalize(self, previous_hash: str | None = None) -> None:
        """Finalize entry with hash chain."""
        self.previous_hash = previous_hash
        self.entry_hash = self.compute_hash()

    def verify(self) -> bool:
        """Verify entry hash is valid."""
        return self.entry_hash == self.compute_hash()


class PluginCapability(BaseModel):
    """A capability provided by a plugin."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    returns: str | None = None
    dangerous: bool = False


class PluginMetadata(BaseModel):
    """Plugin metadata from plugin.yaml."""

    name: str
    version: str
    description: str
    author: str | None = None
    capabilities: list[PluginCapability] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
