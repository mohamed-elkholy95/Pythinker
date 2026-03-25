"""Tests for domain event models — enums, content models, and discriminated union."""

from datetime import datetime

import pytest

from app.domain.models.event import (
    AgentEvent,
    BaseEvent,
    BrowserAgentToolContent,
    BrowserToolContent,
    BudgetEvent,
    CanvasToolContent,
    CanvasUpdateEvent,
    ChartToolContent,
    CheckpointSavedEvent,
    CodeDevToolContent,
    CodeExecutorToolContent,
    ComprehensionEvent,
    ConfidenceEvent,
    CouponItem,
    DatasourceEvent,
    DealItem,
    DealToolContent,
    DeepScanToolContent,
    DoneEvent,
    ErrorEvent,
    EvalMetricsEvent,
    ExportToolContent,
    FileToolContent,
    FlowSelectionEvent,
    FlowTransitionEvent,
    GitToolContent,
    IdleEvent,
    KnowledgeBaseToolContent,
    KnowledgeEvent,
    MCPHealthEvent,
    McpToolContent,
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
    PlanToolContent,
    PlaywrightToolContent,
    ProgressEvent,
    ReflectionEvent,
    ReflectionStatus,
    RepoMapToolContent,
    ReportEvent,
    ResearchModeEvent,
    ScheduleToolContent,
    SearchToolContent,
    ShellToolContent,
    SkillActivationEvent,
    SkillDeliveryEvent,
    SkillEvent,
    SkillToolContent,
    SlidesToToolContent,
    StepStatus,
    StreamEvent,
    SuggestionEvent,
    TaskRecreationEvent,
    TestRunnerToolContent,
    ThoughtEvent,
    ThoughtStatus,
    TitleEvent,
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
    WorkspaceToolContent,
)

# ── Enum tests ──────────────────────────────────────────────


class TestThoughtStatus:
    def test_values(self) -> None:
        assert ThoughtStatus.THINKING == "thinking"
        assert ThoughtStatus.THOUGHT == "thought"
        assert ThoughtStatus.CHAIN_COMPLETE == "chain_complete"


class TestPlanStatus:
    def test_values(self) -> None:
        assert PlanStatus.CREATED == "created"
        assert PlanStatus.UPDATED == "updated"
        assert PlanStatus.COMPLETED == "completed"


class TestStepStatus:
    def test_values(self) -> None:
        assert StepStatus.STARTED == "started"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.FAILED == "failed"
        assert StepStatus.COMPLETED == "completed"


class TestToolStatus:
    def test_values(self) -> None:
        assert ToolStatus.CALLING == "calling"
        assert ToolStatus.CALLED == "called"


class TestPhaseStatus:
    def test_values(self) -> None:
        assert PhaseStatus.STARTED == "started"
        assert PhaseStatus.COMPLETED == "completed"
        assert PhaseStatus.SKIPPED == "skipped"


class TestVerificationStatus:
    def test_values(self) -> None:
        assert VerificationStatus.STARTED == "started"
        assert VerificationStatus.PASSED == "passed"
        assert VerificationStatus.REVISION_NEEDED == "revision_needed"
        assert VerificationStatus.FAILED == "failed"


class TestReflectionStatus:
    def test_values(self) -> None:
        assert ReflectionStatus.TRIGGERED == "triggered"
        assert ReflectionStatus.COMPLETED == "completed"


class TestPlanningPhase:
    def test_all_values(self) -> None:
        expected = {
            "received",
            "analyzing",
            "planning",
            "finalizing",
            "heartbeat",
            "waiting",
            "verifying",
            "executing_setup",
            "tool_executing",
        }
        assert {p.value for p in PlanningPhase} == expected


class TestWideResearchStatus:
    def test_values(self) -> None:
        assert WideResearchStatus.PENDING == "pending"
        assert WideResearchStatus.SEARCHING == "searching"
        assert WideResearchStatus.AGGREGATING == "aggregating"
        assert WideResearchStatus.COMPLETED == "completed"
        assert WideResearchStatus.FAILED == "failed"


# ── BaseEvent tests ─────────────────────────────────────────


class TestBaseEvent:
    def test_defaults(self) -> None:
        e = BaseEvent()
        assert e.type == ""
        assert isinstance(e.id, str)
        assert len(e.id) > 0
        assert isinstance(e.timestamp, datetime)

    def test_unique_ids(self) -> None:
        ids = {BaseEvent().id for _ in range(50)}
        assert len(ids) == 50


# ── ErrorEvent tests ────────────────────────────────────────


class TestErrorEvent:
    def test_minimal(self) -> None:
        e = ErrorEvent(error="something broke")
        assert e.type == "error"
        assert e.error == "something broke"
        assert e.recoverable is True
        assert e.severity == "error"
        assert e.can_resume is False

    def test_full(self) -> None:
        e = ErrorEvent(
            error="timeout",
            error_type="timeout",
            recoverable=False,
            retry_hint="Try again later",
            error_code="E_TIMEOUT",
            error_category="timeout",
            severity="critical",
            retry_after_ms=5000,
            can_resume=True,
            checkpoint_event_id="evt-1",
            details={"elapsed_ms": 30000},
        )
        assert e.error_code == "E_TIMEOUT"
        assert e.retry_after_ms == 5000
        assert e.details == {"elapsed_ms": 30000}


# ── Tool content model tests ────────────────────────────────


class TestBrowserToolContent:
    def test_defaults(self) -> None:
        c = BrowserToolContent()
        assert c.screenshot is None
        assert c.content is None


class TestSearchToolContent:
    def test_minimal(self) -> None:
        c = SearchToolContent(results=[])
        assert c.results == []
        assert c.provider is None


class TestShellToolContent:
    def test_string_console(self) -> None:
        c = ShellToolContent(console="$ ls\nfile.txt")
        assert c.console == "$ ls\nfile.txt"

    def test_list_console(self) -> None:
        c = ShellToolContent(console=[{"type": "output", "text": "ok"}])
        assert len(c.console) == 1


class TestFileToolContent:
    def test_content(self) -> None:
        c = FileToolContent(content="print('hi')")
        assert c.content == "print('hi')"


class TestMcpToolContent:
    def test_any_result(self) -> None:
        c = McpToolContent(result={"key": "val"})
        assert c.result == {"key": "val"}


class TestBrowserAgentToolContent:
    def test_defaults(self) -> None:
        c = BrowserAgentToolContent(result="done")
        assert c.steps_taken == 0


class TestGitToolContent:
    def test_required_fields(self) -> None:
        c = GitToolContent(operation="clone")
        assert c.operation == "clone"
        assert c.output is None
        assert c.commits is None


class TestCodeExecutorToolContent:
    def test_all_fields(self) -> None:
        c = CodeExecutorToolContent(
            language="python",
            code="print(1)",
            output="1",
            exit_code=0,
            execution_time_ms=42,
        )
        assert c.language == "python"
        assert c.exit_code == 0


class TestPlaywrightToolContent:
    def test_defaults(self) -> None:
        c = PlaywrightToolContent()
        assert c.browser_type is None
        assert c.url is None


class TestTestRunnerToolContent:
    def test_defaults(self) -> None:
        c = TestRunnerToolContent()
        assert c.total_tests == 0
        assert c.passed == 0
        assert c.duration_ms is None


class TestSkillToolContent:
    def test_required(self) -> None:
        c = SkillToolContent(operation="invoke")
        assert c.skill_id is None


class TestExportToolContent:
    def test_fields(self) -> None:
        c = ExportToolContent(format="pdf", filename="report.pdf", size_bytes=1024)
        assert c.format == "pdf"


class TestSlidesToToolContent:
    def test_defaults(self) -> None:
        c = SlidesToToolContent()
        assert c.slide_count == 0


class TestWorkspaceToolContent:
    def test_required(self) -> None:
        c = WorkspaceToolContent(action="create")
        assert c.files_count == 0


class TestScheduleToolContent:
    def test_required(self) -> None:
        c = ScheduleToolContent(action="create")
        assert c.schedule_id is None


class TestDeepScanToolContent:
    def test_defaults(self) -> None:
        c = DeepScanToolContent()
        assert c.findings_count == 0


class TestAgentModeToolContentImport:
    def test_construct(self) -> None:
        from app.domain.models.event import AgentModeToolContent

        c = AgentModeToolContent(mode="agent")
        assert c.mode == "agent"


class TestCodeDevToolContent:
    def test_required(self) -> None:
        c = CodeDevToolContent(operation="analyze")
        assert c.file_path is None


class TestCanvasToolContent:
    def test_defaults(self) -> None:
        c = CanvasToolContent(operation="create_project")
        assert c.element_count == 0
        assert c.image_urls is None


class TestPlanToolContent:
    def test_required(self) -> None:
        c = PlanToolContent(operation="create")
        assert c.steps_count == 0


class TestRepoMapToolContent:
    def test_defaults(self) -> None:
        c = RepoMapToolContent()
        assert c.repo_path is None
        assert c.files_count == 0


class TestChartToolContent:
    def test_required(self) -> None:
        c = ChartToolContent(chart_type="bar", title="Sales")
        assert c.data_points == 0
        assert c.error is None


class TestKnowledgeBaseToolContent:
    def test_required(self) -> None:
        c = KnowledgeBaseToolContent(operation="query")
        assert c.results_count == 0
        assert c.query_time_ms == 0.0


# ── Deal models ──────────────────────────────────────────────


class TestDealItem:
    def test_defaults(self) -> None:
        d = DealItem()
        assert d.store == ""
        assert d.price is None
        assert d.item_category == "unknown"

    def test_image_url_coercion_string(self) -> None:
        d = DealItem(image_url="https://img.com/pic.jpg")
        assert d.image_url == "https://img.com/pic.jpg"

    def test_image_url_coercion_dict(self) -> None:
        d = DealItem(image_url={"url": "https://img.com/pic.jpg", "width": 100})
        assert d.image_url == "https://img.com/pic.jpg"

    def test_image_url_coercion_dict_content_url(self) -> None:
        d = DealItem(image_url={"contentUrl": "https://cdn.com/x.png"})
        assert d.image_url == "https://cdn.com/x.png"

    def test_image_url_coercion_none(self) -> None:
        d = DealItem(image_url=None)
        assert d.image_url is None

    def test_image_url_coercion_empty_dict(self) -> None:
        d = DealItem(image_url={})
        assert d.image_url is None


class TestCouponItem:
    def test_defaults(self) -> None:
        c = CouponItem()
        assert c.code == ""
        assert c.verified is False
        assert c.item_category == "unknown"


class TestDealToolContent:
    def test_defaults(self) -> None:
        c = DealToolContent()
        assert c.deals == []
        assert c.coupons == []
        assert c.query == ""
        assert c.best_deal_index is None


# ── Complex event tests ─────────────────────────────────────


class TestToolEvent:
    def test_minimal(self) -> None:
        e = ToolEvent(
            tool_call_id="tc-1",
            tool_name="search",
            function_name="web_search",
            function_args={"query": "test"},
            status=ToolStatus.CALLING,
        )
        assert e.type == "tool"
        assert e.tool_name == "search"
        assert e.call_status is None
        assert e.sequence_number is None


class TestToolProgressEvent:
    def test_minimal(self) -> None:
        e = ToolProgressEvent(
            tool_call_id="tc-1",
            tool_name="browser",
            function_name="navigate",
            progress_percent=50,
            current_step="Loading page",
        )
        assert e.progress_percent == 50
        assert e.estimated_remaining_ms is None


class TestToolStreamEvent:
    def test_minimal(self) -> None:
        e = ToolStreamEvent(
            tool_call_id="tc-1",
            tool_name="file",
            function_name="write_file",
            partial_content="hello",
        )
        assert e.content_type == "text"
        assert e.is_final is False


class TestMessageEvent:
    def test_defaults(self) -> None:
        e = MessageEvent(message="Hello")
        assert e.type == "message"
        assert e.role == "assistant"
        assert e.attachments is None
        assert e.thinking_mode is None


class TestDoneEvent:
    def test_type(self) -> None:
        e = DoneEvent()
        assert e.type == "done"


class TestTitleEvent:
    def test_title(self) -> None:
        e = TitleEvent(title="Research Report")
        assert e.title == "Research Report"


class TestWaitEvent:
    def test_defaults(self) -> None:
        e = WaitEvent()
        assert e.wait_reason is None
        assert e.suggest_user_takeover is None


class TestKnowledgeEvent:
    def test_fields(self) -> None:
        e = KnowledgeEvent(scope="session", content="found 3 items")
        assert e.type == "knowledge"


class TestDatasourceEvent:
    def test_fields(self) -> None:
        e = DatasourceEvent(api_name="openai", documentation="...")
        assert e.type == "datasource"


class TestIdleEvent:
    def test_defaults(self) -> None:
        e = IdleEvent()
        assert e.type == "idle"
        assert e.reason is None


class TestMCPHealthEvent:
    def test_fields(self) -> None:
        e = MCPHealthEvent(server_name="mcp-1", healthy=True, tools_available=5)
        assert e.tools_available == 5


class TestModeChangeEvent:
    def test_fields(self) -> None:
        e = ModeChangeEvent(mode="agent", reason="user requested")
        assert e.type == "mode_change"


class TestSuggestionEvent:
    def test_fields(self) -> None:
        e = SuggestionEvent(suggestions=["Try X", "Try Y"])
        assert len(e.suggestions) == 2
        assert e.source is None


class TestProgressEvent:
    def test_fields(self) -> None:
        e = ProgressEvent(
            phase=PlanningPhase.RECEIVED,
            message="Got it!",
            progress_percent=5,
        )
        assert e.type == "progress"
        assert e.estimated_steps is None


class TestComprehensionEvent:
    def test_fields(self) -> None:
        e = ComprehensionEvent(original_length=5000, summary="User wants X")
        assert e.type == "comprehension"
        assert e.key_requirements is None


class TestTaskRecreationEvent:
    def test_fields(self) -> None:
        e = TaskRecreationEvent(
            reason="new info",
            previous_step_count=3,
            new_step_count=5,
            preserved_findings=2,
        )
        assert e.type == "task_recreation"


class TestReportEvent:
    def test_fields(self) -> None:
        e = ReportEvent(id="r-1", title="Report", content="# Hello")
        assert e.type == "report"
        assert e.sources is None


class TestSkillDeliveryEvent:
    def test_defaults(self) -> None:
        e = SkillDeliveryEvent(
            package_id="pkg-1",
            name="SEO",
            description="SEO tool",
        )
        assert e.version == "1.0.0"
        assert e.icon == "puzzle"
        assert e.files == []


class TestSkillActivationEvent:
    def test_defaults(self) -> None:
        e = SkillActivationEvent()
        assert e.type == "skill_activation"
        assert e.prompt_chars == 0
        assert e.auto_trigger_enabled is False


class TestStreamEvent:
    def test_defaults(self) -> None:
        e = StreamEvent(content="chunk")
        assert e.is_final is False
        assert e.phase == "thinking"
        assert e.lane == "answer"


class TestVerificationEvent:
    def test_fields(self) -> None:
        e = VerificationEvent(status=VerificationStatus.PASSED, verdict="pass")
        assert e.type == "verification"


class TestReflectionEvent:
    def test_fields(self) -> None:
        e = ReflectionEvent(status=ReflectionStatus.TRIGGERED, decision="continue")
        assert e.type == "reflection"


class TestPathEvent:
    def test_fields(self) -> None:
        e = PathEvent(path_id="p-1", action="created")
        assert e.type == "path"
        assert e.score is None


class TestMultiTaskEvent:
    def test_fields(self) -> None:
        e = MultiTaskEvent(
            challenge_id="ch-1",
            action="started",
            current_task_index=0,
            total_tasks=3,
        )
        assert e.progress_percentage == 0.0


class TestWorkspaceEvent:
    def test_fields(self) -> None:
        e = WorkspaceEvent(action="initialized")
        assert e.type == "workspace"
        assert e.files_organized == 0


class TestBudgetEvent:
    def test_fields(self) -> None:
        e = BudgetEvent(
            action="warning",
            budget_limit=10.0,
            consumed=8.5,
            remaining=1.5,
            percentage_used=85.0,
        )
        assert e.warning_threshold == 0.8
        assert e.session_paused is False


class TestPhaseTransitionEvent:
    def test_fields(self) -> None:
        e = PhaseTransitionEvent(phase="research_foundation")
        assert e.type == "phase_transition"
        assert e.label is None


class TestCheckpointSavedEvent:
    def test_fields(self) -> None:
        e = CheckpointSavedEvent(phase="analysis_synthesis")
        assert e.type == "checkpoint_saved"
        assert e.source_count is None


class TestWideResearchEvent:
    def test_fields(self) -> None:
        e = WideResearchEvent(
            research_id="wr-1",
            topic="AI safety",
            status=WideResearchStatus.SEARCHING,
            total_queries=10,
            completed_queries=3,
        )
        assert e.sources_found == 0
        assert e.errors == []


class TestThoughtEvent:
    def test_fields(self) -> None:
        e = ThoughtEvent(status=ThoughtStatus.THINKING, content="Analyzing...")
        assert e.type == "thought"
        assert e.is_final is False


class TestConfidenceEvent:
    def test_fields(self) -> None:
        e = ConfidenceEvent(
            decision="proceed",
            confidence=0.9,
            level="high",
            action_recommendation="proceed",
        )
        assert e.supporting_factors == []
        assert e.risk_factors == []


class TestFlowSelectionEvent:
    def test_fields(self) -> None:
        e = FlowSelectionEvent(flow_mode="plan_act")
        assert e.type == "flow_selection"
        assert e.model is None


class TestFlowTransitionEvent:
    def test_fields(self) -> None:
        e = FlowTransitionEvent(from_state="planning", to_state="executing")
        assert e.type == "flow_transition"
        assert e.elapsed_ms is None


class TestCanvasUpdateEvent:
    def test_fields(self) -> None:
        e = CanvasUpdateEvent(
            project_id="p-1",
            operation="add_element",
            version=2,
        )
        assert e.type == "canvas_update"
        assert e.element_count == 0


class TestResearchModeEvent:
    def test_fields(self) -> None:
        e = ResearchModeEvent(research_mode="deep_research")
        assert e.type == "research_mode"


class TestPhaseEvent:
    def test_fields(self) -> None:
        e = PhaseEvent(
            phase_id="ph-1",
            phase_type="research_foundation",
            label="Research",
            status=PhaseStatus.STARTED,
            order=1,
        )
        assert e.type == "phase"
        assert e.total_phases == 0


class TestEvalMetricsEvent:
    def test_fields(self) -> None:
        e = EvalMetricsEvent(
            metrics={"faithfulness": 0.95},
            hallucination_score=0.05,
            passed=True,
        )
        assert e.type == "eval_metrics"


class TestPartialResultEvent:
    def test_fields(self) -> None:
        e = PartialResultEvent(
            step_index=0,
            step_title="Search",
            headline="Found 12 results",
        )
        assert e.sources_count == 0


class TestSkillEvent:
    def test_fields(self) -> None:
        e = SkillEvent(
            skill_id="sk-1",
            skill_name="Deal Finder",
            action="activated",
            reason="matched trigger",
        )
        assert e.type == "skill"
        assert e.tools_affected is None


# ── Discriminated union test ────────────────────────────────


class TestAgentEventDiscriminator:
    def test_error_event(self) -> None:
        from pydantic import TypeAdapter

        ta = TypeAdapter(AgentEvent)
        e = ta.validate_python({"type": "error", "error": "fail"})
        assert isinstance(e, ErrorEvent)

    def test_done_event(self) -> None:
        from pydantic import TypeAdapter

        ta = TypeAdapter(AgentEvent)
        e = ta.validate_python({"type": "done"})
        assert isinstance(e, DoneEvent)

    def test_message_event(self) -> None:
        from pydantic import TypeAdapter

        ta = TypeAdapter(AgentEvent)
        e = ta.validate_python({"type": "message", "message": "hi"})
        assert isinstance(e, MessageEvent)

    def test_invalid_type_raises(self) -> None:
        from pydantic import TypeAdapter, ValidationError

        ta = TypeAdapter(AgentEvent)
        with pytest.raises(ValidationError):
            ta.validate_python({"type": "nonexistent_event_type"})

    def test_tool_event(self) -> None:
        from pydantic import TypeAdapter

        ta = TypeAdapter(AgentEvent)
        e = ta.validate_python(
            {
                "type": "tool",
                "tool_call_id": "tc-1",
                "tool_name": "search",
                "function_name": "web_search",
                "function_args": {"q": "test"},
                "status": "calling",
            }
        )
        assert isinstance(e, ToolEvent)
        assert e.status == ToolStatus.CALLING
