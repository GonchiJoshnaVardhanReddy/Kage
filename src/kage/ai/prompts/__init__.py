"""AI prompts module for Kage."""

from kage.ai.prompts.parsers import (
    ParsedCommand,
    ParsedFinding,
    ParsedResponse,
    extract_commands_simple,
    parse_response,
    parse_tool_output_for_findings,
)
from kage.ai.prompts.system import (
    COMMAND_SUGGESTION_PROMPT,
    FINDING_EXTRACTION_PROMPT,
    SYSTEM_PROMPT,
    build_context_message,
    build_system_prompt,
)

__all__ = [
    "COMMAND_SUGGESTION_PROMPT",
    "FINDING_EXTRACTION_PROMPT",
    "ParsedCommand",
    "ParsedFinding",
    "ParsedResponse",
    "SYSTEM_PROMPT",
    "build_context_message",
    "build_system_prompt",
    "extract_commands_simple",
    "parse_response",
    "parse_tool_output_for_findings",
]
