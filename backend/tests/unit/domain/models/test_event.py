"""Tests for event models (app.domain.models.event).

Covers BaseEvent, ErrorEvent, PlanEvent, ToolEvent, MessageEvent,
DoneEvent, ProgressEvent, ReportEvent, and key content models.
"""

from datetime import UTC, datetime

from app.domain.models.event import (
    AgentModeToolContent,
    BaseEvent,
    BrowserToolContent,
    ChartToolContent,
    CodeExecutorToolContent,
    ComprehensionEvent,
    DealItem,
    DealToolContent,
    DoneEvent,
    ErrorEvent,
    FileToolContent,
    GitToolContent,
    IdleEvent,
    MCPHealthEvent,
    MessageEvent,
    ModeChangeEvent,
    PhaseEvent,
    PhaseStatus,
    PlanningPhase,
    PlanStatus,
    ProgressEvent,
    ReportEvent,
    SearchToolContent,
    ShellToolContent,
    SkillDeliveryEvent,
    SkillPackageFileData,
    SkillToolContent,
    StepStatus,
    SuggestionEvent,
    TaskRecreationEvent,
    TestRunnerToolContent,
    ThoughtStatus,
    TitleEvent,
    ToolProgressEvent,
    ToolStatus,
    WaitEvent,
)


# ── Enums ────────────────────────────────────────────────────────────


class TestEventEnums:
    """Tests for event-related enums."""

    def test_thought_status_values(self) -> None:
        assert ThoughtStatus.THINKING == "thinking"
        assert ThoughtStatus.THOUGHT == "thought"
        assert ThoughtStatus.CHAIN_COMPLETE == "chain_complete"

    def test_plan_status_values(self) -> None:
        assert PlanStatus.CREATED == "created"
        assert PlanStatus.UPDATED == "updated"
        assert PlanStatus.COMPLETED == "completed"
        assert PlanStatus.RUNNING == "running"
        assert PlanStatus.FINISHED == "finished"

    def test_step_status_values(self) -> None:
        assert StepStatus.STARTED == "started"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.COMPLETED == "completed"

    def test_tool_status_values(self) -> None:
        assert ToolStatus.CALLING == "calling"
        assert ToolStatus.CALLED == "called"

    def test_phase_status_values(self) -> None:
        assert PhaseStatus.STARTED == "started"
        assert PhaseStatus.COMPLETED == "completed"
        assert PhaseStatus.SKIPPED == "skipped"

    def test_planning_phase_values(self) -> None:
        assert PlanningPhase.RECEIVED == "received"
        assert PlanningPhase.ANALYZING == "analyzing"
        assert PlanningPhase.PLANNING == "planning"
        assert PlanningPhase.FINALIZING == "finalizing"
        assert PlanningPhase.HEARTBEAT == "heartbeat"
        assert PlanningPhase.WAITING == "waiting"
        assert PlanningPhase.VERIFYING == "verifying"


# ── BaseEvent ────────────────────────────────────────────────────────


class TestBaseEvent:
    """Tests for BaseEvent model."""

    def test_default_fields(self) -> None:
        event = BaseEvent()
        assert event.type == ""
        assert event.id is not None
        assert len(event.id) > 0
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)

    def test_unique_ids(self) -> None:
        events = [BaseEvent() for _ in range(10)]
        ids = [e.id for e in events]
        assert len(ids) == len(set(ids))

    def test_timestamp_is_utc(self) -> None:
        event = BaseEvent()
        assert event.timestamp.tzinfo is not None


# ── ErrorEvent ───────────────────────────────────────────────────────


class TestErrorEvent:
    """Tests for ErrorEvent model."""

    def test_minimal_creation(self) -> None:
        event = ErrorEvent(error="Something went wrong")
        assert event.type == "error"
        assert event.error == "Something went wrong"
        assert event.recoverable is True
        assert event.severity == "error"

    def test_full_creation(self) -> None:
        event = ErrorEvent(
            error="Token limit exceeded",
            error_type="token_limit",
            recoverable=True,
            retry_hint="Try a simpler request",
            error_code="TOKEN_LIMIT",
            error_category="validation",
            severity="warning",
            retry_after_ms=5000,
            can_resume=True,
            checkpoint_event_id="evt-123",
            details={"tokens_used": 100000},
        )
        assert event.error_type == "token_limit"
        assert event.retry_hint == "Try a simpler request"
        assert event.error_code == "TOKEN_LIMIT"
        assert event.error_category == "validation"
        assert event.severity == "warning"
        assert event.retry_after_ms == 5000
        assert event.can_resume is True
        assert event.checkpoint_event_id == "evt-123"
        assert event.details == {"tokens_used": 100000}

    def test_non_recoverable_error(self) -> None:
        event = ErrorEvent(error="Fatal crash", recoverable=False)
        assert event.recoverable is False

    def test_default_optional_fields(self) -> None:
        event = ErrorEvent(error="test")
        assert event.error_type is None
        assert event.retry_hint is None
        assert event.error_code is None
        assert event.error_category is None
        assert event.retry_after_ms is None
        assert event.can_resume is False
        assert event.checkpoint_event_id is None
        assert event.details is None


# ── MessageEvent ─────────────────────────────────────────────────────


class TestMessageEvent:
    """Tests for MessageEvent model."""

    def test_assistant_message(self) -> None:
        event = MessageEvent(message="Hello there")
        assert event.type == "message"
        assert event.role == "assistant"
        assert event.message == "Hello there"

    def test_user_message(self) -> None:
        event = MessageEvent(role="user", message="Help me")
        assert event.role == "user"

    def test_optional_fields(self) -> None:
        event = MessageEvent(message="test")
        assert event.attachments is None
        assert event.delivery_metadata is None
        assert event.skills is None
        assert event.thinking_mode is None
        assert event.follow_up_selected_suggestion is None


# ── DoneEvent ────────────────────────────────────────────────────────


class TestDoneEvent:
    """Tests for DoneEvent model."""

    def test_creation(self) -> None:
        event = DoneEvent()
        assert event.type == "done"


# ── TitleEvent ───────────────────────────────────────────────────────


class TestTitleEvent:
    """Tests for TitleEvent model."""

    def test_creation(self) -> None:
        event = TitleEvent(title="Research Report")
        assert event.type == "title"
        assert event.title == "Research Report"


# ── WaitEvent ────────────────────────────────────────────────────────


class TestWaitEvent:
    """Tests for WaitEvent model."""

    def test_creation(self) -> None:
        event = WaitEvent()
        assert event.type == "wait"
        assert event.wait_reason is None
        assert event.suggest_user_takeover is None

    def test_with_reason(self) -> None:
        event = WaitEvent(wait_reason="captcha", suggest_user_takeover="browser")
        assert event.wait_reason == "captcha"
        assert event.suggest_user_takeover == "browser"


# ── ProgressEvent ────────────────────────────────────────────────────


class TestProgressEvent:
    """Tests for ProgressEvent model."""

    def test_creation(self) -> None:
        event = ProgressEvent(
            phase=PlanningPhase.ANALYZING,
            message="Analyzing your request...",
        )
        assert event.type == "progress"
        assert event.phase == PlanningPhase.ANALYZING
        assert event.message == "Analyzing your request..."

    def test_with_estimates(self) -> None:
        event = ProgressEvent(
            phase=PlanningPhase.PLANNING,
            message="Creating plan",
            estimated_steps=5,
            progress_percent=30,
            estimated_duration_seconds=120,
            complexity_category="complex",
        )
        assert event.estimated_steps == 5
        assert event.progress_percent == 30
        assert event.estimated_duration_seconds == 120
        assert event.complexity_category == "complex"


# ── ReportEvent ──────────────────────────────────────────────────────


class TestReportEvent:
    """Tests for ReportEvent model."""

    def test_creation(self) -> None:
        event = ReportEvent(
            id="rpt-1",
            title="Analysis Report",
            content="# Report\n\nFindings here...",
        )
        assert event.type == "report"
        assert event.id == "rpt-1"
        assert event.title == "Analysis Report"
        assert "# Report" in event.content


# ── SuggestionEvent ──────────────────────────────────────────────────


class TestSuggestionEvent:
    """Tests for SuggestionEvent model."""

    def test_creation(self) -> None:
        event = SuggestionEvent(suggestions=["Try A", "Try B", "Try C"])
        assert event.type == "suggestion"
        assert len(event.suggestions) == 3


# ── ComprehensionEvent ───────────────────────────────────────────────


class TestComprehensionEvent:
    """Tests for ComprehensionEvent model."""

    def test_creation(self) -> None:
        event = ComprehensionEvent(
            original_length=5000,
            summary="User wants to analyze market data",
            key_requirements=["data analysis", "visualization"],
            complexity_score=0.8,
        )
        assert event.type == "comprehension"
        assert event.original_length == 5000
        assert event.complexity_score == 0.8


# ── TaskRecreationEvent ─────────────────────────────────────────────


class TestTaskRecreationEvent:
    """Tests for TaskRecreationEvent model."""

    def test_creation(self) -> None:
        event = TaskRecreationEvent(
            reason="New requirements identified",
            previous_step_count=3,
            new_step_count=5,
            preserved_findings=2,
        )
        assert event.type == "task_recreation"
        assert event.previous_step_count == 3
        assert event.new_step_count == 5
        assert event.preserved_findings == 2


# ── PhaseEvent ───────────────────────────────────────────────────────


class TestPhaseEvent:
    """Tests for PhaseEvent model."""

    def test_creation(self) -> None:
        event = PhaseEvent(
            phase_id="phase-1",
            phase_type="research",
            label="Research Phase",
            status=PhaseStatus.STARTED,
            order=1,
            total_phases=4,
        )
        assert event.type == "phase"
        assert event.phase_id == "phase-1"
        assert event.status == PhaseStatus.STARTED


# ── IdleEvent ────────────────────────────────────────────────────────


class TestIdleEvent:
    """Tests for IdleEvent model."""

    def test_creation(self) -> None:
        event = IdleEvent(reason="Waiting for user input")
        assert event.type == "idle"
        assert event.reason == "Waiting for user input"


# ── MCPHealthEvent ───────────────────────────────────────────────────


class TestMCPHealthEvent:
    """Tests for MCPHealthEvent model."""

    def test_healthy(self) -> None:
        event = MCPHealthEvent(
            server_name="mcp-server",
            healthy=True,
            tools_available=5,
        )
        assert event.type == "mcp_health"
        assert event.healthy is True
        assert event.tools_available == 5

    def test_unhealthy(self) -> None:
        event = MCPHealthEvent(
            server_name="mcp-server",
            healthy=False,
            error="Connection refused",
        )
        assert event.healthy is False
        assert event.error == "Connection refused"


# ── ModeChangeEvent ──────────────────────────────────────────────────


class TestModeChangeEvent:
    """Tests for ModeChangeEvent model."""

    def test_creation(self) -> None:
        event = ModeChangeEvent(mode="agent", reason="User requested agent mode")
        assert event.type == "mode_change"
        assert event.mode == "agent"


# ── ToolProgressEvent ────────────────────────────────────────────────


class TestToolProgressEvent:
    """Tests for ToolProgressEvent model."""

    def test_creation(self) -> None:
        event = ToolProgressEvent(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
            progress_percent=50,
            current_step="Loading page",
            steps_completed=2,
            steps_total=4,
        )
        assert event.type == "tool_progress"
        assert event.progress_percent == 50
        assert event.current_step == "Loading page"


# ── Tool Content Models ──────────────────────────────────────────────


class TestToolContentModels:
    """Tests for tool content sub-models."""

    def test_browser_tool_content(self) -> None:
        content = BrowserToolContent(screenshot="base64data", content="<h1>Hello</h1>")
        assert content.screenshot == "base64data"
        assert content.content == "<h1>Hello</h1>"

    def test_search_tool_content(self) -> None:
        content = SearchToolContent(results=[], provider="google")
        assert content.results == []
        assert content.provider == "google"

    def test_shell_tool_content(self) -> None:
        content = ShellToolContent(console="output here")
        assert content.console == "output here"

    def test_file_tool_content(self) -> None:
        content = FileToolContent(content="file contents")
        assert content.content == "file contents"

    def test_git_tool_content(self) -> None:
        content = GitToolContent(operation="status", output="clean")
        assert content.operation == "status"

    def test_code_executor_tool_content(self) -> None:
        content = CodeExecutorToolContent(
            language="python",
            code="print('hello')",
            output="hello",
            exit_code=0,
            execution_time_ms=150,
        )
        assert content.language == "python"
        assert content.exit_code == 0

    def test_test_runner_tool_content(self) -> None:
        content = TestRunnerToolContent(
            framework="pytest",
            total_tests=100,
            passed=95,
            failed=3,
            skipped=2,
        )
        assert content.total_tests == 100
        assert content.passed == 95

    def test_skill_tool_content(self) -> None:
        content = SkillToolContent(operation="invoke", skill_id="skill-1")
        assert content.operation == "invoke"

    def test_agent_mode_tool_content(self) -> None:
        content = AgentModeToolContent(mode="agent", previous_mode="discuss")
        assert content.mode == "agent"

    def test_chart_tool_content(self) -> None:
        content = ChartToolContent(
            chart_type="bar",
            title="Sales Data",
            data_points=50,
            series_count=3,
        )
        assert content.chart_type == "bar"
        assert content.data_points == 50

    def test_deal_item_image_url_string(self) -> None:
        item = DealItem(store="Amazon", product_name="Widget", image_url="https://img.com/a.jpg")
        assert item.image_url == "https://img.com/a.jpg"

    def test_deal_item_image_url_dict(self) -> None:
        item = DealItem(store="Amazon", product_name="Widget", image_url={"url": "https://img.com/a.jpg"})
        assert item.image_url == "https://img.com/a.jpg"

    def test_deal_item_image_url_none(self) -> None:
        item = DealItem(store="Amazon", product_name="Widget", image_url=None)
        assert item.image_url is None

    def test_deal_item_image_url_dict_content_url(self) -> None:
        item = DealItem(store="Amazon", product_name="Widget", image_url={"contentUrl": "https://img.com/b.jpg"})
        assert item.image_url == "https://img.com/b.jpg"

    def test_deal_tool_content(self) -> None:
        content = DealToolContent(query="laptop deals", stores_attempted=5, stores_with_results=3)
        assert content.query == "laptop deals"
        assert content.deals == []
        assert content.coupons == []


# ── SkillDeliveryEvent ───────────────────────────────────────────────


class TestSkillDeliveryEvent:
    """Tests for SkillDeliveryEvent model."""

    def test_creation(self) -> None:
        event = SkillDeliveryEvent(
            package_id="pkg-1",
            name="My Skill",
            description="A test skill",
            files=[
                SkillPackageFileData(path="SKILL.md", content="# Skill", size=7),
            ],
        )
        assert event.type == "skill_delivery"
        assert event.name == "My Skill"
        assert len(event.files) == 1
        assert event.files[0].path == "SKILL.md"
