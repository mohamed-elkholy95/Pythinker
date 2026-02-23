"""Tests for ChartTool JSON render-contract propagation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.tools.chart import ChartTool


def _build_success_output(*, include_json: bool) -> str:
    payload: dict[str, object | None] = {
        "success": True,
        "html_path": "/home/ubuntu/chart-abc12345.html",
        "png_path": "/home/ubuntu/chart-abc12345.png",
        "html_size": 1024,
        "png_size": 2048,
        "chart_type": "bar",
        "data_points": 3,
        "series_count": 1,
    }
    if include_json:
        payload["plotly_json_path"] = "/home/ubuntu/chart-abc12345.plotly.json"
        payload["plotly_json_size"] = 512
        payload["render_contract_version"] = "plotly-json-v1"
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_chart_tool_includes_json_output_path_in_script_input() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    sandbox.exec_command = AsyncMock(
        return_value=MagicMock(
            success=True,
            data={"status": "completed", "output": _build_success_output(include_json=True)},
            message="",
        )
    )
    sandbox.file_delete = AsyncMock(return_value=MagicMock(success=True))
    sandbox.wait_for_process = AsyncMock(return_value=MagicMock(success=True))
    sandbox.view_shell = AsyncMock(return_value=MagicMock(data={"output": ""}))

    tool = ChartTool(sandbox=sandbox, session_id="session-test")
    result = await tool.chart_create(
        chart_type="bar",
        title="Latency",
        labels=["A", "B", "C"],
        datasets=[{"name": "P95", "values": [120, 98, 88]}],
    )

    assert result.success is True
    assert result.data is not None
    assert result.data.get("plotly_json_path") == "/home/ubuntu/chart-abc12345.plotly.json"
    assert result.data.get("plotly_json_size") == 512
    assert result.data.get("render_contract_version") == "plotly-json-v1"

    write_call = sandbox.file_write.call_args
    assert write_call is not None
    written_spec = json.loads(write_call.kwargs["content"])
    assert "output_json" in written_spec
    assert str(written_spec["output_json"]).endswith(".plotly.json")


@pytest.mark.asyncio
async def test_chart_tool_handles_missing_json_contract_fields() -> None:
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    sandbox.exec_command = AsyncMock(
        return_value=MagicMock(
            success=True,
            data={"status": "completed", "output": _build_success_output(include_json=False)},
            message="",
        )
    )
    sandbox.file_delete = AsyncMock(return_value=MagicMock(success=True))
    sandbox.wait_for_process = AsyncMock(return_value=MagicMock(success=True))
    sandbox.view_shell = AsyncMock(return_value=MagicMock(data={"output": ""}))

    tool = ChartTool(sandbox=sandbox, session_id="session-test")
    result = await tool.chart_create(
        chart_type="line",
        title="Throughput",
        labels=["Mon", "Tue", "Wed"],
        datasets=[{"name": "RPS", "values": [900, 940, 980]}],
    )

    assert result.success is True
    assert result.data is not None
    assert result.data.get("plotly_json_path") is None
    assert result.data.get("plotly_json_size") is None
    assert result.data.get("render_contract_version") is None
