"""Core module for Kage."""

from kage.core.intent import Intent, IntentResult, classify_intent, needs_ai_classification
from kage.core.models import (
    AuditEntry,
    Command,
    CommandStatus,
    ExecutionEnvironment,
    Finding,
    Message,
    MessageRole,
    PluginCapability,
    PluginMetadata,
    Scope,
    Session,
    Severity,
    Target,
)
from kage.core.planner import ExecutionPlan, PlanStatus, PlanStep
from kage.core.router import CommandRouter, ExecutorType, RouteResult

__all__ = [
    "AuditEntry",
    "Command",
    "CommandRouter",
    "CommandStatus",
    "ExecutionEnvironment",
    "ExecutionPlan",
    "ExecutorType",
    "Finding",
    "Intent",
    "IntentResult",
    "Message",
    "MessageRole",
    "PlanStatus",
    "PlanStep",
    "PluginCapability",
    "PluginMetadata",
    "RouteResult",
    "Scope",
    "Session",
    "Severity",
    "Target",
    "classify_intent",
    "needs_ai_classification",
]
