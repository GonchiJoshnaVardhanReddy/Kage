"""Token budgeting primitives for prompt layer compilation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .context import PromptLayerOutput


def estimate_tokens(text: str) -> int:
    """Estimate token count using a conservative char-based heuristic."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def deduplicate_lines(text: str) -> str:
    """Remove exact duplicate lines while preserving first occurrence order."""
    seen: set[str] = set()
    unique_lines: list[str] = []
    for line in text.splitlines():
        normalized = line.strip()
        if normalized and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        unique_lines.append(line)
    return "\n".join(unique_lines).strip()


@dataclass(slots=True)
class TokenBudget:
    """Budget configuration for prompt compiler."""

    max_tokens: int = 4096
    layer_limits: dict[str, int] = field(default_factory=dict)
    min_priority_to_keep: int = 0


def truncate_to_token_limit(text: str, token_limit: int) -> str:
    """Truncate text to rough token budget by reducing line count."""
    if token_limit <= 0:
        return ""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    current = "\n".join(lines)
    while estimate_tokens(current) > token_limit and len(lines) > 1:
        lines.pop()
        current = "\n".join(lines)
    if estimate_tokens(current) > token_limit:
        max_chars = token_limit * 4
        return current[:max_chars].rstrip()
    return current


def apply_budget_to_layers(
    layers: list[PromptLayerOutput],
    budget: TokenBudget,
) -> tuple[list[PromptLayerOutput], list[str], int]:
    """Enforce per-layer and global token limits; drop lowest-priority layers first."""
    normalized: list[PromptLayerOutput] = []
    for layer in layers:
        content = deduplicate_lines(layer.content)
        layer_limit = budget.layer_limits.get(layer.name)
        if layer_limit is not None:
            content = truncate_to_token_limit(content, layer_limit)
        if content:
            normalized.append(
                PromptLayerOutput(
                    name=layer.name,
                    priority=layer.priority,
                    content=content,
                )
            )

    ordered = sorted(normalized, key=lambda item: item.priority)
    dropped: list[str] = []

    total_tokens = sum(estimate_tokens(layer.content) for layer in ordered)
    while total_tokens > budget.max_tokens and ordered:
        drop_index = len(ordered) - 1
        candidate = ordered[drop_index]
        if candidate.priority < budget.min_priority_to_keep:
            break
        dropped.append(candidate.name)
        ordered.pop(drop_index)
        total_tokens = sum(estimate_tokens(layer.content) for layer in ordered)

    return ordered, dropped, total_tokens

