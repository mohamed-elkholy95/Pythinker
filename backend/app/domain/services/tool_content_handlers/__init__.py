"""Per-tool content handler registry.

Replaces the 472-line elif chain in AgentTaskRunner._handle_tool_event
with a dict-based dispatch. Each handler module is ~30-80 lines focused
on a single tool's content generation logic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from app.domain.models.event import ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)

ContentHandler = Callable[[ToolEvent, "AgentTaskRunner"], Coroutine[Any, Any, None]]


def get_content_handler_registry() -> dict[str, ContentHandler]:
    """Build and return the tool content handler registry.

    Lazy imports prevent circular dependencies and keep startup fast.
    """
    from .browser import handle_browser_content
    from .browser_agent import handle_browser_agent_content
    from .canvas import handle_canvas_content
    from .chart import handle_chart_content
    from .code_executor import handle_code_executor_content
    from .export import handle_export_content
    from .file import handle_file_content
    from .mcp import handle_mcp_content
    from .search import handle_search_content
    from .shell import handle_shell_content

    return {
        "browser": handle_browser_content,
        "search": handle_search_content,
        "chart": handle_chart_content,
        "shell": handle_shell_content,
        "file": handle_file_content,
        "mcp": handle_mcp_content,
        "browser_agent": handle_browser_agent_content,
        "browsing": handle_browser_agent_content,  # alias
        "code_executor": handle_code_executor_content,
        "canvas": handle_canvas_content,
        "export": handle_export_content,
    }
