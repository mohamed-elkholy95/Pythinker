"""Comprehensive unit tests for StepExecutor.

Covers all public methods and internal helpers:
- __init__: default view_tools, custom view_tools, null metrics fallback
- select_model_for_step: fast / deep_think / auto routing, failure fallback
- apply_step_result_payload (static): strict validation, best-effort dict
  extraction, last-resort fallback, edge cases
- track_sources_from_tool_event: delegation to SourceTracker
- track_multimodal_findings: filtering, counting, persistence trigger
- get_multimodal_findings: copy semantics
- clear: state reset
- _extract_multimodal_finding: file_view / browser_view / browser_agent_extract
  / unknown types, empty results
- _persist_key_findings: calls context_manager.add_observation, resets list
- _format_findings_for_context: formatting with source, preview, extracted_text
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

from app.domain.models.event import ToolEvent, ToolStatus
from app.domain.models.plan import Step
from app.domain.models.tool_name import ToolName
from app.domain.services.agents.step_executor import StepExecutor

# ──────────────────────────────────────────────────────────────────────────────
# Helpers / Factories
# ──────────────────────────────────────────────────────────────────────────────


def _make_step(
    *,
    success: bool = True,
    result: str | None = "ok",
    error: str | None = None,
    attachments: list[str] | None = None,
) -> MagicMock:
    """Create a MagicMock that behaves like a mutable Step."""
    step = MagicMock(spec=Step)
    step.success = success
    step.result = result
    step.error = error
    step.attachments = attachments or []
    return step


def _make_tool_event(
    function_name: str,
    function_args: dict[str, Any] | None = None,
    function_result: Any = None,
    status: ToolStatus = ToolStatus.CALLED,
    started_at: datetime | None = None,
) -> ToolEvent:
    """Build a minimal ToolEvent for tests."""
    return ToolEvent(
        tool_call_id="tc-test",
        tool_name="test_tool",
        function_name=function_name,
        function_args=function_args or {},
        status=status,
        function_result=function_result,
        started_at=started_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def _successful_func_result(
    message: str = "content here",
    data: dict | None = None,
) -> MagicMock:
    """A function_result object whose .success is True."""
    fr = MagicMock()
    fr.success = True
    fr.message = message
    fr.data = data or {}
    return fr


def _failed_func_result() -> MagicMock:
    """A function_result whose .success is False."""
    fr = MagicMock()
    fr.success = False
    fr.message = ""
    fr.data = {}
    return fr


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_context_manager() -> MagicMock:
    cm = MagicMock()
    cm.add_observation = MagicMock()
    return cm


@pytest.fixture
def mock_source_tracker() -> MagicMock:
    st = MagicMock()
    st.track_tool_event = MagicMock()
    return st


@pytest.fixture
def mock_metrics() -> MagicMock:
    return MagicMock()


@pytest.fixture
def executor(mock_context_manager, mock_source_tracker, mock_metrics) -> StepExecutor:
    """Default StepExecutor with all dependencies mocked."""
    return StepExecutor(
        context_manager=mock_context_manager,
        source_tracker=mock_source_tracker,
        metrics=mock_metrics,
    )


@pytest.fixture
def executor_custom_view_tools(mock_context_manager, mock_source_tracker) -> StepExecutor:
    """StepExecutor with an explicit custom view_tools set."""
    return StepExecutor(
        context_manager=mock_context_manager,
        source_tracker=mock_source_tracker,
        view_tools={"file_view", "browser_view"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# __init__ tests
# ──────────────────────────────────────────────────────────────────────────────


class TestStepExecutorInit:
    def test_default_view_tools_contains_standard_names(self, executor):
        assert ToolName.FILE_VIEW.value in executor._view_tools
        assert ToolName.BROWSER_VIEW.value in executor._view_tools
        assert ToolName.BROWSER_GET_CONTENT.value in executor._view_tools

    def test_custom_view_tools_are_respected(self, executor_custom_view_tools):
        assert executor_custom_view_tools._view_tools == frozenset({"file_view", "browser_view"})

    def test_initial_view_operation_count_is_zero(self, executor):
        assert executor._view_operation_count == 0

    def test_initial_multimodal_findings_is_empty(self, executor):
        assert executor._multimodal_findings == []

    def test_null_metrics_used_when_none_provided(self, mock_context_manager, mock_source_tracker):
        se = StepExecutor(
            context_manager=mock_context_manager,
            source_tracker=mock_source_tracker,
            metrics=None,
        )
        # Should not raise; get_null_metrics() returns a usable object
        assert se._metrics is not None

    def test_view_tools_accepts_plain_set(self, mock_context_manager, mock_source_tracker):
        plain_set = {"tool_a", "tool_b"}
        se = StepExecutor(
            context_manager=mock_context_manager,
            source_tracker=mock_source_tracker,
            view_tools=plain_set,
        )
        assert isinstance(se._view_tools, frozenset)
        assert se._view_tools == frozenset(plain_set)

    def test_empty_view_tools_falls_back_to_default(self, mock_context_manager, mock_source_tracker):
        """An empty set is falsy, so the impl falls back to ToolName._VIEW (same as None)."""
        se = StepExecutor(
            context_manager=mock_context_manager,
            source_tracker=mock_source_tracker,
            view_tools=set(),
        )
        # Falsy empty set → default ToolName._VIEW set is used
        assert ToolName.FILE_VIEW.value in se._view_tools


# ──────────────────────────────────────────────────────────────────────────────
# select_model_for_step tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSelectModelForStep:
    """Tests for select_model_for_step.

    ModelRouter, ModelTier, and get_model_router are imported lazily inside
    the method body via:
        from app.domain.services.agents.model_router import ModelRouter, ModelTier, get_model_router

    We must therefore patch them at their definition module, not at step_executor.
    """

    _MODULE = "app.domain.services.agents.model_router"

    def _make_router(self, model_name: str) -> MagicMock:
        config = MagicMock()
        config.model_name = model_name
        config.tier = MagicMock()
        config.tier.value = "balanced"
        config.temperature = 0.3
        config.max_tokens = 4096
        router = MagicMock()
        router.route.return_value = config
        return router

    def test_fast_thinking_mode_uses_fast_tier(self, executor):
        fast_router = self._make_router("fast-model")
        with (
            patch(f"{self._MODULE}.ModelRouter", return_value=fast_router),
            patch(f"{self._MODULE}.get_model_router"),
        ):
            result = executor.select_model_for_step("do something", user_thinking_mode="fast")

        assert result == "fast-model"

    def test_deep_think_mode_uses_powerful_tier(self, executor):
        powerful_router = self._make_router("powerful-model")
        with (
            patch(f"{self._MODULE}.ModelRouter", return_value=powerful_router),
            patch(f"{self._MODULE}.get_model_router"),
        ):
            result = executor.select_model_for_step("deep analysis", user_thinking_mode="deep_think")

        assert result == "powerful-model"

    def test_auto_mode_uses_singleton_router(self, executor):
        auto_router = self._make_router("auto-model")
        with (
            patch(f"{self._MODULE}.ModelRouter"),
            patch(f"{self._MODULE}.get_model_router", return_value=auto_router),
        ):
            result = executor.select_model_for_step("some step", user_thinking_mode=None)

        assert result == "auto-model"

    def test_none_thinking_mode_uses_auto_routing(self, executor):
        auto_router = self._make_router("default-model")
        with (
            patch(f"{self._MODULE}.ModelRouter"),
            patch(f"{self._MODULE}.get_model_router", return_value=auto_router),
        ):
            result = executor.select_model_for_step("regular step")

        assert result == "default-model"

    def test_routing_exception_returns_none(self, executor):
        with (
            patch(f"{self._MODULE}.ModelRouter", side_effect=RuntimeError("router broke")),
            patch(f"{self._MODULE}.get_model_router"),
        ):
            result = executor.select_model_for_step("failing step", user_thinking_mode="fast")

        assert result is None

    def test_auto_routing_exception_returns_none(self, executor):
        with (
            patch(f"{self._MODULE}.ModelRouter"),
            patch(f"{self._MODULE}.get_model_router", side_effect=ValueError("config missing")),
        ):
            result = executor.select_model_for_step("step desc", user_thinking_mode=None)

        assert result is None

    def test_unknown_thinking_mode_falls_through_to_auto(self, executor):
        """An unrecognised mode string (not 'fast' or 'deep_think') uses auto routing."""
        auto_router = self._make_router("fallback-model")
        with (
            patch(f"{self._MODULE}.ModelRouter"),
            patch(f"{self._MODULE}.get_model_router", return_value=auto_router),
        ):
            result = executor.select_model_for_step("step", user_thinking_mode="medium")

        assert result == "fallback-model"


# ──────────────────────────────────────────────────────────────────────────────
# apply_step_result_payload (static method) tests
# ──────────────────────────────────────────────────────────────────────────────


class TestApplyStepResultPayload:
    # ── Strict validation path ────────────────────────────────────────────

    def test_strict_success_sets_step_success_true(self):
        step = _make_step()
        payload = {"success": True, "result": "done", "attachments": [], "error": None}
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True
        assert step.success is True

    def test_strict_success_copies_result(self):
        step = _make_step()
        payload = {"success": True, "result": "my result", "attachments": []}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.result == "my result"

    def test_strict_success_uses_raw_when_result_is_none(self):
        step = _make_step()
        payload = {"success": True, "result": None, "attachments": []}
        StepExecutor.apply_step_result_payload(step, payload, "fallback raw text")
        assert step.result == "fallback raw text"

    def test_strict_success_copies_attachments(self):
        step = _make_step()
        payload = {"success": True, "result": "ok", "attachments": ["/tmp/file.txt"]}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.attachments == ["/tmp/file.txt"]

    def test_strict_success_clears_error(self):
        step = _make_step(error="prior error")
        payload = {"success": True, "result": "ok", "attachments": []}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error is None

    def test_strict_failure_sets_step_success_false(self):
        step = _make_step()
        payload = {"success": False, "result": None, "attachments": [], "error": "bad"}
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True
        assert step.success is False

    def test_strict_failure_sets_error_from_payload(self):
        step = _make_step()
        payload = {"success": False, "result": None, "attachments": [], "error": "Step failed cleanly"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error == "Step failed cleanly"

    def test_strict_failure_falls_back_to_default_error_when_error_field_none(self):
        step = _make_step(error=None)
        # Force spec=Step to not have a pre-existing error attribute
        step = MagicMock(spec=Step)
        step.error = None
        payload = {"success": False, "result": None, "attachments": [], "error": None}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error == "Step reported failure"

    def test_strict_failure_preserves_existing_step_error_when_payload_error_none(self):
        step = MagicMock(spec=Step)
        step.error = "pre-existing error"
        payload = {"success": False, "result": None, "attachments": [], "error": None}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error == "pre-existing error"

    def test_strict_failure_clears_result(self):
        step = _make_step(result="stale result")
        payload = {"success": False, "result": None, "attachments": [], "error": "oops"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.result is None

    def test_strict_extra_fields_are_ignored(self):
        """ExecutionStepResult has extra='ignore', so unknown keys should not fail."""
        step = _make_step()
        payload = {
            "success": True,
            "result": "done",
            "attachments": [],
            "thinking": "some chain-of-thought",
            "confidence": 0.99,
        }
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True
        assert step.success is True

    # ── Best-effort extraction path ───────────────────────────────────────

    def test_best_effort_dict_with_success_true(self):
        step = _make_step()
        # Trigger ValidationError by passing non-bool to strict model, then
        # ensure best-effort dict path handles it.
        # We can simulate this by passing a dict that Pydantic strict mode rejects:
        payload = {"success": 1, "result": "ok", "attachments": []}  # 1 is not strict bool
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True
        # Best-effort: success_value is not bool → fallback to False
        assert step.success is False

    def test_best_effort_dict_with_bool_true_success(self):
        step = _make_step()
        # Pass a dict that passes Pydantic strict model (bool is bool).
        # Use a genuinely invalid field type to trigger ValidationError then
        # test recovery. Inject bad nested type that strict rejects:
        payload = {"success": True, "result": 999, "attachments": "not-a-list"}
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        # Strict validation fails (result must be str|None, attachments must be list)
        # Best-effort: success=True (bool), result=str(999)="999"
        assert ok is True
        assert step.success is True
        assert step.result == "999"
        assert step.attachments == []

    def test_best_effort_dict_success_true_result_none_uses_raw(self):
        step = _make_step()
        # Force validation error via wrong type, then check best-effort fallback
        payload = {"success": True, "result": None, "attachments": "bad"}
        StepExecutor.apply_step_result_payload(step, payload, "fallback raw")
        # best-effort: success=True, result=None → use raw_message
        assert step.success is True
        assert step.result == "fallback raw"

    def test_best_effort_dict_success_false_sets_error(self):
        step = _make_step()
        payload = {"success": False, "result": None, "attachments": "bad", "error": "my error"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.success is False
        assert step.error == "my error"

    def test_best_effort_dict_success_false_no_error_field_uses_default(self):
        step = MagicMock(spec=Step)
        step.error = None
        payload = {"success": False, "result": None, "attachments": "bad"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error == "Step payload validation failed"

    def test_best_effort_dict_success_false_preserves_existing_step_error(self):
        step = MagicMock(spec=Step)
        step.error = "previous error"
        payload = {"success": False, "result": None, "attachments": "bad"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.error == "previous error"

    def test_best_effort_list_attachments_coerced_to_strings(self):
        step = _make_step()
        payload = {"success": True, "result": None, "attachments": [1, 2, "three"]}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.attachments == ["1", "2", "three"]

    def test_best_effort_non_list_attachments_reset_to_empty(self):
        step = _make_step()
        payload = {"success": True, "result": "ok", "attachments": "oops"}
        StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert step.attachments == []

    # ── Last-resort fallback path ─────────────────────────────────────────

    def test_last_resort_none_parsed_response_marks_failure(self):
        step = _make_step()
        ok = StepExecutor.apply_step_result_payload(step, None, "raw preview text")
        assert ok is False
        assert step.success is False
        assert step.result is None
        assert step.attachments == []

    def test_last_resort_raw_preview_included_in_error(self):
        step = _make_step()
        raw = "I have completed the research and found key insights."
        StepExecutor.apply_step_result_payload(step, None, raw)
        assert raw in step.error

    def test_last_resort_raw_preview_truncated_at_200_chars(self):
        step = _make_step()
        raw = "X" * 500
        StepExecutor.apply_step_result_payload(step, None, raw)
        assert "X" * 200 in step.error
        assert "X" * 201 not in step.error

    def test_last_resort_none_raw_message_generic_error(self):
        step = _make_step()
        StepExecutor.apply_step_result_payload(step, None, None)
        assert step.error == "Step response did not match expected JSON schema"

    def test_last_resort_empty_raw_message_generic_error(self):
        step = _make_step()
        StepExecutor.apply_step_result_payload(step, None, "")
        assert step.error == "Step response did not match expected JSON schema"

    def test_last_resort_whitespace_only_raw_message_generic_error(self):
        step = _make_step()
        StepExecutor.apply_step_result_payload(step, None, "   ")
        # strip() → empty → generic message
        assert step.error == "Step response did not match expected JSON schema"

    def test_last_resort_empty_dict_without_known_keys(self):
        step = _make_step()
        ok = StepExecutor.apply_step_result_payload(step, {}, "raw")
        # {} has no 'success', 'result', 'attachments' → goes to last-resort
        assert ok is False
        assert step.success is False

    def test_last_resort_integer_parsed_response(self):
        step = _make_step()
        ok = StepExecutor.apply_step_result_payload(step, 42, "raw preview")
        assert ok is False
        assert step.success is False

    def test_last_resort_string_parsed_response(self):
        step = _make_step()
        ok = StepExecutor.apply_step_result_payload(step, "not a dict", "raw preview")
        assert ok is False
        assert step.success is False

    def test_returns_true_only_on_strict_validation_pass(self):
        step = _make_step()
        payload = {"success": True, "result": "ok", "attachments": []}
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True

    def test_returns_true_on_best_effort_path(self):
        step = _make_step()
        payload = {"success": False, "result": None, "attachments": "bad"}
        ok = StepExecutor.apply_step_result_payload(step, payload, "raw")
        assert ok is True

    def test_returns_false_on_last_resort_path(self):
        step = _make_step()
        ok = StepExecutor.apply_step_result_payload(step, None, "raw")
        assert ok is False


# ──────────────────────────────────────────────────────────────────────────────
# track_sources_from_tool_event tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTrackSourcesFromToolEvent:
    def test_delegates_to_source_tracker(self, executor, mock_source_tracker):
        event = _make_tool_event("info_search_web")
        executor.track_sources_from_tool_event(event)
        mock_source_tracker.track_tool_event.assert_called_once_with(event)

    def test_passes_event_unchanged(self, executor, mock_source_tracker):
        event = _make_tool_event("browser_view", function_args={"url": "https://example.com"})
        executor.track_sources_from_tool_event(event)
        call_args = mock_source_tracker.track_tool_event.call_args[0]
        assert call_args[0] is event

    def test_delegates_multiple_events(self, executor, mock_source_tracker):
        for i in range(3):
            event = _make_tool_event(f"tool_{i}")
            executor.track_sources_from_tool_event(event)
        assert mock_source_tracker.track_tool_event.call_count == 3


# ──────────────────────────────────────────────────────────────────────────────
# track_multimodal_findings tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTrackMultimodalFindings:
    def test_non_view_tool_is_ignored(self, executor):
        event = _make_tool_event("shell_exec", function_result=_successful_func_result())
        executor.track_multimodal_findings(event)
        assert executor._view_operation_count == 0
        assert executor._multimodal_findings == []

    def test_failed_result_is_ignored(self, executor):
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=_failed_func_result())
        executor.track_multimodal_findings(event)
        assert executor._view_operation_count == 0

    def test_none_result_is_ignored(self, executor):
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=None)
        executor.track_multimodal_findings(event)
        assert executor._view_operation_count == 0

    def test_view_tool_increments_counter(self, executor):
        fr = _successful_func_result(message="preview content", data={"file_type": "pdf"})
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        executor.track_multimodal_findings(event)
        assert executor._view_operation_count == 1

    def test_two_view_ops_trigger_persistence(self, executor, mock_context_manager):
        fr = _successful_func_result(message="visible content")
        for _ in range(2):
            event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
            executor.track_multimodal_findings(event)

        # After 2 ops, counter resets to 0 and context_manager is called
        assert executor._view_operation_count == 0
        mock_context_manager.add_observation.assert_called_once()

    def test_counter_resets_after_persistence(self, executor, mock_context_manager):
        fr = _successful_func_result(message="content")
        for _ in range(2):
            event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
            executor.track_multimodal_findings(event)

        assert executor._view_operation_count == 0

    def test_findings_reset_after_persistence(self, executor, mock_context_manager):
        fr = _successful_func_result(message="some content preview here")
        for _ in range(2):
            event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
            executor.track_multimodal_findings(event)

        assert executor._multimodal_findings == []

    def test_one_op_does_not_trigger_persistence(self, executor, mock_context_manager):
        fr = _successful_func_result(message="content preview")
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        executor.track_multimodal_findings(event)
        mock_context_manager.add_observation.assert_not_called()

    def test_three_ops_trigger_exactly_one_persistence(self, executor, mock_context_manager):
        """After 2 ops persistence fires; 3rd op starts fresh counter."""
        fr = _successful_func_result(message="content preview here")
        for _ in range(3):
            event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
            executor.track_multimodal_findings(event)

        mock_context_manager.add_observation.assert_called_once()
        assert executor._view_operation_count == 1

    def test_custom_view_tools_respected(self, executor_custom_view_tools, mock_context_manager):
        """Only tools in the custom view_tools set should be tracked."""
        fr = _successful_func_result(message="browser content")
        # browser_view IS in custom set
        event_in = _make_tool_event("browser_view", function_result=fr)
        executor_custom_view_tools.track_multimodal_findings(event_in)
        assert executor_custom_view_tools._view_operation_count == 1

        # playwright_get_content is NOT in the custom set
        event_out = _make_tool_event("playwright_get_content", function_result=fr)
        executor_custom_view_tools.track_multimodal_findings(event_out)
        assert executor_custom_view_tools._view_operation_count == 1  # unchanged


# ──────────────────────────────────────────────────────────────────────────────
# get_multimodal_findings tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGetMultimodalFindings:
    def test_returns_empty_list_initially(self, executor):
        assert executor.get_multimodal_findings() == []

    def test_returns_copy_not_reference(self, executor):
        executor._multimodal_findings = [{"tool": "file_view", "type": "file_view"}]
        result = executor.get_multimodal_findings()
        result.append({"extra": "item"})
        # Internal list should not be affected
        assert len(executor._multimodal_findings) == 1

    def test_reflects_accumulated_findings(self, executor):
        executor._multimodal_findings = [{"tool": "a"}, {"tool": "b"}]
        assert len(executor.get_multimodal_findings()) == 2


# ──────────────────────────────────────────────────────────────────────────────
# clear tests
# ──────────────────────────────────────────────────────────────────────────────


class TestClear:
    def test_resets_view_operation_count(self, executor):
        executor._view_operation_count = 5
        executor.clear()
        assert executor._view_operation_count == 0

    def test_resets_multimodal_findings(self, executor):
        executor._multimodal_findings = [{"tool": "file_view"}]
        executor.clear()
        assert executor._multimodal_findings == []

    def test_clear_is_idempotent(self, executor):
        executor.clear()
        executor.clear()
        assert executor._view_operation_count == 0
        assert executor._multimodal_findings == []


# ──────────────────────────────────────────────────────────────────────────────
# _extract_multimodal_finding tests
# ──────────────────────────────────────────────────────────────────────────────


class TestExtractMultimodalFinding:
    def test_none_function_result_returns_none(self, executor):
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=None)
        result = executor._extract_multimodal_finding(event)
        assert result is None

    def test_file_view_produces_file_view_finding(self, executor):
        fr = _successful_func_result(
            message="text content preview",
            data={"file_type": "pdf", "extracted_text": "hello world"},
        )
        event = _make_tool_event(
            ToolName.FILE_VIEW.value,
            function_args={"file": "/path/to/doc.pdf"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["type"] == "file_view"
        assert finding["tool"] == ToolName.FILE_VIEW.value
        assert finding["source"] == "/path/to/doc.pdf"

    def test_file_view_captures_content_preview(self, executor):
        fr = _successful_func_result(message="A" * 600, data={"file_type": "txt"})
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        # Preview truncated to 500 chars
        assert len(finding["content_preview"]) <= 500

    def test_file_view_captures_extracted_text(self, executor):
        fr = _successful_func_result(
            message="some text",
            data={"file_type": "pdf", "extracted_text": "B" * 1200},
        )
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert "extracted_text" in finding
        assert len(finding["extracted_text"]) <= 1000

    def test_file_view_missing_extracted_text_not_in_finding(self, executor):
        fr = _successful_func_result(message="text", data={"file_type": "txt"})
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert "extracted_text" not in finding

    def test_browser_view_produces_browser_view_finding(self, executor):
        fr = _successful_func_result(message="page content")
        event = _make_tool_event(
            ToolName.BROWSER_VIEW.value,
            function_args={"url": "https://example.com"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["type"] == "browser_view"
        assert finding["url"] == "https://example.com"

    def test_browser_get_content_produces_browser_view_finding(self, executor):
        fr = _successful_func_result(message="page html")
        event = _make_tool_event(
            ToolName.BROWSER_GET_CONTENT.value,
            function_args={"url": "https://page.com"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["type"] == "browser_view"

    def test_browser_agent_extract_produces_extraction_finding(self, executor):
        fr = _successful_func_result(message="extracted data")
        event = _make_tool_event(
            ToolName.BROWSER_AGENT_EXTRACT.value,
            function_args={"goal": "Extract product prices"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["type"] == "extraction"
        assert finding["extraction_goal"] == "Extract product prices"

    def test_browser_agent_extract_result_truncated_to_1000(self, executor):
        fr = _successful_func_result(message="C" * 1500)
        event = _make_tool_event(
            ToolName.BROWSER_AGENT_EXTRACT.value,
            function_args={"goal": "get data"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert len(finding["result"]) <= 1000

    def test_finding_includes_timestamp(self, executor):
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        fr = _successful_func_result(message="content preview")
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr, started_at=ts)
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["timestamp"] == ts.isoformat()

    def test_finding_timestamp_none_when_started_at_missing(self, executor):
        fr = _successful_func_result(message="content here")
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        # Override started_at to None
        event.started_at = None  # type: ignore[assignment]
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["timestamp"] is None

    def test_source_from_url_arg_when_no_file_arg(self, executor):
        fr = _successful_func_result(message="page content preview here")
        event = _make_tool_event(
            ToolName.BROWSER_VIEW.value,
            function_args={"url": "https://example.com/page"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["source"] == "https://example.com/page"

    def test_source_prefers_file_over_url(self, executor):
        fr = _successful_func_result(message="file content here")
        event = _make_tool_event(
            ToolName.FILE_VIEW.value,
            function_args={"file": "/docs/report.pdf", "url": "https://ignored.com"},
            function_result=fr,
        )
        finding = executor._extract_multimodal_finding(event)
        assert finding is not None
        assert finding["source"] == "/docs/report.pdf"

    def test_returns_none_when_no_content_preview_or_result(self, executor):
        """A view event that extracts empty content should not produce a finding."""
        fr = _successful_func_result(message="", data={})
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        # Empty message → content_preview="" → finding returns None
        assert finding is None

    def test_function_result_with_result_attr_instead_of_data(self, executor):
        """Covers the `elif hasattr(func_result, 'result')` branch."""
        fr = MagicMock(spec=["success", "result"])
        fr.success = True
        fr.result = "my result content here for preview purposes and more"
        event = _make_tool_event(ToolName.BROWSER_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        # result attr used for content
        assert finding is not None

    def test_function_result_as_plain_dict(self, executor):
        """Covers the `else` branch when func_result is a dict."""
        fr = {"content_preview": "plain dict content here that is long enough to be preview"}
        event = _make_tool_event(ToolName.BROWSER_VIEW.value, function_result=fr)
        finding = executor._extract_multimodal_finding(event)
        # str(dict) gives some result; content_preview/result may be empty → None
        # We don't assert truthiness — just that no exception is raised
        assert finding is None or isinstance(finding, dict)


# ──────────────────────────────────────────────────────────────────────────────
# _persist_key_findings tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPersistKeyFindings:
    def test_does_nothing_when_findings_empty(self, executor, mock_context_manager):
        executor._persist_key_findings()
        mock_context_manager.add_observation.assert_not_called()

    def test_calls_add_observation_with_correct_type(self, executor, mock_context_manager):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "test preview"}]
        executor._persist_key_findings()
        call_kwargs = mock_context_manager.add_observation.call_args[1]
        assert call_kwargs.get("observation_type") == "multimodal_findings"

    def test_calls_add_observation_with_high_importance(self, executor, mock_context_manager):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "test"}]
        executor._persist_key_findings()
        call_kwargs = mock_context_manager.add_observation.call_args[1]
        assert call_kwargs.get("importance") == 0.8

    def test_resets_findings_after_persist(self, executor, mock_context_manager):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "content"}]
        executor._persist_key_findings()
        assert executor._multimodal_findings == []

    def test_content_argument_is_non_empty_string(self, executor, mock_context_manager):
        executor._multimodal_findings = [{"type": "browser_view", "content_preview": "some page"}]
        executor._persist_key_findings()
        call_kwargs = mock_context_manager.add_observation.call_args[1]
        assert isinstance(call_kwargs.get("content"), str)
        assert len(call_kwargs.get("content", "")) > 0


# ──────────────────────────────────────────────────────────────────────────────
# _format_findings_for_context tests
# ──────────────────────────────────────────────────────────────────────────────


class TestFormatFindingsForContext:
    def test_empty_findings_returns_empty_string(self, executor):
        result = executor._format_findings_for_context()
        assert result == ""

    def test_starts_with_header(self, executor):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "stuff"}]
        result = executor._format_findings_for_context()
        assert result.startswith("## Key Visual Findings")

    def test_numbered_findings(self, executor):
        executor._multimodal_findings = [
            {"type": "file_view", "content_preview": "content one"},
            {"type": "browser_view", "content_preview": "content two"},
        ]
        result = executor._format_findings_for_context()
        assert "Finding 1:" in result
        assert "Finding 2:" in result

    def test_source_included_when_present(self, executor):
        executor._multimodal_findings = [
            {"type": "file_view", "source": "/docs/report.pdf", "content_preview": "preview text"}
        ]
        result = executor._format_findings_for_context()
        assert "/docs/report.pdf" in result

    def test_url_used_as_source_fallback(self, executor):
        executor._multimodal_findings = [
            {
                "type": "browser_view",
                "url": "https://example.com",
                "source": "",
                "content_preview": "content here",
            }
        ]
        result = executor._format_findings_for_context()
        assert any(urlparse(token.strip("()[]<>,.;!?")).netloc == "example.com" for token in result.split())

    def test_content_preview_included_and_truncated(self, executor):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "D" * 400}]
        result = executor._format_findings_for_context()
        # Formatting truncates to 300 chars
        assert "D" * 300 in result
        assert "D" * 301 not in result

    def test_result_field_shown_when_no_content_preview(self, executor):
        executor._multimodal_findings = [
            {"type": "extraction", "result": "extracted value here", "extraction_goal": "get data"}
        ]
        result = executor._format_findings_for_context()
        assert "extracted value here" in result

    def test_extracted_text_included_when_present(self, executor):
        executor._multimodal_findings = [
            {
                "type": "file_view",
                "content_preview": "preview",
                "extracted_text": "verbatim text from pdf",
            }
        ]
        result = executor._format_findings_for_context()
        assert "verbatim text from pdf" in result

    def test_extracted_text_truncated_to_200(self, executor):
        executor._multimodal_findings = [
            {
                "type": "file_view",
                "content_preview": "preview",
                "extracted_text": "E" * 300,
            }
        ]
        result = executor._format_findings_for_context()
        assert "E" * 200 in result
        assert "E" * 201 not in result

    def test_finding_without_source_omits_source_line(self, executor):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": "content"}]
        result = executor._format_findings_for_context()
        assert "**Source:**" not in result

    def test_multiple_findings_all_rendered(self, executor):
        executor._multimodal_findings = [{"type": "file_view", "content_preview": f"content {i}"} for i in range(3)]
        result = executor._format_findings_for_context()
        assert "Finding 1:" in result
        assert "Finding 2:" in result
        assert "Finding 3:" in result


# ──────────────────────────────────────────────────────────────────────────────
# Integration-style: full track_multimodal_findings → persist pipeline
# ──────────────────────────────────────────────────────────────────────────────


class TestMultimodalFindingsPipeline:
    def test_two_file_view_ops_persist_and_reset(self, executor, mock_context_manager):
        fr = _successful_func_result(message="text preview content for file")
        for _ in range(2):
            event = _make_tool_event(
                ToolName.FILE_VIEW.value,
                function_args={"file": "/doc.pdf"},
                function_result=fr,
            )
            executor.track_multimodal_findings(event)

        mock_context_manager.add_observation.assert_called_once()
        args = mock_context_manager.add_observation.call_args[1]
        assert args["observation_type"] == "multimodal_findings"
        # After persist, counter and findings are reset
        assert executor._view_operation_count == 0
        assert executor._multimodal_findings == []

    def test_browser_view_finding_captured_in_context(self, executor, mock_context_manager):
        fr = _successful_func_result(message="browser page content preview here")
        for _ in range(2):
            event = _make_tool_event(
                ToolName.BROWSER_VIEW.value,
                function_args={"url": "https://test.com"},
                function_result=fr,
            )
            executor.track_multimodal_findings(event)

        content_arg = mock_context_manager.add_observation.call_args[1]["content"]
        assert "browser_view" in content_arg

    def test_clear_then_track_starts_fresh(self, executor, mock_context_manager):
        fr = _successful_func_result(message="first content preview")
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        executor.track_multimodal_findings(event)
        executor.clear()
        assert executor._view_operation_count == 0
        assert executor._multimodal_findings == []

        # Now track two more without the first counting
        fr2 = _successful_func_result(message="second content preview here")
        for _ in range(2):
            event2 = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr2)
            executor.track_multimodal_findings(event2)

        mock_context_manager.add_observation.assert_called_once()

    def test_get_findings_between_ops_returns_accumulated(self, executor):
        fr = _successful_func_result(message="content preview for test")
        event = _make_tool_event(ToolName.FILE_VIEW.value, function_result=fr)
        executor.track_multimodal_findings(event)
        findings = executor.get_multimodal_findings()
        assert len(findings) == 1
        assert findings[0]["type"] == "file_view"
