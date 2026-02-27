"""Chart tool content handler."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.domain.models.event import ChartToolContent, ToolEvent

if TYPE_CHECKING:
    from app.domain.services.agent_task_runner import AgentTaskRunner

logger = logging.getLogger(__name__)


async def handle_chart_content(event: ToolEvent, ctx: AgentTaskRunner) -> None:
    """Sync chart artifacts (HTML/PNG/Plotly JSON) to storage."""
    if not (event.function_result and hasattr(event.function_result, "data")):
        return

    raw_data = getattr(event.function_result, "data", None)
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    tool_success = bool(getattr(event.function_result, "success", False))
    tool_message = str(getattr(event.function_result, "message", "") or "")

    html_path = data.get("html_path")
    png_path = data.get("png_path")
    plotly_json_path = data.get("plotly_json_path")

    html_info = None
    png_info = None
    plotly_json_info = None
    sync_errors: list[str] = []
    sync_warnings: list[str] = []

    if not tool_success and tool_message:
        sync_errors.append(tool_message)
    elif tool_success and not html_path and not png_path and not plotly_json_path:
        sync_errors.append("Chart generation returned no output files")

    sync_plan: list[tuple[str, str, str]] = []
    if isinstance(html_path, str) and html_path:
        sync_plan.append(("html", html_path, "text/html"))
    if isinstance(png_path, str) and png_path:
        sync_plan.append(("png", png_path, "image/png"))
    if isinstance(plotly_json_path, str) and plotly_json_path:
        sync_plan.append(("plotly_json", plotly_json_path, "application/json"))

    if sync_plan:
        sync_tasks = [
            ctx._sync_file_to_storage_with_retry(
                artifact_path,
                content_type=content_type,
                max_attempts=3,
            )
            for _, artifact_path, content_type in sync_plan
        ]
        results = await asyncio.gather(*sync_tasks, return_exceptions=True)

        for (artifact_kind, artifact_path, _), result in zip(sync_plan, results, strict=False):
            artifact_label = artifact_kind.replace("_", " ").upper()
            if isinstance(result, Exception):
                message = f"{artifact_label} sync failed: {result}"
                if artifact_kind == "plotly_json":
                    sync_warnings.append(message)
                else:
                    sync_errors.append(message)
                logger.warning("%s", message)
                continue

            if result is None:
                message = f"{artifact_label} file missing or empty in sandbox"
                if artifact_kind == "plotly_json":
                    sync_warnings.append(message)
                else:
                    sync_errors.append(message)
                logger.warning("%s for %s", message, artifact_path)
                continue

            if artifact_kind == "html":
                html_info = result
            elif artifact_kind == "png":
                png_info = result
            elif artifact_kind == "plotly_json":
                plotly_json_info = result

    chart_error = "; ".join(sync_errors) if sync_errors else None

    event.tool_content = ChartToolContent(
        chart_type=data.get("chart_type", "bar"),
        title=data.get("title", "Chart"),
        html_file_id=html_info.file_id if html_info else None,
        png_file_id=png_info.file_id if png_info else None,
        plotly_json_file_id=plotly_json_info.file_id if plotly_json_info else None,
        html_filename=html_info.filename if html_info else None,
        png_filename=png_info.filename if png_info else None,
        plotly_json_filename=plotly_json_info.filename if plotly_json_info else None,
        html_size=data.get("html_size"),
        plotly_json_size=data.get("plotly_json_size"),
        render_contract_version=data.get("render_contract_version"),
        data_points=data.get("data_points", 0),
        series_count=data.get("series_count", 0),
        error=chart_error,
    )

    log_fn = logger.error if chart_error else logger.info
    log_fn(
        (
            "Chart created: type=%s title=%s data_points=%s series=%s "
            "html=%s png=%s plotly_json=%s contract=%s warnings=%s error=%s"
        ),
        data.get("chart_type"),
        data.get("title"),
        data.get("data_points"),
        data.get("series_count"),
        "synced" if html_info else "missing/failed",
        "synced" if png_info else "missing/failed",
        "synced" if plotly_json_info else "missing/failed",
        data.get("render_contract_version"),
        "; ".join(sync_warnings) if sync_warnings else None,
        chart_error,
    )
