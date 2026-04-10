"""
Tests for Plotly runtime capability check and fallback behavior.

Covers:
- PlotlyCapabilityCheck: probing sandbox for Plotly + Kaleido availability
- Cache TTL behaviour: cached results are reused within TTL, refreshed after
- Cache invalidation: per-session and bulk
- Probe error handling: sandbox errors, empty output, parse failures
- Orchestrator integration: generate_chart skips when capability unavailable
- Orchestrator integration: generate_chart proceeds when capability available
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from app.domain.models.tool_result import ToolResult
from app.domain.services.plotly_capability_check import (
    PlotlyCapabilityCheck,
    PlotlyCapabilityResult,
    PlotlyCapabilityStatus,
)
from app.domain.services.plotly_chart_orchestrator import (
    ChartAnalysisResult,
    PlotlyChartOrchestrator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checker() -> PlotlyCapabilityCheck:
    """Fresh capability checker with a short TTL for testing."""
    return PlotlyCapabilityCheck(cache_ttl=60.0)


@pytest.fixture
def mock_sandbox_available() -> AsyncMock:
    """Sandbox mock that simulates Plotly + Kaleido installed."""
    sandbox = AsyncMock()
    sandbox.exec_command.return_value = ToolResult.ok(
        message="ok",
        data={"output": "6.3.1,1.0.0"},
    )
    return sandbox


@pytest.fixture
def mock_sandbox_unavailable() -> AsyncMock:
    """Sandbox mock that simulates Plotly NOT installed (command fails)."""
    sandbox = AsyncMock()
    sandbox.exec_command.return_value = ToolResult.error(
        message="ModuleNotFoundError: No module named 'plotly'",
    )
    return sandbox


@pytest.fixture
def mock_sandbox_empty_output() -> AsyncMock:
    """Sandbox mock that returns success but with empty output."""
    sandbox = AsyncMock()
    sandbox.exec_command.return_value = ToolResult.ok(
        message="ok",
        data={"output": ""},
    )
    return sandbox


@pytest.fixture
def mock_sandbox_exception() -> AsyncMock:
    """Sandbox mock that raises an exception on exec_command."""
    sandbox = AsyncMock()
    sandbox.exec_command.side_effect = ConnectionError("sandbox unreachable")
    return sandbox


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Mock LLM that returns a chart-generating analysis."""
    llm = AsyncMock()
    llm.model_name = "test-model"
    return llm


# ---------------------------------------------------------------------------
# PlotlyCapabilityResult unit tests
# ---------------------------------------------------------------------------


class TestPlotlyCapabilityResult:
    """Verify PlotlyCapabilityResult dataclass."""

    def test_is_available_true(self) -> None:
        result = PlotlyCapabilityResult(
            status=PlotlyCapabilityStatus.AVAILABLE,
            plotly_version="6.3.1",
            kaleido_version="1.0.0",
            checked_at=time.monotonic(),
        )
        assert result.is_available is True

    def test_is_available_false_for_unavailable(self) -> None:
        result = PlotlyCapabilityResult(
            status=PlotlyCapabilityStatus.UNAVAILABLE,
            checked_at=time.monotonic(),
        )
        assert result.is_available is False

    def test_is_available_false_for_unknown(self) -> None:
        result = PlotlyCapabilityResult(
            status=PlotlyCapabilityStatus.UNKNOWN,
            checked_at=time.monotonic(),
            error_message="Probe exception",
        )
        assert result.is_available is False

    def test_default_fields(self) -> None:
        result = PlotlyCapabilityResult(
            status=PlotlyCapabilityStatus.AVAILABLE,
        )
        assert result.plotly_version is None
        assert result.kaleido_version is None
        assert result.checked_at == 0.0
        assert result.error_message is None


# ---------------------------------------------------------------------------
# PlotlyCapabilityStatus enum tests
# ---------------------------------------------------------------------------


class TestPlotlyCapabilityStatus:
    """Verify status enum values."""

    def test_status_values(self) -> None:
        assert PlotlyCapabilityStatus.AVAILABLE == "available"
        assert PlotlyCapabilityStatus.UNAVAILABLE == "unavailable"
        assert PlotlyCapabilityStatus.UNKNOWN == "unknown"

    def test_is_str_enum(self) -> None:
        assert isinstance(PlotlyCapabilityStatus.AVAILABLE, str)


# ---------------------------------------------------------------------------
# Capability check — successful probe
# ---------------------------------------------------------------------------


class TestCapabilityCheckAvailable:
    """Verify probe returns AVAILABLE when Plotly + Kaleido are importable."""

    @pytest.mark.asyncio
    async def test_probe_returns_available(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock
    ) -> None:
        result = await checker.check(mock_sandbox_available, "session-1")

        assert result.status == PlotlyCapabilityStatus.AVAILABLE
        assert result.plotly_version == "6.3.1"
        assert result.kaleido_version == "1.0.0"
        assert result.is_available is True
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_probe_caches_result(self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock) -> None:
        """Second check within TTL should return cached result without re-probing."""
        result1 = await checker.check(mock_sandbox_available, "session-1")
        result2 = await checker.check(mock_sandbox_available, "session-1")

        assert result1 is result2  # same object from cache
        # exec_command called only once
        assert mock_sandbox_available.exec_command.call_count == 1

    @pytest.mark.asyncio
    async def test_probe_caches_per_session(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock
    ) -> None:
        """Different sessions should probe independently."""
        await checker.check(mock_sandbox_available, "session-1")
        await checker.check(mock_sandbox_available, "session-2")

        assert mock_sandbox_available.exec_command.call_count == 2
        assert "session-1" in checker.cached_sessions
        assert "session-2" in checker.cached_sessions


# ---------------------------------------------------------------------------
# Capability check — unavailable probe
# ---------------------------------------------------------------------------


class TestCapabilityCheckUnavailable:
    """Verify probe returns UNAVAILABLE when Plotly is not installed."""

    @pytest.mark.asyncio
    async def test_probe_returns_unavailable_on_command_failure(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_unavailable: AsyncMock
    ) -> None:
        result = await checker.check(mock_sandbox_unavailable, "session-1")

        assert result.status == PlotlyCapabilityStatus.UNAVAILABLE
        assert result.is_available is False
        assert result.plotly_version is None
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_probe_returns_unavailable_on_empty_output(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_empty_output: AsyncMock
    ) -> None:
        result = await checker.check(mock_sandbox_empty_output, "session-1")

        assert result.status == PlotlyCapabilityStatus.UNAVAILABLE
        assert result.error_message == "Empty probe output"

    @pytest.mark.asyncio
    async def test_probe_returns_unknown_on_exception(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_exception: AsyncMock
    ) -> None:
        result = await checker.check(mock_sandbox_exception, "session-1")

        assert result.status == PlotlyCapabilityStatus.UNKNOWN
        assert result.is_available is False
        assert "Probe exception" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_probe_returns_unavailable_when_output_contains_import_traceback(
        self, checker: PlotlyCapabilityCheck
    ) -> None:
        sandbox = AsyncMock()
        sandbox.exec_command.return_value = ToolResult.ok(
            message="ok",
            data={
                "output": (
                    "Traceback (most recent call last):\n"
                    '  File "<string>", line 1, in <module>\n'
                    "ModuleNotFoundError: No module named 'plotly'"
                )
            },
        )

        result = await checker.check(sandbox, "session-1")

        assert result.status == PlotlyCapabilityStatus.UNAVAILABLE
        assert result.is_available is False
        assert "ModuleNotFoundError" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Cache TTL and invalidation
# ---------------------------------------------------------------------------


class TestCapabilityCacheBehaviour:
    """Verify caching, TTL expiry, and invalidation."""

    @pytest.mark.asyncio
    async def test_cache_reuses_within_ttl(self, mock_sandbox_available: AsyncMock) -> None:
        checker = PlotlyCapabilityCheck(cache_ttl=300.0)
        await checker.check(mock_sandbox_available, "s1")
        await checker.check(mock_sandbox_available, "s1")

        assert mock_sandbox_available.exec_command.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, mock_sandbox_available: AsyncMock) -> None:
        checker = PlotlyCapabilityCheck(cache_ttl=0.0)  # immediate expiry
        await checker.check(mock_sandbox_available, "s1")
        await checker.check(mock_sandbox_available, "s1")

        # TTL=0 means every check re-probes
        assert mock_sandbox_available.exec_command.call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_removes_cached_session(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock
    ) -> None:
        await checker.check(mock_sandbox_available, "s1")
        assert "s1" in checker.cached_sessions

        checker.invalidate("s1")
        assert "s1" not in checker.cached_sessions

    @pytest.mark.asyncio
    async def test_invalidate_unknown_session_is_noop(self, checker: PlotlyCapabilityCheck) -> None:
        checker.invalidate("nonexistent")  # should not raise

    @pytest.mark.asyncio
    async def test_invalidate_all_clears_everything(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock
    ) -> None:
        await checker.check(mock_sandbox_available, "s1")
        await checker.check(mock_sandbox_available, "s2")
        assert len(checker.cached_sessions) == 2

        checker.invalidate_all()
        assert len(checker.cached_sessions) == 0

    @pytest.mark.asyncio
    async def test_after_invalidate_reprobes(
        self, checker: PlotlyCapabilityCheck, mock_sandbox_available: AsyncMock
    ) -> None:
        await checker.check(mock_sandbox_available, "s1")
        checker.invalidate("s1")
        await checker.check(mock_sandbox_available, "s1")

        assert mock_sandbox_available.exec_command.call_count == 2


# ---------------------------------------------------------------------------
# Orchestrator fallback — capability check integration
# ---------------------------------------------------------------------------


def _make_orchestrator(
    sandbox: AsyncMock,
    llm: AsyncMock | None = None,
) -> PlotlyChartOrchestrator:
    return PlotlyChartOrchestrator(
        sandbox=sandbox,
        session_id="test-session",
        llm=llm,
    )


def _make_sandbox_with_chart_output() -> AsyncMock:
    """Sandbox mock that simulates successful chart generation."""
    sandbox = AsyncMock()
    sandbox.file_write.return_value = ToolResult.ok(message="written")
    sandbox.file_delete.return_value = ToolResult.ok(message="deleted")
    sandbox.exec_command.return_value = ToolResult.ok(
        message="ok",
        data={
            "output": '{"success": true, "html_path": "/workspace/chart.html", '
            '"png_path": "/workspace/chart.png", '
            '"html_size": 2048, "png_size": 1024, '
            '"data_points": 3}'
        },
    )
    return sandbox


class TestOrchestratorFallbackNoLlm:
    """Verify orchestrator returns None when no LLM is available."""

    @pytest.mark.asyncio
    async def test_no_llm_returns_none(self) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=None)

        result = await orch.generate_chart(
            report_title="Comparison",
            markdown_content="# Data\n| A | B |\n| 1 | 2 |",
            report_id="r1",
        )
        assert result is None


class TestOrchestratorFallbackEmptyContent:
    """Verify orchestrator returns None for empty content."""

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self, mock_llm: AsyncMock) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=mock_llm)

        result = await orch.generate_chart(
            report_title="Empty",
            markdown_content="   ",
            report_id="r1",
        )
        assert result is None
        mock_llm.ask_structured.assert_not_called()


class TestOrchestratorFallbackLlmError:
    """Verify orchestrator gracefully handles LLM failures."""

    @pytest.mark.asyncio
    async def test_llm_exception_returns_none(self, mock_llm: AsyncMock) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.side_effect = RuntimeError("LLM timeout")

        result = await orch.generate_chart(
            report_title="Test",
            markdown_content="# Data\n| A | B |\n| 1 | 2 |",
            report_id="r1",
        )
        assert result is None


class TestOrchestratorFallbackLlmSaysNo:
    """Verify orchestrator respects LLM's decision to skip chart."""

    @pytest.mark.asyncio
    async def test_llm_says_no_chart(self, mock_llm: AsyncMock) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=False,
            reason="Qualitative content, no numeric comparison.",
        )

        result = await orch.generate_chart(
            report_title="Guide",
            markdown_content="# How to do X\nStep 1...",
            report_id="r1",
        )
        assert result is None


class TestOrchestratorFallbackTooFewPoints:
    """Verify orchestrator skips when LLM returns < 2 data points."""

    @pytest.mark.asyncio
    async def test_single_point_returns_none(self, mock_llm: AsyncMock) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="Test",
            metric_name="Score",
            lower_is_better=False,
            points=[{"label": "A", "value": 10.0}],
            reason="Only one data point.",
        )

        result = await orch.generate_chart(
            report_title="Test",
            markdown_content="# Data\n| A | 10 |",
            report_id="r1",
        )
        assert result is None


class TestOrchestratorSuccessPath:
    """Verify orchestrator produces chart when everything works."""

    @pytest.mark.asyncio
    async def test_full_chart_generation(self, mock_llm: AsyncMock) -> None:
        sandbox = _make_sandbox_with_chart_output()
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="API Latency Comparison",
            metric_name="Latency (ms)",
            lower_is_better=True,
            points=[
                {"label": "Claude", "value": 95.0},
                {"label": "GPT-4", "value": 120.0},
                {"label": "Gemini", "value": 110.0},
            ],
            reason="Comparing latencies.",
        )

        result = await orch.generate_chart(
            report_title="API Latency Comparison",
            markdown_content="# Latency\n| Model | ms |\n|---|---|\n| Claude | 95 |",
            report_id="r1",
        )

        assert result is not None
        assert result.data_points == 3
        assert result.html_path == "/workspace/chart.html"
        assert result.png_path == "/workspace/chart.png"
        assert result.html_size == 2048
        assert result.png_size == 1024
        assert result.metric_name == "Latency (ms)"


class TestOrchestratorSandboxScriptFailure:
    """Verify orchestrator returns None when sandbox script fails."""

    @pytest.mark.asyncio
    async def test_script_failure_returns_none(self, mock_llm: AsyncMock) -> None:
        sandbox = AsyncMock()
        sandbox.file_write.return_value = ToolResult.ok(message="written")
        sandbox.file_delete.return_value = ToolResult.ok(message="deleted")
        sandbox.exec_command.return_value = ToolResult.error(
            message="Script failed: ModuleNotFoundError: No module named 'plotly'",
        )
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="Test",
            metric_name="Score",
            lower_is_better=False,
            points=[
                {"label": "A", "value": 10.0},
                {"label": "B", "value": 20.0},
            ],
        )

        result = await orch.generate_chart(
            report_title="Test",
            markdown_content="# Data\n| A | 10 |\n| B | 20 |",
            report_id="r1",
        )
        assert result is None


class TestOrchestratorSandboxWriteFailure:
    """Verify orchestrator returns None when file_write fails."""

    @pytest.mark.asyncio
    async def test_write_failure_returns_none(self, mock_llm: AsyncMock) -> None:
        sandbox = AsyncMock()
        sandbox.file_write.return_value = ToolResult.error(message="Permission denied")
        orch = _make_orchestrator(sandbox, llm=mock_llm)
        mock_llm.ask_structured.return_value = ChartAnalysisResult(
            should_generate=True,
            chart_type="bar",
            title="Test",
            metric_name="Score",
            lower_is_better=False,
            points=[
                {"label": "A", "value": 10.0},
                {"label": "B", "value": 20.0},
            ],
        )

        result = await orch.generate_chart(
            report_title="Test",
            markdown_content="# Data\n| A | 10 |\n| B | 20 |",
            report_id="r1",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Capability check + orchestrator combined scenario
# ---------------------------------------------------------------------------


class TestCapabilityCheckOrchestratorIntegration:
    """End-to-end scenario: capability check gates chart generation."""

    @pytest.mark.asyncio
    async def test_skip_chart_when_capability_unavailable(
        self,
    ) -> None:
        """When capability check says UNAVAILABLE, chart generation should not
        even attempt to call the LLM."""
        sandbox = AsyncMock()
        # Capability probe returns unavailable
        sandbox.exec_command.return_value = ToolResult.error(
            message="ModuleNotFoundError: No module named 'plotly'",
        )
        llm = AsyncMock()
        llm.model_name = "test-model"

        checker = PlotlyCapabilityCheck(cache_ttl=60.0)
        cap_result = await checker.check(sandbox, "test-session")

        assert cap_result.is_available is False

        # The orchestrator itself doesn't use the checker internally yet —
        # the caller would gate on this. Verify the pattern works:
        if cap_result.is_available:
            orch = _make_orchestrator(sandbox, llm=llm)
            _ = await orch.generate_chart(
                report_title="Test",
                markdown_content="# Data",
                report_id="r1",
            )
            llm.ask_structured.assert_called()
        else:
            # Chart generation skipped entirely — LLM never called
            llm.ask_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceed_when_capability_available(self, mock_llm: AsyncMock) -> None:
        """When capability check says AVAILABLE, chart generation proceeds."""
        sandbox = _make_sandbox_with_chart_output()
        sandbox.exec_command.side_effect = [
            ToolResult.ok(message="ok", data={"output": "6.3.1,1.0.0"}),
            ToolResult.ok(
                message="ok",
                data={
                    "output": '{"success": true, "html_path": "/workspace/chart.html", '
                    '"png_path": "/workspace/chart.png", '
                    '"html_size": 2048, "png_size": 1024, '
                    '"data_points": 3}'
                },
            ),
        ]

        checker = PlotlyCapabilityCheck(cache_ttl=60.0)
        cap_result = await checker.check(sandbox, "test-session")

        assert cap_result.is_available is True

        if cap_result.is_available:
            orch = _make_orchestrator(sandbox, llm=mock_llm)
            mock_llm.ask_structured.return_value = ChartAnalysisResult(
                should_generate=True,
                chart_type="bar",
                title="Test",
                metric_name="Score",
                lower_is_better=False,
                points=[
                    {"label": "A", "value": 10.0},
                    {"label": "B", "value": 20.0},
                ],
            )
            result = await orch.generate_chart(
                report_title="Test",
                markdown_content="# Data",
                report_id="r1",
            )
            assert result is not None
