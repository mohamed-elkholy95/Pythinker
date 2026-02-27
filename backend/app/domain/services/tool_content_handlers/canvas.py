"""Canvas tool content handler."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.models.event import CanvasToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_canvas_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Extract canvas project metadata and element count."""
    operation = event.function_name.replace("canvas_", "") if event.function_name else "unknown"
    project_id: str | None = None
    project_name: str | None = None
    element_count = 0
    image_urls: list[str] | None = None

    data: Any | None = None
    if event.function_result and hasattr(event.function_result, "data"):
        data = event.function_result.data

    if isinstance(data, dict):
        project_id = data.get("project_id") or data.get("id")
        project_name = data.get("project_name") or data.get("name")
        if isinstance(data.get("elements"), list):
            element_count = len(data["elements"])
        elif isinstance(data.get("element_count"), int):
            element_count = data["element_count"]
        else:
            pages = data.get("pages")
            if isinstance(pages, list):
                for page in pages:
                    if isinstance(page, dict):
                        elems = page.get("elements")
                        if isinstance(elems, list):
                            element_count += len(elems)
        if isinstance(data.get("image_url"), str):
            image_urls = [data["image_url"]]
        elif isinstance(data.get("image_urls"), list):
            image_urls = [str(url) for url in data["image_urls"]]

    if not project_id:
        arg_project_id = event.function_args.get("project_id")
        if isinstance(arg_project_id, str):
            project_id = arg_project_id

    if not project_name:
        arg_name = event.function_args.get("name")
        if isinstance(arg_name, str):
            project_name = arg_name

    event.tool_content = CanvasToolContent(
        operation=operation,
        project_id=project_id,
        project_name=project_name,
        element_count=element_count,
        image_urls=image_urls,
    )
