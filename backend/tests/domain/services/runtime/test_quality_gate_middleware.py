"""Tests for QualityGateMiddleware.

Covers:
- before_step calls toolset_manager and stores filtered tools in metadata.
- after_step calls coverage_validator and stores score + validity in metadata.
- No validators present → context returned unchanged.
- after_step calls async grounding_validator and stores grounding results.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.runtime.middleware import RuntimeContext
from app.domain.services.runtime.quality_gate_middleware import QualityGateMiddleware

# ─────────────────────────── helpers ─────────────────────────────────────────


def _make_ctx(**metadata: object) -> RuntimeContext:
    return RuntimeContext(session_id="sess-test", agent_id="agent-1", metadata=dict(metadata))


# ─────────────────────────── before_step tests ───────────────────────────────


@pytest.mark.asyncio
async def test_before_step_filters_tools() -> None:
    """before_step calls get_tools_for_task and stores result in metadata."""
    filtered_tools = ["search_tool", "file_read_tool"]

    toolset_manager = MagicMock()
    toolset_manager.get_tools_for_task.return_value = filtered_tools

    middleware = QualityGateMiddleware(toolset_manager=toolset_manager)
    ctx = _make_ctx(current_step_description="search the web for Python news")

    result = await middleware.before_step(ctx)

    toolset_manager.get_tools_for_task.assert_called_once_with("search the web for Python news")
    assert result.metadata["filtered_tools"] == filtered_tools


# ─────────────────────────── after_step tests ────────────────────────────────


@pytest.mark.asyncio
async def test_after_step_runs_coverage_check() -> None:
    """after_step calls coverage_validator.validate and stores quality_score and is_valid."""
    coverage_result = SimpleNamespace(quality_score=0.85, is_valid=True)

    coverage_validator = MagicMock()
    coverage_validator.validate.return_value = coverage_result

    middleware = QualityGateMiddleware(coverage_validator=coverage_validator)
    ctx = _make_ctx(
        step_output="Here is the answer to your question.",
        user_request="What is Python?",
    )

    result = await middleware.after_step(ctx)

    coverage_validator.validate.assert_called_once_with(
        output="Here is the answer to your question.",
        user_request="What is Python?",
    )
    assert result.metadata["quality_score"] == 0.85
    assert result.metadata["is_valid"] is True


@pytest.mark.asyncio
async def test_no_validators_passes_through() -> None:
    """Context is returned unchanged when no validators are configured."""
    middleware = QualityGateMiddleware()
    original_metadata = {"step_output": "some output", "other_key": 42}
    ctx = _make_ctx(**original_metadata)

    result_before = await middleware.before_step(ctx)
    result_after = await middleware.after_step(result_before)

    # No quality keys injected.
    assert "filtered_tools" not in result_after.metadata
    assert "quality_score" not in result_after.metadata
    assert "is_valid" not in result_after.metadata
    assert "grounding_score" not in result_after.metadata
    assert "is_grounding_acceptable" not in result_after.metadata
    # Original keys untouched.
    assert result_after.metadata["other_key"] == 42


@pytest.mark.asyncio
async def test_grounding_check_on_after_step() -> None:
    """after_step awaits grounding_validator.validate and stores grounding results."""
    grounding_result = SimpleNamespace(overall_score=0.92, is_acceptable=True)

    grounding_validator = AsyncMock()
    grounding_validator.validate = AsyncMock(return_value=grounding_result)

    middleware = QualityGateMiddleware(grounding_validator=grounding_validator)
    ctx = _make_ctx(
        step_output="The capital of France is Paris.",
        source_context="France is a country in Western Europe. Its capital city is Paris.",
    )

    result = await middleware.after_step(ctx)

    grounding_validator.validate.assert_awaited_once_with(
        output="The capital of France is Paris.",
        source_context="France is a country in Western Europe. Its capital city is Paris.",
    )
    assert result.metadata["grounding_score"] == 0.92
    assert result.metadata["is_grounding_acceptable"] is True
