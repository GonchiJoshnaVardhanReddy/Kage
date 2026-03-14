"""Conversation manager for Kage."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kage.ai.base import BaseLLMProvider, LLMConfig, LLMMessage
from kage.ai.prompts import build_context_message, build_system_prompt, parse_response
from kage.ai.streaming import StreamHandler, StreamState
from kage.core.models import Command, Finding, Message, MessageRole, Session, Severity
from kage.core.tools import ToolExecutionPlan, plans_from_commands, plans_from_provider_tool_calls
from kage.utils import utcnow

if TYPE_CHECKING:
    from kage.persistence.config import KageConfig

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Context for a conversation turn."""

    session: Session
    safe_mode: bool = True
    max_history: int = 20


class ConversationManager:
    """Manages conversation flow with the AI assistant."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        config: KageConfig,
        session: Session,
        llm_tools: list[dict[str, object]] | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.session = session
        self._llm_tools = llm_tools
        self._llm_config = LLMConfig(
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            tools=llm_tools,
        )

    def _build_messages(
        self,
        user_message: str,
        additional_context: str | None = None,
    ) -> list[LLMMessage]:
        """Build the message list for the LLM."""
        messages: list[LLMMessage] = []

        # System prompt
        scope_targets = [t.value for t in self.session.scope.targets]
        system_prompt = build_system_prompt(
            safe_mode=self.session.safe_mode,
            scope_targets=scope_targets if scope_targets else None,
            provider_name=self.config.llm.provider,
            model_name=self.config.llm.model,
        )
        messages.append(LLMMessage(role="system", content=system_prompt))

        # Add context message if we have history
        if self.session.commands or self.session.findings:
            context = build_context_message(
                previous_commands=[
                    {
                        "command": c.command,
                        "status": c.status.value,
                        "output": c.stdout or "",
                    }
                    for c in self.session.commands[-5:]
                ],
                findings=[
                    {"title": f.title, "severity": f.severity.value} for f in self.session.findings
                ],
            )
            if context:
                messages.append(LLMMessage(role="system", content=context))

        if additional_context:
            messages.append(LLMMessage(role="system", content=additional_context))

        security_memory = self.session.metadata.get("security_memory", {})
        parsed_outputs = security_memory.get("parsed_outputs", [])
        if parsed_outputs:
            recent = parsed_outputs[-5:]
            parsed_lines = ["## Parsed Tool Outputs (recent)"]
            for item in recent:
                tool = item.get("tool", "unknown")
                parsed = item.get("parsed")
                parsed_lines.append(f"- {tool}: {json.dumps(parsed, default=str)[:500]}")
            messages.append(LLMMessage(role="system", content="\n".join(parsed_lines)))

        # Add conversation history (limited)
        for msg in self.session.messages[-self.config.session.max_history :]:
            if msg.role == MessageRole.SYSTEM:
                continue  # Skip system messages in history
            messages.append(
                LLMMessage(
                    role=msg.role.value,
                    content=msg.content,
                )
            )

        # Add current user message
        messages.append(LLMMessage(role="user", content=user_message))

        return messages

    async def send_message(
        self,
        user_message: str,
        on_chunk: Callable[[str], None] | None = None,
        additional_context: str | None = None,
    ) -> tuple[str, list[Command], list[ToolExecutionPlan]]:
        """Send a message and get a response.

        Returns:
            Tuple of (response text, legacy command list, structured tool plans)
        """
        # Record user message
        self.session.messages.append(Message(role=MessageRole.USER, content=user_message))
        self.session.updated_at = utcnow()

        # Build messages for LLM
        messages = self._build_messages(user_message, additional_context=additional_context)

        # Stream response
        handler = StreamHandler(
            provider=self.provider,
            on_chunk=on_chunk,
        )

        state = StreamState()
        try:
            state = await handler.stream_response(messages, self._llm_config)
            response_text = state.content
        except Exception as e:
            response_text = f"Error communicating with LLM: {e}"

        # Guard against empty responses (e.g. stale connection, provider glitch)
        if not response_text or not response_text.strip():
            response_text = (
                "No response received from LLM. "
                "Please check your provider connection and try again."
            )

        # Record assistant message
        self.session.messages.append(Message(role=MessageRole.ASSISTANT, content=response_text))

        # Parse response for commands
        parsed = parse_response(response_text)
        commands = []
        for cmd in parsed.commands:
            command = Command(
                command=cmd.command,
                description=cmd.description,
            )
            commands.append(command)

        plans_from_tools = plans_from_provider_tool_calls(state.tool_calls)
        legacy_plans = plans_from_commands(commands)
        plans = plans_from_tools if plans_from_tools else legacy_plans

        return response_text, commands, plans

    async def send_message_sync(
        self,
        user_message: str,
        additional_context: str | None = None,
    ) -> tuple[str, list[Command], list[ToolExecutionPlan]]:
        """Send a message without streaming (for simpler use cases)."""
        # Record user message
        self.session.messages.append(Message(role=MessageRole.USER, content=user_message))
        self.session.updated_at = utcnow()

        # Build messages for LLM
        messages = self._build_messages(user_message, additional_context=additional_context)

        try:
            response = await self.provider.complete(messages, self._llm_config)
            response_text = response.content
        except Exception as e:
            response_text = f"Error communicating with LLM: {e}"

        # Record assistant message
        self.session.messages.append(Message(role=MessageRole.ASSISTANT, content=response_text))

        # Parse response for commands
        parsed = parse_response(response_text)
        commands = []
        for cmd in parsed.commands:
            command = Command(
                command=cmd.command,
                description=cmd.description,
            )
            commands.append(command)

        plans_from_tools = plans_from_provider_tool_calls(response.tool_calls)
        legacy_plans = plans_from_commands(commands)
        plans = plans_from_tools if plans_from_tools else legacy_plans

        return response_text, commands, plans

    async def analyze_output(
        self,
        command: Command,
        output: str,
    ) -> list[Finding]:
        """Analyze command output for potential findings."""
        analysis_prompt = f"""Analyze the following command output for security findings.

Command: {command.command}
Target: {self.session.scope.targets[0].value if self.session.scope.targets else "Unknown"}

Output:
```
{output[:4000]}
```

Identify any:
- Open ports/services
- Potential vulnerabilities
- Interesting information disclosure
- Misconfigurations
- Attack vectors

If no significant findings, say "No significant findings."
"""

        messages = [
            LLMMessage(role="system", content="You are a security analyst reviewing tool output."),
            LLMMessage(role="user", content=analysis_prompt),
        ]

        try:
            response = await self.provider.complete(messages, self._llm_config)
            parsed = parse_response(response.content)

            findings = []
            for f in parsed.findings:
                severity_value = f.severity.lower()
                severity = (
                    Severity(severity_value)
                    if severity_value in {"critical", "high", "medium", "low", "info"}
                    else Severity.INFO
                )
                finding = Finding(
                    title=f.title,
                    severity=severity,
                    description=f.description,
                    evidence=f.evidence,
                    impact=f.impact,
                    remediation=f.remediation,
                    target=self.session.scope.targets[0].value
                    if self.session.scope.targets
                    else None,
                    auto_detected=True,
                )
                findings.append(finding)

            return findings

        except Exception as e:
            logger.warning("Failed to analyze command output for '%s': %s", command.command, e)
            return []

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.session.messages.clear()

    def get_summary(self) -> str:
        """Get a summary of the current session."""
        return f"""Session: {self.session.id[:8]}
Messages: {len(self.session.messages)}
Commands: {len(self.session.commands)}
Findings: {len(self.session.findings)}
Scope: {len(self.session.scope.targets)} targets
Safe Mode: {"Enabled" if self.session.safe_mode else "Disabled"}
"""
