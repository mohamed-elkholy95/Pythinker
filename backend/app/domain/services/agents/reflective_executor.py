"""Reflective execution wrapper for phased research actions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from app.domain.external.llm import LLM
from app.domain.models.research_phase import ResearchPhase
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    """Tool invocation descriptor used by reflective execution."""

    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ReflectionResult(BaseModel):
    """Result of a tool execution plus reflection output."""

    action_result: ToolResult[Any] | None
    learned: str
    next_step: str | None = None
    phase: ResearchPhase | None = None


class ReflectiveExecutor:
    """Executes actions and produces concise learned/next-step reflections."""

    def __init__(
        self,
        execute_tool: Callable[[ToolCall], Awaitable[ToolResult[Any] | None]],
        llm: LLM | None = None,
    ):
        self._execute_tool = execute_tool
        self._llm = llm

    async def execute_with_reflection(
        self,
        action: ToolCall,
        phase: ResearchPhase | None = None,
    ) -> ReflectionResult:
        result = await self._execute_tool(action)
        learned, next_step = await self._reflect(action, result)
        return ReflectionResult(
            action_result=result,
            learned=learned,
            next_step=next_step,
            phase=phase,
        )

    async def _reflect(
        self,
        action: ToolCall,
        result: ToolResult[Any] | None,
    ) -> tuple[str, str | None]:
        if self._llm is None:
            return self._default_reflection(action, result)

        prompt = (
            "You executed a research action. Return exactly two lines:\n"
            "LEARNED: <what was learned>\n"
            "NEXT: <what to do next>\n\n"
            f"Action: {action.tool_name}\n"
            f"Parameters: {action.parameters}\n"
            f"Success: {getattr(result, 'success', None)}\n"
            f"Message: {getattr(result, 'message', None)}\n"
            f"Data: {getattr(result, 'data', None)}"
        )

        try:
            response = await self._llm.ask(
                [
                    {"role": "system", "content": "You are a concise research reflection assistant."},
                    {"role": "user", "content": prompt},
                ]
            )
            content = response.get("content", "") if isinstance(response, dict) else ""
            parsed = self.parse_reflection(content)
            if parsed[0]:
                return parsed
        except Exception:
            logger.debug("Failed to generate LLM reflection, using default", exc_info=True)

        return self._default_reflection(action, result)

    @staticmethod
    def parse_reflection(content: str) -> tuple[str, str | None]:
        learned = ""
        next_step: str | None = None

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("LEARNED:"):
                learned = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("NEXT:"):
                next_step = stripped.split(":", 1)[1].strip()

        if not learned:
            learned = content.strip().splitlines()[0].strip() if content.strip() else ""

        return learned, next_step or None

    @staticmethod
    def _default_reflection(action: ToolCall, result: ToolResult[Any] | None) -> tuple[str, str | None]:
        if result is None:
            return (
                f"The action '{action.tool_name}' returned no result.",
                "Retry with adjusted parameters.",
            )

        if result.success:
            learned = result.message or f"'{action.tool_name}' completed successfully."
            return learned, "Proceed to the next research phase."

        learned = result.message or f"'{action.tool_name}' failed."
        return learned, "Refine the query and run another search."
