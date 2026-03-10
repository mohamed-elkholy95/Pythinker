"""Test step executor last-resort fallback includes raw message preview."""

from unittest.mock import MagicMock

import pytest

from app.domain.models.plan import Step
from app.domain.services.agents.step_executor import StepExecutor


@pytest.fixture
def step_executor():
    return StepExecutor(
        context_manager=MagicMock(),
        source_tracker=MagicMock(),
        metrics=MagicMock(),
    )


def test_last_resort_fallback_includes_raw_preview(step_executor):
    step = MagicMock(spec=Step)
    raw = "I have completed the research and found 5 key insights about the topic."
    result = step_executor.apply_step_result_payload(step, None, raw)
    assert result is False
    assert step.success is False
    assert raw in step.error


def test_last_resort_fallback_truncates_long_message(step_executor):
    step = MagicMock(spec=Step)
    raw = "A" * 500
    result = step_executor.apply_step_result_payload(step, None, raw)
    assert result is False
    # Preview should be truncated to 200 chars
    assert "A" * 200 in step.error
    assert "A" * 201 not in step.error


def test_last_resort_fallback_handles_none_raw(step_executor):
    step = MagicMock(spec=Step)
    result = step_executor.apply_step_result_payload(step, None, None)
    assert result is False
    assert step.error == "Step response did not match expected JSON schema"


def test_last_resort_fallback_handles_empty_raw(step_executor):
    step = MagicMock(spec=Step)
    result = step_executor.apply_step_result_payload(step, None, "")
    assert result is False
    assert step.error == "Step response did not match expected JSON schema"


def test_success_payload_without_result_does_not_echo_raw_json(step_executor):
    step = MagicMock(spec=Step)
    raw = '{"success": true}'

    result = step_executor.apply_step_result_payload(step, {"success": True}, raw)

    assert result is True
    assert step.success is True
    assert step.result is None
    assert step.attachments == []


def test_tool_result_shaped_payload_is_rejected(step_executor):
    step = MagicMock(spec=Step)
    raw = '{"success": true, "message": "[WIDE RESEARCH] Completed research"}'

    result = step_executor.apply_step_result_payload(
        step,
        {"success": True, "message": "[WIDE RESEARCH] Completed research"},
        raw,
    )

    assert result is False
    assert step.success is False
    assert step.result is None
    assert "tool result" in step.error.lower()
