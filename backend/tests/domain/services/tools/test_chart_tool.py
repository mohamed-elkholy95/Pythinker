"""Tests for ChartTool JSON render-contract propagation and chart type support."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.tools.chart import ChartTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# New chart types and features tests
# ---------------------------------------------------------------------------


def _make_sandbox(output: str | None = None) -> AsyncMock:
    """Create a mock sandbox with standard behavior."""
    sandbox = AsyncMock()
    sandbox.file_write = AsyncMock(return_value=MagicMock(success=True))
    sandbox.file_delete = AsyncMock(return_value=MagicMock(success=True))
    sandbox.wait_for_process = AsyncMock(return_value=MagicMock(success=True))
    sandbox.view_shell = AsyncMock(return_value=MagicMock(data={"output": ""}))

    if output is None:
        output = _build_success_output(include_json=True)

    sandbox.exec_command = AsyncMock(
        return_value=MagicMock(
            success=True,
            data={"status": "completed", "output": output},
            message="",
        )
    )
    return sandbox


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chart_type",
    ["donut", "waterfall", "funnel"],
)
async def test_new_chart_types_accepted(chart_type: str) -> None:
    """New chart types pass through to sandbox script without error."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type=chart_type,
        title=f"Test {chart_type}",
        labels=["A", "B", "C"],
        datasets=[{"name": "S1", "values": [10, 20, 30]}],
    )
    assert result.success is True
    # Verify chart_type was passed through to sandbox spec
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["chart_type"] == chart_type


@pytest.mark.asyncio
async def test_auto_chart_type_passthrough() -> None:
    """Auto chart type is passed to sandbox for resolution."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="auto",
        title="Auto Test",
        labels=["X", "Y"],
        datasets=[{"name": "S1", "values": [1, 2]}],
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["chart_type"] == "auto"


@pytest.mark.asyncio
async def test_auto_orientation_passthrough() -> None:
    """Auto orientation is passed through to sandbox."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="bar",
        title="Orientation Test",
        labels=["Short"],
        datasets=[{"name": "S1", "values": [42]}],
        orientation="auto",
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["orientation"] == "auto"


@pytest.mark.asyncio
async def test_treemap_requires_parents() -> None:
    """Treemap without parents returns validation error."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="treemap",
        title="Treemap Test",
        labels=["Root", "Child1"],
        datasets=[{"name": "S1", "values": [100, 50]}],
    )
    assert result.success is False
    assert "parents" in result.message.lower()


@pytest.mark.asyncio
async def test_treemap_parents_length_mismatch() -> None:
    """Treemap with mismatched parents/labels length returns error."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="treemap",
        title="Treemap Test",
        labels=["Root", "Child1", "Child2"],
        datasets=[{"name": "S1", "values": [100, 50, 30]}],
        parents=["", "Root"],  # Only 2 parents for 3 labels
    )
    assert result.success is False
    assert "match" in result.message.lower()


@pytest.mark.asyncio
async def test_treemap_with_valid_parents() -> None:
    """Treemap with valid parents passes through correctly."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="treemap",
        title="Budget",
        labels=["Total", "Eng", "Sales"],
        datasets=[{"name": "Budget", "values": [100, 60, 40]}],
        parents=["", "Total", "Total"],
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["parents"] == ["", "Total", "Total"]


@pytest.mark.asyncio
async def test_indicator_no_labels_required() -> None:
    """Indicator chart works without labels."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="indicator",
        title="Current MRR",
        datasets=[{"name": "MRR", "values": [125000]}],
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["chart_type"] == "indicator"
    assert written["labels"] == []


@pytest.mark.asyncio
async def test_indicator_with_reference() -> None:
    """Indicator chart passes reference for delta calculation."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="indicator",
        title="MRR",
        datasets=[{"name": "MRR", "values": [125000]}],
        reference=110000,
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["reference"] == 110000


@pytest.mark.asyncio
async def test_waterfall_measure_passthrough() -> None:
    """Waterfall measure field is passed through in dataset."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    datasets = [
        {
            "name": "P&L",
            "values": [100, -20, -10, 70],
            "measure": ["absolute", "relative", "relative", "total"],
        }
    ]
    result = await tool.chart_create(
        chart_type="waterfall",
        title="P&L",
        labels=["Revenue", "COGS", "Tax", "Profit"],
        datasets=datasets,
    )
    assert result.success is True
    written = json.loads(sandbox.file_write.call_args.kwargs["content"])
    assert written["datasets"][0]["measure"] == ["absolute", "relative", "relative", "total"]


@pytest.mark.asyncio
async def test_empty_labels_rejected_for_non_indicator() -> None:
    """Non-indicator charts require labels."""
    sandbox = _make_sandbox()
    tool = ChartTool(sandbox=sandbox, session_id="s1")
    result = await tool.chart_create(
        chart_type="bar",
        title="Empty",
        labels=[],
        datasets=[{"values": [1]}],
    )
    assert result.success is False
    assert "labels" in result.message.lower()
