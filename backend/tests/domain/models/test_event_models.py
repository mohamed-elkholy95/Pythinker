"""Tests for app.domain.models.event — all enums, base models, content models, and events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domain.models.event import (
    AgentEvent,
    BaseEvent,
    BrowserToolContent,
    BudgetEvent,
    CanvasUpdateEvent,
    ChartToolContent,
    CheckpointSavedEvent,
    CodeExecutorToolContent,
    ComprehensionEvent,
    ConfidenceEvent,
    CouponItem,
    DatasourceEvent,
    DealItem,
    DealToolContent,
    DoneEvent,
    ErrorEvent,
    EvalMetricsEvent,
    FileToolContent,
    FlowSelectionEvent,
    FlowTransitionEvent,
    GitToolContent,
    IdleEvent,
    KnowledgeEvent,
    MCPHealthEvent,
    MessageEvent,
    ModeChangeEvent,
    MultiTaskEvent,
    PartialResultEvent,
    PathEvent,
    PhaseEvent,
    PhaseStatus,
    PhaseTransitionEvent,
    PlanningPhase,
    PlanStatus,
    ProgressEvent,
    ReflectionEvent,
    ReflectionStatus,
    ReportEvent,
    ResearchModeEvent,
    SearchToolContent,
    ShellToolContent,
    SkillActivationEvent,
    SkillDeliveryEvent,
    SkillEvent,
    StepStatus,
    StreamEvent,
    SuggestionEvent,
    TaskRecreationEvent,
    ThoughtEvent,
    ThoughtStatus,
    ToolEvent,
    ToolProgressEvent,
    ToolStatus,
    ToolStreamEvent,
    VerificationEvent,
    VerificationStatus,
    WaitEvent,
    WideResearchEvent,
    WideResearchStatus,
    WorkspaceEvent,
)
from app.domain.models.search import SearchResultItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_agent_event_adapter: TypeAdapter[AgentEvent] = TypeAdapter(AgentEvent)  # type: ignore[type-arg]


def _make_search_result(**kwargs: Any) -> SearchResultItem:
    defaults: dict[str, Any] = {"title": "T", "link": "https://example.com", "snippet": "S"}
    defaults.update(kwargs)
    return SearchResultItem(**defaults)


# ===========================================================================
# 1. Enum Classes
# ===========================================================================


class TestThoughtStatus:
    def test_values_exist(self) -> None:
        assert ThoughtStatus.THINKING == "thinking"
        assert ThoughtStatus.THOUGHT == "thought"
        assert ThoughtStatus.CHAIN_COMPLETE == "chain_complete"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ThoughtStatus.THINKING, str)

    def test_value_representation(self) -> None:
        assert ThoughtStatus.THINKING.value == "thinking"
        assert ThoughtStatus.CHAIN_COMPLETE.value == "chain_complete"

    def test_all_members_count(self) -> None:
        assert len(ThoughtStatus) == 3


class TestPlanStatus:
    def test_values_exist(self) -> None:
        assert PlanStatus.CREATED == "created"
        assert PlanStatus.UPDATED == "updated"
        assert PlanStatus.COMPLETED == "completed"

    def test_is_str_subclass(self) -> None:
        assert isinstance(PlanStatus.CREATED, str)

    def test_all_members_count(self) -> None:
        assert len(PlanStatus) == 3


class TestStepStatus:
    def test_values_exist(self) -> None:
        assert StepStatus.STARTED == "started"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.COMPLETED == "completed"

    def test_is_str_subclass(self) -> None:
        assert isinstance(StepStatus.FAILED, str)

    def test_all_members_count(self) -> None:
        assert len(StepStatus) == 4


class TestToolStatus:
    def test_values_exist(self) -> None:
        assert ToolStatus.CALLING == "calling"
        assert ToolStatus.CALLED == "called"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ToolStatus.CALLING, str)

    def test_all_members_count(self) -> None:
        assert len(ToolStatus) == 2


class TestPhaseStatus:
    def test_values_exist(self) -> None:
        assert PhaseStatus.STARTED == "started"
        assert PhaseStatus.COMPLETED == "completed"
        assert PhaseStatus.SKIPPED == "skipped"

    def test_is_str_subclass(self) -> None:
        assert isinstance(PhaseStatus.SKIPPED, str)

    def test_all_members_count(self) -> None:
        assert len(PhaseStatus) == 3


class TestPlanningPhase:
    def test_all_nine_values_exist(self) -> None:
        assert PlanningPhase.RECEIVED == "received"
        assert PlanningPhase.ANALYZING == "analyzing"
        assert PlanningPhase.PLANNING == "planning"
        assert PlanningPhase.FINALIZING == "finalizing"
        assert PlanningPhase.HEARTBEAT == "heartbeat"
        assert PlanningPhase.WAITING == "waiting"
        assert PlanningPhase.VERIFYING == "verifying"
        assert PlanningPhase.EXECUTING_SETUP == "executing_setup"
        assert PlanningPhase.TOOL_EXECUTING == "tool_executing"

    def test_is_str_subclass(self) -> None:
        assert isinstance(PlanningPhase.HEARTBEAT, str)

    def test_all_members_count(self) -> None:
        assert len(PlanningPhase) == 9


class TestVerificationStatus:
    def test_all_four_values(self) -> None:
        assert VerificationStatus.STARTED == "started"
        assert VerificationStatus.PASSED == "passed"
        assert VerificationStatus.REVISION_NEEDED == "revision_needed"
        assert VerificationStatus.FAILED == "failed"

    def test_is_str_subclass(self) -> None:
        assert isinstance(VerificationStatus.PASSED, str)

    def test_all_members_count(self) -> None:
        assert len(VerificationStatus) == 4


class TestReflectionStatus:
    def test_both_values(self) -> None:
        assert ReflectionStatus.TRIGGERED == "triggered"
        assert ReflectionStatus.COMPLETED == "completed"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ReflectionStatus.TRIGGERED, str)

    def test_all_members_count(self) -> None:
        assert len(ReflectionStatus) == 2


class TestWideResearchStatus:
    def test_all_five_values(self) -> None:
        assert WideResearchStatus.PENDING == "pending"
        assert WideResearchStatus.SEARCHING == "searching"
        assert WideResearchStatus.AGGREGATING == "aggregating"
        assert WideResearchStatus.COMPLETED == "completed"
        assert WideResearchStatus.FAILED == "failed"

    def test_is_str_subclass(self) -> None:
        assert isinstance(WideResearchStatus.AGGREGATING, str)

    def test_all_members_count(self) -> None:
        assert len(WideResearchStatus) == 5


# ===========================================================================
# 2. BaseEvent
# ===========================================================================


class TestBaseEvent:
    def test_type_is_empty_string(self) -> None:
        event = BaseEvent()
        assert event.type == ""

    def test_auto_generates_uuid_id(self) -> None:
        event = BaseEvent()
        # Should be a valid UUID string
        parsed = uuid.UUID(event.id)
        assert str(parsed) == event.id

    def test_unique_ids_each_instance(self) -> None:
        a = BaseEvent()
        b = BaseEvent()
        assert a.id != b.id

    def test_timestamp_is_utc_aware(self) -> None:
        event = BaseEvent()
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == UTC

    def test_timestamp_is_recent(self) -> None:
        before = datetime.now(UTC)
        event = BaseEvent()
        after = datetime.now(UTC)
        assert before <= event.timestamp <= after

    def test_custom_id_accepted(self) -> None:
        custom = "custom-id-123"
        event = BaseEvent(id=custom)
        assert event.id == custom


# ===========================================================================
# 3. ErrorEvent
# ===========================================================================


class TestErrorEvent:
    def test_type_literal(self) -> None:
        event = ErrorEvent(error="something broke")
        assert event.type == "error"

    def test_recoverable_default_true(self) -> None:
        event = ErrorEvent(error="oops")
        assert event.recoverable is True

    def test_severity_default_error(self) -> None:
        event = ErrorEvent(error="oops")
        assert event.severity == "error"

    def test_can_resume_default_false(self) -> None:
        event = ErrorEvent(error="oops")
        assert event.can_resume is False

    def test_optional_fields_default_none(self) -> None:
        event = ErrorEvent(error="oops")
        assert event.error_type is None
        assert event.retry_hint is None
        assert event.error_code is None
        assert event.error_category is None
        assert event.retry_after_ms is None
        assert event.checkpoint_event_id is None
        assert event.details is None

    def test_all_fields_accepted(self) -> None:
        event = ErrorEvent(
            error="timeout",
            error_type="timeout",
            recoverable=False,
            retry_hint="Try again later",
            error_code="ERR_TIMEOUT",
            error_category="transport",
            severity="critical",
            retry_after_ms=5000,
            can_resume=True,
            checkpoint_event_id="evt-abc",
            details={"trace": "..."},
        )
        assert event.error == "timeout"
        assert event.severity == "critical"
        assert event.retry_after_ms == 5000
        assert event.can_resume is True
        assert event.details == {"trace": "..."}

    def test_inherits_base_event_fields(self) -> None:
        event = ErrorEvent(error="fail")
        assert hasattr(event, "id")
        assert hasattr(event, "timestamp")


# ===========================================================================
# 4. ToolContent Models
# ===========================================================================


class TestBrowserToolContent:
    def test_all_fields_optional(self) -> None:
        content = BrowserToolContent()
        assert content.screenshot is None
        assert content.content is None

    def test_fields_accepted(self) -> None:
        content = BrowserToolContent(screenshot="base64data", content="<html/>")
        assert content.screenshot == "base64data"
        assert content.content == "<html/>"


class TestSearchToolContent:
    def test_minimal_construction(self) -> None:
        results = [_make_search_result()]
        content = SearchToolContent(results=results)
        assert len(content.results) == 1
        assert content.provider is None
        assert content.search_depth is None
        assert content.credits_used is None
        assert content.intent_tier is None

    def test_all_fields_accepted(self) -> None:
        content = SearchToolContent(
            results=[],
            provider="serper",
            search_depth="advanced",
            credits_used=10,
            intent_tier="DEEP",
        )
        assert content.provider == "serper"
        assert content.credits_used == 10


class TestShellToolContent:
    def test_console_as_list(self) -> None:
        content = ShellToolContent(console=[{"line": "output"}])
        assert isinstance(content.console, list)

    def test_console_as_string(self) -> None:
        content = ShellToolContent(console="hello world")
        assert content.console == "hello world"


class TestFileToolContent:
    def test_required_content_field(self) -> None:
        content = FileToolContent(content="file contents here")
        assert content.content == "file contents here"

    def test_missing_content_raises(self) -> None:
        with pytest.raises(ValidationError):
            FileToolContent()  # type: ignore[call-arg]


class TestGitToolContent:
    def test_minimal_construction(self) -> None:
        content = GitToolContent(operation="status")
        assert content.operation == "status"
        assert content.output is None
        assert content.repo_path is None
        assert content.branch is None
        assert content.commits is None
        assert content.diff_content is None

    def test_all_fields_accepted(self) -> None:
        content = GitToolContent(
            operation="log",
            output="abc123 message",
            repo_path="/repo",
            branch="main",
            commits=[{"hash": "abc123"}],
            diff_content="--- a\n+++ b",
        )
        assert content.branch == "main"
        assert content.commits is not None
        assert len(content.commits) == 1


class TestCodeExecutorToolContent:
    def test_minimal_construction(self) -> None:
        content = CodeExecutorToolContent(language="python")
        assert content.language == "python"
        assert content.code is None
        assert content.output is None
        assert content.error is None
        assert content.exit_code is None
        assert content.execution_time_ms is None
        assert content.artifacts is None

    def test_all_fields_accepted(self) -> None:
        content = CodeExecutorToolContent(
            language="python",
            code="print('hello')",
            output="hello",
            error=None,
            exit_code=0,
            execution_time_ms=42,
            artifacts=[{"path": "output.csv"}],
        )
        assert content.exit_code == 0
        assert content.execution_time_ms == 42


class TestChartToolContent:
    def test_minimal_construction(self) -> None:
        content = ChartToolContent(chart_type="bar", title="Revenue")
        assert content.chart_type == "bar"
        assert content.title == "Revenue"
        assert content.data_points == 0
        assert content.series_count == 0
        assert content.html_file_id is None
        assert content.png_file_id is None
        assert content.error is None

    def test_all_fields_accepted(self) -> None:
        content = ChartToolContent(
            chart_type="line",
            title="Trend",
            html_file_id="file-abc",
            png_file_id="file-def",
            html_filename="chart.html",
            png_filename="chart.png",
            html_size=4096,
            data_points=100,
            series_count=3,
            execution_time_ms=250,
            error=None,
        )
        assert content.data_points == 100
        assert content.html_filename == "chart.html"


class TestDealItemImageUrlValidator:
    def test_none_passthrough(self) -> None:
        item = DealItem(image_url=None)
        assert item.image_url is None

    def test_str_passthrough(self) -> None:
        item = DealItem(image_url="https://example.com/img.jpg")
        assert item.image_url == "https://example.com/img.jpg"

    def test_dict_with_url_key(self) -> None:
        item = DealItem(image_url={"url": "https://example.com/img.jpg"})  # type: ignore[arg-type]
        assert item.image_url == "https://example.com/img.jpg"

    def test_dict_with_content_url_key(self) -> None:
        item = DealItem(image_url={"contentUrl": "https://example.com/img2.jpg"})  # type: ignore[arg-type]
        assert item.image_url == "https://example.com/img2.jpg"

    def test_dict_without_url_keys_returns_none(self) -> None:
        item = DealItem(image_url={"other": "value"})  # type: ignore[arg-type]
        assert item.image_url is None

    def test_unexpected_type_returns_none(self) -> None:
        item = DealItem(image_url=12345)  # type: ignore[arg-type]
        assert item.image_url is None


class TestDealItemDefaults:
    def test_defaults(self) -> None:
        item = DealItem()
        assert item.store == ""
        assert item.product_name == ""
        assert item.url == ""
        assert item.item_category == "unknown"
        assert item.price is None
        assert item.score is None
        assert item.in_stock is None
        assert item.coupon_code is None


class TestCouponItemDefaults:
    def test_defaults(self) -> None:
        coupon = CouponItem()
        assert coupon.code == ""
        assert coupon.description == ""
        assert coupon.store == ""
        assert coupon.expiry is None
        assert coupon.verified is False
        assert coupon.source == ""
        assert coupon.item_category == "unknown"
        assert coupon.source_url is None


class TestDealToolContent:
    def test_minimal_construction(self) -> None:
        content = DealToolContent()
        assert content.deals == []
        assert content.coupons == []
        assert content.query == ""
        assert content.best_deal_index is None
        assert content.searched_stores == []
        assert content.store_errors == []
        assert content.empty_reason is None
        assert content.stores_attempted is None
        assert content.stores_with_results is None

    def test_with_nested_deals_and_coupons(self) -> None:
        deal = DealItem(store="Amazon", price=9.99)
        coupon = CouponItem(code="SAVE10", store="Amazon")
        content = DealToolContent(
            deals=[deal],
            coupons=[coupon],
            query="laptop",
            best_deal_index=0,
            searched_stores=["Amazon"],
        )
        assert len(content.deals) == 1
        assert content.deals[0].store == "Amazon"
        assert len(content.coupons) == 1
        assert content.coupons[0].code == "SAVE10"


# ===========================================================================
# 5. Core Events — type field and required args
# ===========================================================================


class TestToolEvent:
    def _minimal(self) -> ToolEvent:
        return ToolEvent(
            tool_call_id="call-1",
            tool_name="browser",
            function_name="navigate",
            function_args={"url": "https://example.com"},
            status=ToolStatus.CALLING,
        )

    def test_type_literal(self) -> None:
        assert self._minimal().type == "tool"

    def test_required_fields_set(self) -> None:
        event = self._minimal()
        assert event.tool_call_id == "call-1"
        assert event.function_name == "navigate"
        assert event.status == ToolStatus.CALLING

    def test_optional_fields_default_none(self) -> None:
        event = self._minimal()
        assert event.tool_content is None
        assert event.function_result is None
        assert event.call_status is None
        assert event.sequence_number is None
        assert event.duration_ms is None
        assert event.display_command is None


class TestToolProgressEvent:
    def test_type_literal(self) -> None:
        event = ToolProgressEvent(
            tool_call_id="call-1",
            tool_name="browser",
            function_name="navigate",
            progress_percent=50,
            current_step="Loading page",
        )
        assert event.type == "tool_progress"

    def test_defaults(self) -> None:
        event = ToolProgressEvent(
            tool_call_id="call-1",
            tool_name="browser",
            function_name="navigate",
            progress_percent=0,
            current_step="Starting",
        )
        assert event.steps_completed == 0
        assert event.steps_total is None
        assert event.elapsed_ms == 0
        assert event.estimated_remaining_ms is None
        assert event.checkpoint_id is None


class TestToolStreamEvent:
    def test_type_literal(self) -> None:
        event = ToolStreamEvent(
            tool_call_id="call-1",
            tool_name="file_write",
            function_name="write_file",
            partial_content="partial content...",
        )
        assert event.type == "tool_stream"

    def test_defaults(self) -> None:
        event = ToolStreamEvent(
            tool_call_id="call-1",
            tool_name="file_write",
            function_name="write_file",
            partial_content="...",
        )
        assert event.content_type == "text"
        assert event.is_final is False


class TestMessageEvent:
    def test_type_literal(self) -> None:
        event = MessageEvent(message="Hello")
        assert event.type == "message"

    def test_role_default_assistant(self) -> None:
        event = MessageEvent(message="Hello")
        assert event.role == "assistant"

    def test_role_user_accepted(self) -> None:
        event = MessageEvent(message="Hello", role="user")
        assert event.role == "user"

    def test_optional_fields_default_none(self) -> None:
        event = MessageEvent(message="Hi")
        assert event.attachments is None
        assert event.delivery_metadata is None
        assert event.skills is None
        assert event.thinking_mode is None
        assert event.follow_up_selected_suggestion is None


class TestDoneEvent:
    def test_type_literal(self) -> None:
        assert DoneEvent().type == "done"

    def test_inherits_base_id_timestamp(self) -> None:
        event = DoneEvent()
        assert hasattr(event, "id")
        assert hasattr(event, "timestamp")


class TestWaitEvent:
    def test_type_literal(self) -> None:
        assert WaitEvent().type == "wait"

    def test_optional_fields_default_none(self) -> None:
        event = WaitEvent()
        assert event.wait_reason is None
        assert event.suggest_user_takeover is None


class TestIdleEvent:
    def test_type_literal(self) -> None:
        assert IdleEvent().type == "idle"

    def test_optional_reason(self) -> None:
        event = IdleEvent(reason="session_expired")
        assert event.reason == "session_expired"

    def test_reason_default_none(self) -> None:
        assert IdleEvent().reason is None


class TestStreamEvent:
    def test_type_literal(self) -> None:
        event = StreamEvent(content="chunk")
        assert event.type == "stream"

    def test_phase_default_thinking(self) -> None:
        event = StreamEvent(content="chunk")
        assert event.phase == "thinking"

    def test_lane_default_answer(self) -> None:
        event = StreamEvent(content="chunk")
        assert event.lane == "answer"

    def test_is_final_default_false(self) -> None:
        event = StreamEvent(content="chunk")
        assert event.is_final is False

    def test_all_fields_accepted(self) -> None:
        event = StreamEvent(
            content="done",
            is_final=True,
            phase="summarizing",
            lane="reasoning",
        )
        assert event.is_final is True
        assert event.lane == "reasoning"


class TestProgressEvent:
    def test_type_literal(self) -> None:
        event = ProgressEvent(phase=PlanningPhase.PLANNING, message="Generating plan")
        assert event.type == "progress"

    def test_required_fields(self) -> None:
        event = ProgressEvent(phase=PlanningPhase.ANALYZING, message="Analyzing task")
        assert event.phase == PlanningPhase.ANALYZING
        assert event.message == "Analyzing task"

    def test_optional_fields_default_none(self) -> None:
        event = ProgressEvent(phase=PlanningPhase.HEARTBEAT, message="Ping")
        assert event.estimated_steps is None
        assert event.progress_percent is None
        assert event.estimated_duration_seconds is None
        assert event.complexity_category is None
        assert event.wait_elapsed_seconds is None
        assert event.wait_stage is None


class TestReportEvent:
    def test_type_literal(self) -> None:
        event = ReportEvent(id="rpt-1", title="My Report", content="# Hello")
        assert event.type == "report"

    def test_required_fields(self) -> None:
        event = ReportEvent(id="rpt-1", title="Report", content="body")
        assert event.id == "rpt-1"
        assert event.title == "Report"
        assert event.content == "body"

    def test_optional_fields_default_none(self) -> None:
        event = ReportEvent(id="rpt-1", title="T", content="C")
        assert event.attachments is None
        assert event.sources is None


class TestSuggestionEvent:
    def test_type_literal(self) -> None:
        event = SuggestionEvent(suggestions=["Do X", "Do Y"])
        assert event.type == "suggestion"

    def test_required_suggestions_list(self) -> None:
        event = SuggestionEvent(suggestions=["A", "B", "C"])
        assert len(event.suggestions) == 3

    def test_optional_fields_default_none(self) -> None:
        event = SuggestionEvent(suggestions=["X"])
        assert event.source is None
        assert event.anchor_event_id is None
        assert event.anchor_excerpt is None


class TestBudgetEvent:
    def test_type_literal(self) -> None:
        event = BudgetEvent(
            action="warning",
            budget_limit=10.0,
            consumed=8.5,
            remaining=1.5,
            percentage_used=0.85,
        )
        assert event.type == "budget"

    def test_defaults(self) -> None:
        event = BudgetEvent(
            action="warning",
            budget_limit=5.0,
            consumed=4.0,
            remaining=1.0,
            percentage_used=0.80,
        )
        assert event.warning_threshold == 0.8
        assert event.session_paused is False


class TestWideResearchEvent:
    def test_type_literal(self) -> None:
        event = WideResearchEvent(
            research_id="r-1",
            topic="AI trends",
            status=WideResearchStatus.SEARCHING,
            total_queries=5,
        )
        assert event.type == "wide_research"

    def test_defaults(self) -> None:
        event = WideResearchEvent(
            research_id="r-1",
            topic="topic",
            status=WideResearchStatus.PENDING,
            total_queries=3,
        )
        assert event.completed_queries == 0
        assert event.sources_found == 0
        assert event.search_types == []
        assert event.current_query is None
        assert event.errors == []


class TestThoughtEvent:
    def test_type_literal(self) -> None:
        event = ThoughtEvent(status=ThoughtStatus.THINKING)
        assert event.type == "thought"

    def test_required_status(self) -> None:
        event = ThoughtEvent(status=ThoughtStatus.CHAIN_COMPLETE)
        assert event.status == ThoughtStatus.CHAIN_COMPLETE

    def test_optional_fields_default(self) -> None:
        event = ThoughtEvent(status=ThoughtStatus.THOUGHT)
        assert event.thought_type is None
        assert event.content is None
        assert event.confidence is None
        assert event.step_name is None
        assert event.chain_id is None
        assert event.is_final is False


class TestConfidenceEvent:
    def test_type_literal(self) -> None:
        event = ConfidenceEvent(
            decision="proceed",
            confidence=0.9,
            level="high",
            action_recommendation="proceed",
        )
        assert event.type == "confidence"

    def test_defaults(self) -> None:
        event = ConfidenceEvent(
            decision="verify",
            confidence=0.5,
            level="medium",
            action_recommendation="verify",
        )
        assert event.supporting_factors == []
        assert event.risk_factors == []


class TestFlowSelectionEvent:
    def test_type_literal(self) -> None:
        event = FlowSelectionEvent(flow_mode="plan_act")
        assert event.type == "flow_selection"

    def test_optional_fields_default_none(self) -> None:
        event = FlowSelectionEvent(flow_mode="coordinator")
        assert event.model is None
        assert event.session_id is None
        assert event.reason is None


class TestVerificationEvent:
    def test_type_literal(self) -> None:
        event = VerificationEvent(status=VerificationStatus.PASSED)
        assert event.type == "verification"

    def test_optional_fields(self) -> None:
        event = VerificationEvent(status=VerificationStatus.REVISION_NEEDED)
        assert event.verdict is None
        assert event.confidence is None
        assert event.summary is None
        assert event.revision_feedback is None


class TestReflectionEvent:
    def test_type_literal(self) -> None:
        event = ReflectionEvent(status=ReflectionStatus.TRIGGERED)
        assert event.type == "reflection"

    def test_optional_fields_default_none(self) -> None:
        event = ReflectionEvent(status=ReflectionStatus.COMPLETED)
        assert event.decision is None
        assert event.confidence is None
        assert event.summary is None
        assert event.trigger_reason is None


class TestPartialResultEvent:
    def test_type_literal(self) -> None:
        event = PartialResultEvent(
            step_index=0,
            step_title="Research step",
            headline="Found 10 results",
        )
        assert event.type == "partial_result"

    def test_sources_count_default(self) -> None:
        event = PartialResultEvent(
            step_index=1,
            step_title="Step 2",
            headline="Headline",
        )
        assert event.sources_count == 0


class TestSkillEvent:
    def test_type_literal(self) -> None:
        event = SkillEvent(
            skill_id="skill-1",
            skill_name="SEO Analyzer",
            action="activated",
            reason="user request",
        )
        assert event.type == "skill"

    def test_tools_affected_default_none(self) -> None:
        event = SkillEvent(
            skill_id="skill-1",
            skill_name="SEO Analyzer",
            action="matched",
            reason="keyword match",
        )
        assert event.tools_affected is None


class TestPhaseEvent:
    def test_type_literal(self) -> None:
        event = PhaseEvent(
            phase_id="phase-1",
            phase_type="planning",
            label="Planning",
            status=PhaseStatus.STARTED,
        )
        assert event.type == "phase"

    def test_defaults(self) -> None:
        event = PhaseEvent(
            phase_id="p-1",
            phase_type="planning",
            label="Planning",
            status=PhaseStatus.COMPLETED,
        )
        assert event.order == 0
        assert event.icon == ""
        assert event.color == ""
        assert event.total_phases == 0
        assert event.skip_reason is None


class TestPhaseTransitionEvent:
    def test_type_literal(self) -> None:
        event = PhaseTransitionEvent(phase="planning")
        assert event.type == "phase_transition"

    def test_optional_fields(self) -> None:
        event = PhaseTransitionEvent(phase="executing")
        assert event.label is None
        assert event.research_id is None
        assert event.source is None


class TestCheckpointSavedEvent:
    def test_type_literal(self) -> None:
        event = CheckpointSavedEvent(phase="phase-2")
        assert event.type == "checkpoint_saved"

    def test_optional_fields(self) -> None:
        event = CheckpointSavedEvent(phase="phase-1")
        assert event.research_id is None
        assert event.notes_preview is None
        assert event.source_count is None


class TestWorkspaceEvent:
    def test_type_literal(self) -> None:
        event = WorkspaceEvent(action="initialized")
        assert event.type == "workspace"

    def test_defaults(self) -> None:
        event = WorkspaceEvent(action="deliverables_ready")
        assert event.workspace_type is None
        assert event.workspace_path is None
        assert event.structure is None
        assert event.files_organized == 0
        assert event.deliverables_count == 0
        assert event.manifest_path is None


class TestCanvasUpdateEvent:
    def test_type_literal(self) -> None:
        event = CanvasUpdateEvent(
            project_id="proj-1",
            operation="add_element",
            version=2,
        )
        assert event.type == "canvas_update"

    def test_defaults(self) -> None:
        event = CanvasUpdateEvent(
            project_id="proj-1",
            operation="create_project",
            version=1,
        )
        assert event.session_id is None
        assert event.element_count == 0
        assert event.project_name is None
        assert event.changed_element_ids is None
        assert event.source is None


class TestFlowTransitionEvent:
    def test_type_literal(self) -> None:
        event = FlowTransitionEvent(from_state="PLANNING", to_state="EXECUTING")
        assert event.type == "flow_transition"

    def test_optional_fields(self) -> None:
        event = FlowTransitionEvent(from_state="IDLE", to_state="PLANNING")
        assert event.reason is None
        assert event.step_id is None
        assert event.elapsed_ms is None


class TestResearchModeEvent:
    def test_type_literal(self) -> None:
        event = ResearchModeEvent(research_mode="deep_research")
        assert event.type == "research_mode"

    def test_fast_search_mode(self) -> None:
        event = ResearchModeEvent(research_mode="fast_search")
        assert event.research_mode == "fast_search"


class TestEvalMetricsEvent:
    def test_type_literal(self) -> None:
        event = EvalMetricsEvent(metrics={"faithfulness": 0.9})
        assert event.type == "eval_metrics"

    def test_defaults(self) -> None:
        event = EvalMetricsEvent(metrics={})
        assert event.hallucination_score == 0.0
        assert event.passed is True


class TestComprehensionEvent:
    def test_type_literal(self) -> None:
        event = ComprehensionEvent(
            original_length=5000,
            summary="User wants a market analysis report",
        )
        assert event.type == "comprehension"

    def test_optional_fields_default_none(self) -> None:
        event = ComprehensionEvent(original_length=1000, summary="Summary")
        assert event.key_requirements is None
        assert event.complexity_score is None


class TestTaskRecreationEvent:
    def test_type_literal(self) -> None:
        event = TaskRecreationEvent(
            reason="new understanding",
            previous_step_count=3,
            new_step_count=5,
            preserved_findings=2,
        )
        assert event.type == "task_recreation"

    def test_all_required_fields(self) -> None:
        event = TaskRecreationEvent(
            reason="clarification received",
            previous_step_count=2,
            new_step_count=4,
            preserved_findings=1,
        )
        assert event.previous_step_count == 2
        assert event.new_step_count == 4
        assert event.preserved_findings == 1


class TestSkillDeliveryEvent:
    def test_type_literal(self) -> None:
        event = SkillDeliveryEvent(
            package_id="pkg-1",
            name="SEO Analyzer",
            description="Analyzes SEO factors",
        )
        assert event.type == "skill_delivery"

    def test_defaults(self) -> None:
        event = SkillDeliveryEvent(
            package_id="pkg-1",
            name="MySkill",
            description="Does stuff",
        )
        assert event.version == "1.0.0"
        assert event.icon == "puzzle"
        assert event.category == "custom"
        assert event.author is None
        assert event.file_tree == {}
        assert event.files == []
        assert event.file_id is None
        assert event.skill_id is None


class TestSkillActivationEvent:
    def test_type_literal(self) -> None:
        event = SkillActivationEvent()
        assert event.type == "skill_activation"

    def test_defaults(self) -> None:
        event = SkillActivationEvent()
        assert event.skill_ids == []
        assert event.skill_names == []
        assert event.tool_restrictions is None
        assert event.prompt_chars == 0
        assert event.activation_sources == {}
        assert event.command_skill_id is None
        assert event.auto_trigger_enabled is False


class TestMCPHealthEvent:
    def test_type_literal(self) -> None:
        event = MCPHealthEvent(server_name="context7", healthy=True)
        assert event.type == "mcp_health"

    def test_defaults(self) -> None:
        event = MCPHealthEvent(server_name="tavily", healthy=False)
        assert event.error is None
        assert event.tools_available == 0


class TestKnowledgeEvent:
    def test_type_literal(self) -> None:
        event = KnowledgeEvent(scope="user", content="User prefers dark mode")
        assert event.type == "knowledge"

    def test_required_fields(self) -> None:
        event = KnowledgeEvent(scope="global", content="Python 3.12 released")
        assert event.scope == "global"
        assert event.content == "Python 3.12 released"


class TestDatasourceEvent:
    def test_type_literal(self) -> None:
        event = DatasourceEvent(api_name="serper", documentation="API docs here")
        assert event.type == "datasource"

    def test_required_fields(self) -> None:
        event = DatasourceEvent(api_name="tavily", documentation="# Tavily Docs")
        assert event.api_name == "tavily"
        assert event.documentation == "# Tavily Docs"


class TestPathEvent:
    def test_type_literal(self) -> None:
        event = PathEvent(path_id="path-1", action="created")
        assert event.type == "path"

    def test_optional_fields_default_none(self) -> None:
        event = PathEvent(path_id="path-1", action="exploring")
        assert event.score is None
        assert event.description is None


class TestMultiTaskEvent:
    def test_type_literal(self) -> None:
        event = MultiTaskEvent(
            challenge_id="ch-1",
            action="started",
            current_task_index=0,
            total_tasks=3,
        )
        assert event.type == "multi_task"

    def test_defaults(self) -> None:
        event = MultiTaskEvent(
            challenge_id="ch-1",
            action="task_switching",
            current_task_index=1,
            total_tasks=3,
        )
        assert event.current_task is None
        assert event.progress_percentage == 0.0
        assert event.elapsed_time_seconds is None


class TestModeChangeEvent:
    def test_type_literal(self) -> None:
        event = ModeChangeEvent(mode="agent")
        assert event.type == "mode_change"

    def test_reason_default_none(self) -> None:
        event = ModeChangeEvent(mode="discuss")
        assert event.reason is None

    def test_reason_accepted(self) -> None:
        event = ModeChangeEvent(mode="agent", reason="user request")
        assert event.reason == "user request"


# ===========================================================================
# 6. AgentEvent discriminated union
# ===========================================================================


class TestAgentEventDiscriminatedUnion:
    def test_parses_error_event(self) -> None:
        raw: dict[str, Any] = {"type": "error", "error": "Something went wrong"}
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, ErrorEvent)
        assert event.type == "error"
        assert event.error == "Something went wrong"

    def test_parses_done_event(self) -> None:
        raw: dict[str, Any] = {"type": "done"}
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, DoneEvent)
        assert event.type == "done"

    def test_parses_progress_event(self) -> None:
        raw: dict[str, Any] = {
            "type": "progress",
            "phase": "planning",
            "message": "Creating plan",
        }
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, ProgressEvent)

    def test_parses_stream_event(self) -> None:
        raw: dict[str, Any] = {"type": "stream", "content": "hello"}
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, StreamEvent)

    def test_unknown_type_raises_validation_error(self) -> None:
        raw: dict[str, Any] = {"type": "nonexistent_type_xyz"}
        with pytest.raises(ValidationError):
            _agent_event_adapter.validate_python(raw)

    def test_parses_wide_research_event(self) -> None:
        raw: dict[str, Any] = {
            "type": "wide_research",
            "research_id": "r-1",
            "topic": "AI trends",
            "status": "searching",
            "total_queries": 5,
        }
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, WideResearchEvent)
        assert event.status == WideResearchStatus.SEARCHING

    def test_parses_budget_event(self) -> None:
        raw: dict[str, Any] = {
            "type": "budget",
            "action": "warning",
            "budget_limit": 10.0,
            "consumed": 8.0,
            "remaining": 2.0,
            "percentage_used": 0.80,
        }
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, BudgetEvent)

    def test_error_event_inherits_base_event_fields_via_union(self) -> None:
        event_id = str(uuid.uuid4())
        raw: dict[str, Any] = {
            "type": "error",
            "error": "test error",
            "id": event_id,
        }
        event = _agent_event_adapter.validate_python(raw)
        assert isinstance(event, ErrorEvent)
        assert event.id == event_id
