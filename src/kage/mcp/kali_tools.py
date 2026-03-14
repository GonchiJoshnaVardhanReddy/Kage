"""Kali Tools MCP orchestration helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from kage.mcp.manager import MCPManager


@dataclass
class KaliToolRecommendation:
    """A recommended Kali tool with docs and an executable suggestion."""

    tool_name: str
    rationale: str
    details: str = ""
    usage: str = ""
    suggested_command: str | None = None


@dataclass
class KaliWorkflowResult:
    """Result of a Kali docs-driven workflow lookup."""

    query: str
    recommendations: list[KaliToolRecommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_recommendations(self) -> bool:
        return bool(self.recommendations)


class KaliToolsAdvisor:
    """Advisor that queries Kali docs MCP tools and builds actionable suggestions."""

    SEARCH_TOOL = "search_kali_tools"
    DETAILS_TOOL = "get_tool_details"
    USAGE_TOOL = "get_tool_usage"
    LIST_BY_CATEGORY_TOOL = "list_tools_by_category"
    LIST_CATEGORIES_TOOL = "list_categories"

    REQUIRED_CORE_TOOLS = {SEARCH_TOOL, DETAILS_TOOL, USAGE_TOOL}

    def __init__(self, manager: MCPManager) -> None:
        self.manager = manager

    def is_available(self) -> bool:
        """Whether the minimum Kali docs MCP tools are available."""
        return all(self.manager.has_tool(tool) for tool in self.REQUIRED_CORE_TOOLS)

    async def recommend_tools(self, user_request: str) -> KaliWorkflowResult:
        """Build tool recommendations for a security request."""
        result = KaliWorkflowResult(query=user_request)

        search_text = await self._call_text(self.SEARCH_TOOL, {"query": user_request})
        if not search_text:
            result.warnings.append("Kali docs search returned no data.")
            return result

        primary_tool = self._extract_primary_tool_name(search_text)
        if not primary_tool:
            result.warnings.append("Could not identify a tool from Kali docs search results.")
            return result

        recommendation = await self._build_recommendation(
            tool_name=primary_tool,
            rationale=f"Matched '{user_request}' via Kali tools search.",
        )
        result.recommendations.append(recommendation)

        if self._needs_multi_step_plan(user_request):
            for query, rationale in (
                ("port scanner", "Port and service discovery"),
                ("directory enumeration", "Web content discovery"),
                ("vulnerability scanner", "Web vulnerability checks"),
            ):
                tool = await self._discover_tool_name(query)
                if not tool or tool == primary_tool:
                    continue
                result.recommendations.append(
                    await self._build_recommendation(tool, rationale=rationale)
                )
                if len(result.recommendations) >= 3:
                    break

        return result

    async def _build_recommendation(
        self,
        tool_name: str,
        rationale: str,
    ) -> KaliToolRecommendation:
        details = await self._call_text(self.DETAILS_TOOL, {"tool_name": tool_name})
        usage = await self._call_text(self.USAGE_TOOL, {"tool_name": tool_name})
        command = self._extract_command_from_usage(tool_name, usage)
        return KaliToolRecommendation(
            tool_name=tool_name,
            rationale=rationale,
            details=details,
            usage=usage,
            suggested_command=command,
        )

    async def _discover_tool_name(self, query: str) -> str | None:
        text = await self._call_text(self.SEARCH_TOOL, {"query": query})
        return self._extract_primary_tool_name(text) if text else None

    async def _call_text(self, tool: str, arguments: dict[str, str]) -> str:
        tool_result = await self.manager.call_tool(tool, arguments)
        if not tool_result.success or tool_result.is_error:
            return ""
        return tool_result.text.strip()

    @staticmethod
    def _needs_multi_step_plan(user_request: str) -> bool:
        text = user_request.lower()
        keywords = ("recon", "reconnaissance", "enumerate", "web reconnaissance")
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _extract_primary_tool_name(text: str) -> str | None:
        # JSON output path
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        for key in ("name", "tool_name", "tool"):
                            value = item.get(key)
                            if isinstance(value, str) and value.strip():
                                return value.strip().lower()
        except json.JSONDecodeError:
            pass

        # Plain text path: look for markdown/code-like hints first.
        for pattern in (
            r"`([a-z0-9][a-z0-9+._-]{1,63})`",
            r"^\s*[-*]\s*([a-z0-9][a-z0-9+._-]{1,63})\b",
            r"^\s*([a-z0-9][a-z0-9+._-]{1,63})\s*[:\-]",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).lower()

        return None

    @staticmethod
    def _extract_command_from_usage(tool_name: str, usage: str) -> str | None:
        if not usage:
            return None

        for line in usage.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith(("#", "//", "- ", "* ")):
                continue
            if candidate.lower().startswith(tool_name.lower()):
                return candidate

        return None
