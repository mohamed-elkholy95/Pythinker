"""
Integration tests for Plan-Execute workflow.

Tests the complete flow from planning through execution with mocked LLM.
Covers multi-step plans, tool failure recovery, verification feedback loops,
and stuck detection.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.event import (
    StepEvent,
)
from app.domain.models.plan import ExecutionStatus


class TestSimpleQueryFlow:
    """Tests for simple query handling."""

    @pytest.mark.asyncio
    async def test_simple_query_classifies_correctly(self, mock_llm, mock_settings):
        """Simple queries should be classified for fast path."""
        from app.domain.services.flows.fast_path import FastPathRouter, QueryIntent

        router = FastPathRouter(browser=None, llm=mock_llm, search_engine=None)

        # Simple factual question
        intent, _ = router.classify("What is 2+2?")
        # Knowledge queries should be identified
        assert intent in [QueryIntent.KNOWLEDGE, QueryIntent.TASK]

    @pytest.mark.asyncio
    async def test_url_query_classifies_as_navigation(self, mock_llm, mock_settings):
        """URL queries should classify as navigation."""
        from app.domain.services.flows.fast_path import FastPathRouter, QueryIntent

        router = FastPathRouter(browser=None, llm=mock_llm, search_engine=None)

        intent, params = router.classify("open https://example.com")
        assert intent == QueryIntent.DIRECT_BROWSE
        assert "target" in params


class TestMultiStepPlanExecution:
    """Tests for multi-step plan execution."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def mock_planner(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create a mock planner agent."""
        from app.domain.services.agents.planner import PlannerAgent

        return PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            feature_flags={"structured_outputs": False},
        )

    @pytest.fixture
    def mock_executor(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create a mock execution agent."""
        from app.domain.services.agents.execution import ExecutionAgent

        return ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_three_step_plan_creates_correctly(self, mock_planner, mock_message):
        """A 3-step plan should be created correctly."""
        # Setup planner to return a 3-step plan
        mock_planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Research Plan",
                goal="Research and summarize",
                language="en",
                message="Plan ready",
                steps=[
                    MagicMock(description="Search for information"),
                    MagicMock(description="Analyze results"),
                    MagicMock(description="Write summary"),
                ],
            )
        )

        message = mock_message(message="Research Python best practices and summarize")

        # Create the plan
        plan = None
        async for event in mock_planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        assert len(plan.steps) >= 3
        assert plan.title == "Research Plan"

        # Verify all steps are pending
        for step in plan.steps:
            assert step.status == ExecutionStatus.PENDING

        # Verify plan can get next step
        next_step = plan.get_next_step()
        assert next_step is not None
        assert next_step.id == "1"

    @pytest.mark.asyncio
    async def test_plan_progress_tracking(self, mock_message, plan_factory):
        """Plan progress should be tracked correctly."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Step 1"},
                {"id": "2", "description": "Step 2"},
                {"id": "3", "description": "Step 3"},
            ]
        )

        # Initially all pending
        progress = plan.get_progress()
        assert progress["total"] == 3
        assert progress["completed"] == 0

        # Complete first step
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].success = True

        progress = plan.get_progress()
        assert progress["completed"] == 1

        # Complete all steps
        for step in plan.steps:
            step.status = ExecutionStatus.COMPLETED
            step.success = True

        progress = plan.get_progress()
        assert progress["completed"] == 3


class TestToolFailureRecovery:
    """Tests for tool failure and retry handling."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.mark.asyncio
    async def test_transient_error_retries(self, mock_tool_registry):
        """Transient errors should trigger retries."""
        call_count = 0

        async def flaky_tool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary network error")
            return {"success": True, "data": "result"}

        mock_tool_registry.tools["web_search"] = {"response": None, "error": None}
        mock_tool_registry.execute = flaky_tool

        # Execute tool with retries
        result = None
        for attempt in range(3):
            try:
                result = await mock_tool_registry.execute("web_search", {"query": "test"})
                break
            except Exception:
                if attempt == 2:
                    raise
                continue

        assert result is not None
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_permanent_error_fails_gracefully(self, mock_tool_registry):
        """Permanent errors should fail gracefully."""
        mock_tool_registry.register(
            "auth_tool",
            error=Exception("Authentication failed - invalid credentials"),
        )

        with pytest.raises(Exception) as exc_info:
            await mock_tool_registry.execute("auth_tool", {})

        assert "Authentication failed" in str(exc_info.value)


class TestVerificationFeedbackLoop:
    """Tests for plan verification and revision."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.mark.asyncio
    async def test_invalid_plan_gets_revised(
        self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools, mock_message
    ):
        """Invalid plans should trigger revision."""
        from app.domain.services.agents.planner import PlannerAgent

        planner = PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            feature_flags={"structured_outputs": False},
        )

        # First plan is invalid, second is valid
        call_count = [0]

        async def mock_ask_structured(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call - return plan with unknown tool
                return MagicMock(
                    title="Invalid Plan",
                    goal="Test",
                    language="en",
                    message="Plan created",
                    steps=[MagicMock(description="Use nonexistent_tool")],
                )
            # Second call - return valid plan
            return MagicMock(
                title="Valid Plan",
                goal="Test",
                language="en",
                message="Plan revised",
                steps=[MagicMock(description="Use web_search tool")],
            )

        planner.llm.ask_structured = AsyncMock(side_effect=mock_ask_structured)

        message = mock_message(message="Search for something")

        # Create initial plan
        plan = None
        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None

        # Simulate verification failure and replan
        replan_context = "Previous plan used unknown tool: nonexistent_tool"
        revised_plan = None
        async for event in planner.create_plan(message, replan_context=replan_context):
            if hasattr(event, "plan"):
                revised_plan = event.plan
                break

        assert revised_plan is not None
        # Plan should be revised (LLM called twice)
        assert call_count[0] == 2


class TestStuckDetectionAndRecovery:
    """Tests for stuck detection during execution."""

    @pytest.fixture
    def stuck_detector(self):
        """Create a stuck detector for testing."""
        from app.domain.services.agents.stuck_detector import StuckDetector

        return StuckDetector()

    def test_detects_repetitive_outputs(self, stuck_detector):
        """Repeated identical outputs should be detected as stuck."""
        # Track the same response multiple times
        response = {"content": "Searching for information..."}

        for _ in range(5):
            stuck_detector.track_response(response)

        # Should be stuck after repetitive responses
        assert stuck_detector.is_stuck() is True

    def test_no_false_positive_on_progress(self, stuck_detector):
        """Different outputs should not trigger stuck detection."""
        responses = [
            {"content": "Found 3 results"},
            {"content": "Analyzing first result: Python documentation"},
            {"content": "Extracting key information about async patterns"},
        ]

        for response in responses:
            stuck_detector.track_response(response)

        # Should not be stuck with different responses
        assert stuck_detector.is_stuck() is False


class TestEventStreaming:
    """Tests for event streaming during execution."""

    @pytest.mark.asyncio
    async def test_plan_creation_emits_progress_events(self, mock_llm, mock_json_parser, mock_tools, mock_message):
        """Plan creation should emit progress events."""
        from app.domain.models.event import ProgressEvent
        from app.domain.services.agents.planner import PlannerAgent

        mock_repo = AsyncMock()
        mock_repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        mock_repo.save_memory = AsyncMock()

        planner = PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_repo,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Test Plan",
                goal="Test goal",
                language="en",
                message="Done",
                steps=[MagicMock(description="Step 1")],
            )
        )

        message = mock_message(message="Test task")
        events = []

        async for event in planner.create_plan(message):
            events.append(event)

        # Should have progress events
        progress_events = [e for e in events if isinstance(e, ProgressEvent)]
        assert len(progress_events) >= 1

    @pytest.mark.asyncio
    async def test_step_execution_emits_step_events(
        self, mock_llm, mock_json_parser, mock_tools, mock_message, plan_factory, step_factory
    ):
        """Step execution should emit step events."""
        from app.domain.services.agents.execution import ExecutionAgent

        mock_repo = AsyncMock()
        mock_repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        mock_repo.save_memory = AsyncMock()

        executor = ExecutionAgent(
            agent_id="test-executor",
            agent_repository=mock_repo,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

        executor.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"final_answer": "Done"}',
            }
        )
        executor.json_parser.parse = AsyncMock(return_value={"final_answer": "Done"})

        plan = plan_factory(steps=[{"id": "1", "description": "Test step"}])
        step = plan.steps[0]
        message = mock_message(message="Test")

        events = []
        async for event in executor.execute_step(plan, step, message):
            events.append(event)

        # Should have step events
        step_events = [e for e in events if isinstance(e, StepEvent)]
        assert len(step_events) >= 1


class TestStateTransitions:
    """Tests for plan and step state transitions."""

    def test_step_status_transitions(self, step_factory):
        """Step status should transition correctly."""
        step = step_factory(status=ExecutionStatus.PENDING)

        assert step.status == ExecutionStatus.PENDING
        assert step.is_actionable() is True

        step.status = ExecutionStatus.RUNNING
        assert step.is_actionable() is False
        assert step.is_done() is False

        step.status = ExecutionStatus.COMPLETED
        step.success = True
        assert step.is_done() is True
        assert step.status.is_success() is True

    def test_step_failure_transition(self, step_factory):
        """Failed steps should transition correctly."""
        step = step_factory(status=ExecutionStatus.PENDING)

        step.status = ExecutionStatus.FAILED
        step.error = "Tool execution failed"

        assert step.is_done() is True
        assert step.status.is_failure() is True

    def test_step_blocked_transition(self, step_factory):
        """Blocked steps should have blocking info."""
        step = step_factory(status=ExecutionStatus.PENDING)

        step.mark_blocked("Dependency failed", blocked_by="step_1")

        assert step.status == ExecutionStatus.BLOCKED
        assert step.blocked_by == "step_1"
        assert "Dependency failed" in step.notes

    def test_plan_completion_detection(self, plan_factory):
        """Plan completion should be detected correctly."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Step 1"},
                {"id": "2", "description": "Step 2"},
            ]
        )

        # Not done initially
        assert plan.is_done() is False

        # Still not done after one step
        plan.steps[0].status = ExecutionStatus.COMPLETED
        assert plan.get_next_step() is not None

        # Done after all steps
        plan.steps[1].status = ExecutionStatus.COMPLETED
        plan.status = ExecutionStatus.COMPLETED
        assert plan.is_done() is True
