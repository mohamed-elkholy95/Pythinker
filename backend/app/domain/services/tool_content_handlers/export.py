"""Export tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.domain.models.event import ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_export_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Sync exported files (archives, reports) to session files."""
    if event.function_result and hasattr(event.function_result, "data"):
        data = event.function_result.data
        if isinstance(data, dict):
            export_path = data.get("path") or data.get("file_path") or data.get("output_path")
            if export_path:
                await ctx._sync_file_to_storage(export_path)
                logger.debug("Agent %s: Synced export file '%s'", ctx._agent_id, export_path)
