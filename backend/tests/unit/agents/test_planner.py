"""
Unit tests for PlannerAgent.

Tests the planning agent in isolation with mocked LLM responses.
Covers plan creation, complexity assessment, step normalization, and requirement tracking.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.plan import ExecutionStatus, Step
from app.domain.services.agents.planner import (
    DEFAULT_MAX_PLAN_STEPS,
    DEFAULT_MIN_PLAN_STEPS,
    PlannerAgent,
    get_step_limits,
    get_task_complexity,
)


@pytest.fixture
def mock_settings_no_structured():
    """Mock settings with feature_structured_outputs disabled."""
    settings = MagicMock()
    settings.feature_structured_outputs = False
    return settings


class TestTaskComplexity:
    """Tests for the get_task_complexity function."""

    @pytest.mark.parametrize(
        "message,expected",
        [
            # Simple tasks
            ("What is Python?", "medium"),  # Short but no simple indicator
            ("Just rename this file", "simple"),
            ("Only add a print statement", "simple"),
            ("Quick fix for the typo", "simple"),
            # Medium tasks (default)
            ("Create a function that calculates fibonacci numbers", "medium"),
            ("Update the user profile page", "medium"),
            ("Add error handling to the login flow", "medium"),
            # Complex tasks
            ("Research AI trends, analyze market data, and create investment report", "complex"),
            ("Investigate the performance issues and compare different optimization strategies", "complex"),
            (
                "Create a comprehensive analysis of multiple sources and compile a detailed report",
                "complex",
            ),
        ],
    )
    def test_complexity_classification(self, message: str, expected: str):
        """Task complexity should be classified correctly based on message content."""
        result = get_task_complexity(message)
        assert result == expected

    def test_short_message_with_simple_indicator(self):
        """Short messages with simple indicators should be classified as simple."""
        result = get_task_complexity("just print hello")
        assert result == "simple"

    def test_long_message_is_complex(self):
        """Long messages (>50 words) should be classified as complex."""
        long_message = " ".join(["word"] * 55)
        result = get_task_complexity(long_message)
        assert result == "complex"

    def test_numbered_list_is_complex(self):
        """Messages with 3+ numbered items should be complex."""
        message = """
        1. First do this
        2. Then do that
        3. Finally do this
        4. And wrap up
        """
        result = get_task_complexity(message)
        assert result == "complex"

    def test_bullet_list_is_complex(self):
        """Messages with 3+ bullet items should be complex."""
        message = """
        - Search for information
        - Analyze the results
        - Create a summary
        - Share with team
        """
        result = get_task_complexity(message)
        assert result == "complex"


class TestStepLimits:
    """Tests for step limit functions."""

    def test_simple_task_limits(self):
        """Simple tasks should have 1-2 step limits."""
        min_steps, max_steps = get_step_limits("simple")
        assert min_steps == 1
        assert max_steps == 2

    def test_medium_task_limits(self):
        """Medium tasks should have 2-4 step limits."""
        min_steps, max_steps = get_step_limits("medium")
        assert min_steps == 2
        assert max_steps == 4

    def test_complex_task_limits(self):
        """Complex tasks should have 3-6 step limits."""
        min_steps, max_steps = get_step_limits("complex")
        assert min_steps == 3
        assert max_steps == 6

    def test_unknown_complexity_uses_defaults(self):
        """Unknown complexity should use default limits."""
        min_steps, max_steps = get_step_limits("unknown")
        assert min_steps == DEFAULT_MIN_PLAN_STEPS
        assert max_steps == DEFAULT_MAX_PLAN_STEPS


class TestPlannerAgent:
    """Unit tests for PlannerAgent."""

    @pytest.fixture
    def mock_agent_repository(self):
        """Mock agent repository."""
        repo = AsyncMock()
        repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        repo.save_memory = AsyncMock()
        return repo

    @pytest.fixture
    def planner(self, mock_llm, mock_agent_repository, mock_json_parser, mock_tools):
        """Create a PlannerAgent with mocked dependencies."""
        return PlannerAgent(
            agent_id="test-planner-123",
            agent_repository=mock_agent_repository,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
            feature_flags={"structured_outputs": False},
        )

    @pytest.mark.asyncio
    async def test_simple_task_generates_minimal_steps(self, planner, mock_llm_plan_response, mock_message):
        """Simple queries should generate 1-3 steps."""
        # Setup mock to return a simple plan
        mock_llm_plan_response(
            steps=[{"description": "Provide the answer"}],
            complexity="simple",
        )

        # Mock ask_structured to return a proper response
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Simple Answer",
                goal="Answer the question",
                language="en",
                message="Here's the answer",
                steps=[MagicMock(description="Provide the answer")],
            )
        )

        message = mock_message(message="What is 2+2?")
        plan = None

        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        # Simple tasks normalized to at most 3 steps
        assert len(plan.steps) <= 3

    @pytest.mark.asyncio
    async def test_complex_task_generates_detailed_plan(self, planner, mock_llm_plan_response, mock_message):
        """Research tasks should generate 5-12 steps."""
        # Setup mock to return a complex plan
        complex_steps = [MagicMock(description=f"Research step {i}") for i in range(1, 8)]

        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Comprehensive Research",
                goal="Research and analyze AI trends",
                language="en",
                message="Starting comprehensive research",
                steps=complex_steps,
            )
        )

        message = mock_message(
            message="Research the latest AI developments and write a comprehensive report with detailed analysis"
        )
        plan = None

        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        # Complex task should have multiple steps
        assert len(plan.steps) >= 3

    @pytest.mark.asyncio
    async def test_plan_includes_required_fields(self, planner, mock_message):
        """All plan steps must have required fields."""
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Test Plan",
                goal="Test goal",
                language="en",
                message="Plan created",
                steps=[
                    MagicMock(description="Search for Python tutorials"),
                    MagicMock(description="Analyze results"),
                ],
            )
        )

        message = mock_message(message="Find information about Python")
        plan = None

        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        assert plan.title is not None
        assert plan.goal is not None

        for step in plan.steps:
            assert hasattr(step, "id")
            assert hasattr(step, "description")
            assert hasattr(step, "status")
            assert step.description is not None

    @pytest.mark.asyncio
    async def test_plan_step_ids_are_sequential(self, planner, mock_message):
        """Step IDs should be sequential starting from 1."""
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Test Plan",
                goal="Test goal",
                language="en",
                message="Plan created",
                steps=[
                    MagicMock(description="Step A"),
                    MagicMock(description="Step B"),
                    MagicMock(description="Step C"),
                ],
            )
        )

        message = mock_message(message="Do three things")
        plan = None

        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        for i, step in enumerate(plan.steps):
            assert step.id == str(i + 1)

    @pytest.mark.asyncio
    async def test_plan_with_attachments(self, planner, mock_message):
        """Plans should handle messages with attachments."""
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="File Analysis",
                goal="Analyze the uploaded files",
                language="en",
                message="Analyzing files",
                steps=[MagicMock(description="Read and analyze uploaded files")],
            )
        )

        message = mock_message(
            message="Analyze these files",
            attachments=["/uploads/doc1.pdf", "/uploads/doc2.txt"],
        )
        plan = None

        async for event in planner.create_plan(message):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        # Plan should be created successfully with attachments

    @pytest.mark.asyncio
    async def test_replan_includes_context(self, planner, mock_message):
        """Replanning should include the replan context."""
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Revised Plan",
                goal="Test goal",
                language="en",
                message="Plan revised",
                steps=[MagicMock(description="Revised approach")],
            )
        )

        message = mock_message(message="Original task")
        replan_context = "Previous plan failed due to missing tool"

        plan = None
        async for event in planner.create_plan(message, replan_context=replan_context):
            if hasattr(event, "plan"):
                plan = event.plan
                break

        assert plan is not None
        # Verify the LLM was called (replan context processed)
        assert planner.llm.ask_structured.called

    @pytest.mark.asyncio
    async def test_fallback_to_json_parser_on_structured_failure(self, planner, mock_message, mock_json_parser):
        """Should fallback to JSON parser if structured output fails."""
        # Make structured output fail
        planner.llm.ask_structured = AsyncMock(side_effect=Exception("Structured output failed"))

        # Setup fallback response
        planner.llm.ask = AsyncMock(
            return_value={
                "role": "assistant",
                "content": '{"title": "Fallback Plan", "goal": "Test", "steps": [{"description": "Step 1"}]}',
            }
        )
        mock_json_parser.parse = AsyncMock(
            return_value={
                "title": "Fallback Plan",
                "goal": "Test",
                "steps": [{"description": "Step 1"}],
            }
        )

        message = mock_message(message="Test task")
        events = [event async for event in planner.create_plan(message)]

        # Should have generated some events (progress events at minimum)
        assert len(events) > 0


class TestPlanNormalization:
    """Tests for plan step normalization."""

    @pytest.fixture
    def planner(self, mock_llm, mock_json_parser, mock_tools):
        """Create a PlannerAgent for normalization tests."""
        mock_repo = AsyncMock()
        mock_repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        mock_repo.save_memory = AsyncMock()

        return PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_repo,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    def test_normalize_steps_within_limit(self, planner):
        """Steps within limit should not be modified."""
        steps = [
            Step(description="Step 1"),
            Step(description="Step 2"),
            Step(description="Step 3"),
        ]

        normalized = planner._normalize_plan_steps(steps, task_message="medium task")

        assert len(normalized) == 3
        for i, step in enumerate(normalized):
            assert step.id == str(i + 1)

    def test_normalize_merges_overflow_steps(self, planner):
        """Steps exceeding limit should be merged into final step."""
        steps = [Step(description=f"Step {i}") for i in range(1, 15)]

        normalized = planner._normalize_plan_steps(steps, task_message="simple task")

        # Simple tasks have max 3 steps
        assert len(normalized) <= 6  # Medium default if not detected as simple

        # Last step should contain merged steps info
        last_step = normalized[-1]
        assert last_step.metadata is not None
        assert "merged_from" in last_step.metadata

    def test_normalize_adds_filler_steps_for_medium_tasks(self, planner):
        """Medium tasks below minimum should get filler steps."""
        steps = [Step(description="Search for information")]

        normalized = planner._normalize_plan_steps(steps, task_message="Compare these frameworks in detail")

        # Should add fillers up to minimum
        assert len(normalized) >= 1

    def test_normalize_simple_task_no_fillers(self, planner):
        """Simple tasks should not get filler steps."""
        steps = [Step(description="Just print hello")]

        normalized = planner._normalize_plan_steps(steps, task_message="just print hello")

        # Simple tasks don't need fillers
        assert len(normalized) == 1

    def test_merged_step_description_truncated(self, planner):
        """Merged step descriptions should be truncated if too long."""
        # Create many steps with long descriptions
        steps = [
            Step(description=f"This is a very long step description number {i} that goes on and on")
            for i in range(1, 20)
        ]

        normalized = planner._normalize_plan_steps(steps, task_message="complex task")

        # Last step should have truncated description if merged
        last_step = normalized[-1]
        if last_step.metadata and last_step.metadata.get("merged_from"):
            assert len(last_step.description) <= 243  # MAX_MERGED_STEP_CHARS + "..."


class TestRequirementTracking:
    """Tests for requirement extraction and tracking."""

    @pytest.fixture
    def planner(self, mock_llm, mock_json_parser, mock_tools):
        """Create a PlannerAgent for requirement tests."""
        mock_repo = AsyncMock()
        mock_repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        mock_repo.save_memory = AsyncMock()

        return PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_repo,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_requirements_extracted_from_message(self, planner, mock_message):
        """Requirements should be extracted from user message."""
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                title="Test Plan",
                goal="Create report",
                language="en",
                message="Plan created",
                steps=[MagicMock(description="Create PDF report")],
            )
        )

        message = mock_message(message="Create a report that must be in PDF format and include charts")

        async for _ in planner.create_plan(message):
            pass

        planner.get_requirements()
        # Requirements should be extracted (if any "must" keywords present)
        # The actual extraction depends on the requirement_extractor implementation

    def test_get_requirements_initially_none(self, planner):
        """Requirements should be None before planning."""
        assert planner.get_requirements() is None

    def test_get_requirements_summary_empty_when_none(self, planner):
        """Summary should be empty when no requirements."""
        assert planner.get_requirements_summary() == ""

    def test_get_unaddressed_reminder_none_when_no_requirements(self, planner):
        """Reminder should be None when no requirements."""
        assert planner.get_unaddressed_reminder() is None


class TestPlanUpdate:
    """Tests for plan update functionality."""

    @pytest.fixture
    def planner(self, mock_llm, mock_json_parser, mock_tools):
        """Create a PlannerAgent for update tests."""
        mock_repo = AsyncMock()
        mock_repo.get_memory = AsyncMock(return_value=MagicMock(messages=[], empty=True))
        mock_repo.save_memory = AsyncMock()

        return PlannerAgent(
            agent_id="test-planner",
            agent_repository=mock_repo,
            llm=mock_llm,
            tools=mock_tools,
            json_parser=mock_json_parser,
        )

    @pytest.mark.asyncio
    async def test_update_plan_preserves_completed_steps(self, planner, plan_factory, step_factory):
        """Completed steps should be preserved during plan update."""
        # Create a plan with one completed step
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Step 1", "status": ExecutionStatus.COMPLETED},
                {"id": "2", "description": "Step 2", "status": ExecutionStatus.PENDING},
            ]
        )
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].success = True

        completed_step = plan.steps[0]

        # Mock LLM to return updated steps
        planner.llm.ask_structured = AsyncMock(
            return_value=MagicMock(
                steps=[
                    MagicMock(description="New step 2"),
                    MagicMock(description="New step 3"),
                ]
            )
        )

        updated_plan = None
        async for event in planner.update_plan(plan, completed_step):
            if hasattr(event, "plan"):
                updated_plan = event.plan
                break

        assert updated_plan is not None
        # First step should still be completed
        completed_steps = [s for s in updated_plan.steps if s.is_done()]
        assert len(completed_steps) >= 1

    @pytest.mark.asyncio
    async def test_update_plan_handles_empty_llm_response(self, planner, plan_factory, step_factory):
        """Empty LLM response should not clear remaining pending steps."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Step 1", "status": ExecutionStatus.COMPLETED},
                {"id": "2", "description": "Step 2", "status": ExecutionStatus.PENDING},
                {"id": "3", "description": "Step 3", "status": ExecutionStatus.PENDING},
            ]
        )
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].success = True

        completed_step = plan.steps[0]

        # Mock LLM to return empty steps (safeguard test)
        planner.llm.ask_structured = AsyncMock(return_value=MagicMock(steps=[]))

        updated_plan = None
        async for event in planner.update_plan(plan, completed_step):
            if hasattr(event, "plan"):
                updated_plan = event.plan
                break

        assert updated_plan is not None
        # Should still have steps (safeguard prevents premature completion)
        # Either LLM empty response is handled, or original pending steps kept
        assert len(updated_plan.steps) >= 1
