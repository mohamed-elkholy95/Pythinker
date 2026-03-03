"""Scratchpad tool — agent-facing interface for persistent working notes.

Provides two tools:
- scratchpad_write: Append a note (with optional tag) to the scratchpad.
- scratchpad_read: Read all current scratchpad entries.

The scratchpad content survives all forms of compaction because it's
injected transiently (not stored in conversation memory).
"""

import logging
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.scratchpad import Scratchpad
from app.domain.services.tools.base import BaseTool, tool

logger = logging.getLogger(__name__)


class ScratchpadTool(BaseTool):
    """Tool for reading/writing persistent agent notes."""

    name: str = "scratchpad"

    def __init__(self, scratchpad: Scratchpad, max_observe: int | None = None) -> None:
        super().__init__(max_observe=max_observe)
        self._scratchpad = scratchpad

    @tool(
        name="scratchpad_write",
        description=(
            "Write a note to your persistent scratchpad. Notes survive context compaction "
            "and are always available. Use for key findings, URLs, decisions, errors, "
            "and intermediate results you need to remember."
        ),
        parameters={
            "note": {
                "type": "string",
                "description": "The note text to record.",
            },
            "tag": {
                "type": "string",
                "description": "Optional category tag (e.g. 'url', 'error', 'decision', 'finding').",
            },
        },
        required=["note"],
    )
    async def scratchpad_write(self, note: str = "", tag: str = "", **_: Any) -> ToolResult:
        """Write a note to the scratchpad."""
        if not note:
            return ToolResult.error("Note text is required.")

        self._scratchpad.append(note, tag=tag)
        return ToolResult.ok(
            message=f"Note recorded ({len(note)} chars, tag={tag or 'none'}). "
            f"Scratchpad has {self._scratchpad.entry_count} entries.",
        )

    @tool(
        name="scratchpad_read",
        description="Read all notes from your persistent scratchpad.",
        parameters={},
        required=[],
    )
    async def scratchpad_read(self, **_: Any) -> ToolResult:
        """Read all scratchpad entries."""
        if self._scratchpad.is_empty:
            return ToolResult.ok(message="Scratchpad is empty.", data="")

        content = self._scratchpad.get_content()
        return ToolResult.ok(
            message=f"Scratchpad has {self._scratchpad.entry_count} entries.",
            data=content,
        )
