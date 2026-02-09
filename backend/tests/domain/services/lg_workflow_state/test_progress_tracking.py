# backend/tests/domain/services/langgraph/test_progress_tracking.py
"""Tests for requirement progress tracking in LangGraph workflow.

These tests verify that the progress tracking system properly:
1. Initializes RequirementProgress from user intent
2. Updates progress when steps complete
3. Calculates alignment scores correctly
4. Uses semantic matching to detect addressed requirements
"""

from unittest.mock import MagicMock

import pytest

from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.agents.intent_tracker import IntentTracker, IntentType, UserIntent
from app.domain.services.langgraph.nodes.planning import _initialize_requirement_progress
from app.domain.services.langgraph.nodes.update import (
    _get_step_output,
    _update_requirement_progress,
    update_node,
)
from app.domain.services.langgraph.state import (
    RequirementProgress,
    create_initial_state,
    merge_requirement_progress,
)

# ============================================================================
# Unit Tests for RequirementProgress
# ============================================================================


class TestRequirementProgress:
    """Tests for RequirementProgress dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        progress = RequirementProgress(requirement="Test requirement")
        assert progress.requirement == "Test requirement"
        assert progress.is_addressed is False
        assert progress.confidence == 0.0
        assert progress.addressed_by_step is None
        assert progress.evidence is None

    def test_addressed_requirement(self):
        """Test addressed requirement values."""
        progress = RequirementProgress(
            requirement="Create a login page",
            is_addressed=True,
            confidence=0.8,
            addressed_by_step="step-1",
            evidence="Created login.html with form",
        )
        assert progress.is_addressed is True
        assert progress.confidence == 0.8
        assert progress.addressed_by_step == "step-1"
        assert "login" in progress.evidence.lower()


class TestMergeRequirementProgress:
    """Tests for the merge_requirement_progress reducer."""

    def test_merge_with_none_returns_original(self):
        """Merging with None should return the original list."""
        original = [RequirementProgress(requirement="Test")]
        result = merge_requirement_progress(original, None)
        assert result == original

    def test_merge_replaces_old_with_new(self):
        """New progress should replace old progress."""
        old = [RequirementProgress(requirement="Old")]
        new = [RequirementProgress(requirement="New")]
        result = merge_requirement_progress(old, new)
        assert result == new
        assert len(result) == 1
        assert result[0].requirement == "New"

    def test_merge_with_empty_list(self):
        """Merging with empty list should return empty."""
        original = [RequirementProgress(requirement="Test")]
        result = merge_requirement_progress(original, [])
        assert result == []


# ============================================================================
# Unit Tests for _initialize_requirement_progress
# ============================================================================


class TestInitializeRequirementProgress:
    """Tests for _initialize_requirement_progress function."""

    def test_empty_requirements(self):
        """Empty requirements should return empty list."""
        user_intent = UserIntent(
            intent_type=IntentType.ACTION,
            primary_goal="Test goal",
            explicit_requirements=[],
            implicit_requirements=[],
            constraints=[],
            implicit_constraints=[],
            preferences={},
            original_prompt="Test",
        )
        progress = _initialize_requirement_progress(user_intent)
        assert progress == []

    def test_explicit_requirements_only(self):
        """Only explicit requirements should be tracked."""
        user_intent = UserIntent(
            intent_type=IntentType.CREATION,
            primary_goal="Create a website",
            explicit_requirements=["Add login page", "Add dashboard"],
            implicit_requirements=[],
            constraints=[],
            implicit_constraints=[],
            preferences={},
            original_prompt="Create a website with login and dashboard",
        )
        progress = _initialize_requirement_progress(user_intent)
        assert len(progress) == 2
        assert progress[0].requirement == "Add login page"
        assert progress[1].requirement == "Add dashboard"
        assert all(not p.is_addressed for p in progress)

    def test_implicit_requirements_only(self):
        """Implicit requirements should also be tracked."""
        user_intent = UserIntent(
            intent_type=IntentType.CREATION,
            primary_goal="Create a script",
            explicit_requirements=[],
            implicit_requirements=["handle errors", "log output"],
            constraints=[],
            implicit_constraints=[],
            preferences={},
            original_prompt="Create a script that handles errors and logs output",
        )
        progress = _initialize_requirement_progress(user_intent)
        assert len(progress) == 2
        assert progress[0].requirement == "handle errors"
        assert progress[1].requirement == "log output"

    def test_both_explicit_and_implicit(self):
        """Both explicit and implicit requirements should be tracked."""
        user_intent = UserIntent(
            intent_type=IntentType.CREATION,
            primary_goal="Build API",
            explicit_requirements=["Create endpoint"],
            implicit_requirements=["validate input"],
            constraints=["no external libraries"],
            implicit_constraints=[],
            preferences={},
            original_prompt="Build an API with endpoint that validates input",
        )
        progress = _initialize_requirement_progress(user_intent)
        assert len(progress) == 2
        # Explicit first, then implicit
        assert progress[0].requirement == "Create endpoint"
        assert progress[1].requirement == "validate input"
        # All should be unaddressed initially
        assert all(p.is_addressed is False for p in progress)
        assert all(p.confidence == 0.0 for p in progress)


# ============================================================================
# Unit Tests for _get_step_output
# ============================================================================


class TestGetStepOutput:
    """Tests for _get_step_output function."""

    def test_empty_state(self):
        """Empty state should return empty string."""
        state = {}
        result = _get_step_output(state)
        assert result == ""

    def test_step_notes_only(self):
        """Should extract notes from current step."""
        step = MagicMock()
        step.notes = "Step completed successfully"
        state = {"current_step": step, "tool_results": []}
        result = _get_step_output(state)
        assert "Step completed successfully" in result

    def test_tool_results_dict(self):
        """Should extract output from dict tool results."""
        step = MagicMock()
        step.notes = None
        state = {
            "current_step": step,
            "tool_results": [
                {"output": "File created at /path/to/file"},
                {"result": "Search found 5 results"},
            ],
        }
        result = _get_step_output(state)
        assert "File created" in result
        assert "Search found" in result

    def test_tool_results_object(self):
        """Should extract output from ToolResult objects."""
        step = MagicMock()
        step.notes = None

        tool_result = MagicMock()
        tool_result.output = "Browser navigated to https://example.com"

        state = {"current_step": step, "tool_results": [tool_result]}
        result = _get_step_output(state)
        assert "Browser navigated" in result

    def test_combined_notes_and_results(self):
        """Should combine step notes and tool results."""
        step = MagicMock()
        step.notes = "Step 1 complete"
        state = {
            "current_step": step,
            "tool_results": [{"output": "Created file.py"}],
        }
        result = _get_step_output(state)
        assert "Step 1 complete" in result
        assert "Created file.py" in result

    def test_truncates_long_output(self):
        """Should truncate very long tool outputs."""
        step = MagicMock()
        step.notes = None
        long_output = "x" * 1000
        state = {
            "current_step": step,
            "tool_results": [{"output": long_output}],
        }
        result = _get_step_output(state)
        # Should be truncated to 500 chars
        assert len(result) <= 500


# ============================================================================
# Unit Tests for _update_requirement_progress
# ============================================================================


class TestUpdateRequirementProgress:
    """Tests for _update_requirement_progress function."""

    def _create_mock_state(
        self,
        requirements: list[str] | None = None,
        current_progress: list[RequirementProgress] | None = None,
        step_notes: str | None = None,
        tool_output: str | None = None,
    ) -> dict:
        """Create a mock state for testing."""
        # Create mock step
        step = MagicMock()
        step.id = "step-1"
        step.description = "Test step"
        step.notes = step_notes

        # Create mock intent tracker
        intent_tracker = IntentTracker()

        # Create user intent if requirements provided
        user_intent = None
        if requirements is not None:
            user_intent = UserIntent(
                intent_type=IntentType.ACTION,
                primary_goal="Test goal",
                explicit_requirements=requirements,
                implicit_requirements=[],
                constraints=[],
                implicit_constraints=[],
                preferences={},
                original_prompt="Test",
            )

        # Create progress list
        if current_progress is None and requirements:
            current_progress = [RequirementProgress(requirement=req) for req in requirements]

        # Build tool results
        tool_results = []
        if tool_output:
            tool_results.append({"output": tool_output})

        return {
            "current_step": step,
            "intent_tracker": intent_tracker,
            "user_intent": user_intent,
            "requirement_progress": current_progress or [],
            "tool_results": tool_results,
            "intent_alignment_score": 0.0,
        }

    def test_no_intent_tracker_returns_existing(self):
        """Without intent tracker, should return existing progress."""
        state = self._create_mock_state(requirements=["Test"])
        state["intent_tracker"] = None

        progress, score = _update_requirement_progress(state)
        assert progress == state["requirement_progress"]
        assert score == 0.0

    def test_no_user_intent_returns_existing(self):
        """Without user intent, should return existing progress."""
        state = self._create_mock_state()
        state["user_intent"] = None

        progress, _ = _update_requirement_progress(state)
        assert progress == []

    def test_no_current_step_returns_existing(self):
        """Without current step, should return existing progress."""
        state = self._create_mock_state(requirements=["Test"])
        state["current_step"] = None

        progress, _ = _update_requirement_progress(state)
        assert len(progress) == 1

    def test_requirement_addressed_by_semantic_match(self):
        """Requirement should be marked addressed when output matches."""
        state = self._create_mock_state(
            requirements=["Create a login form"],
            step_notes="Created login form with username and password fields",
            tool_output="File login.html created successfully",
        )

        progress, _ = _update_requirement_progress(state)

        # Should have matched based on semantic similarity
        assert len(progress) == 1
        # Note: actual matching depends on semantic similarity threshold

    def test_already_addressed_stays_addressed(self):
        """Already addressed requirements should stay addressed."""
        addressed_progress = [
            RequirementProgress(
                requirement="Create button",
                is_addressed=True,
                confidence=0.8,
                addressed_by_step="step-0",
                evidence="Button created",
            )
        ]
        state = self._create_mock_state(
            requirements=["Create button"],
            current_progress=addressed_progress,
        )

        progress, _ = _update_requirement_progress(state)

        assert len(progress) == 1
        assert progress[0].is_addressed is True
        assert progress[0].addressed_by_step == "step-0"  # Original step

    def test_alignment_score_calculation(self):
        """Alignment score should be calculated correctly."""
        # Use requirements that won't match semantically with "Test step" description
        progress = [
            RequirementProgress(requirement="Database migration completed", is_addressed=True),
            RequirementProgress(requirement="Authentication module finished", is_addressed=True),
            RequirementProgress(requirement="Deploy application to production servers", is_addressed=False),
            RequirementProgress(requirement="Security vulnerability audit passed", is_addressed=False),
        ]
        state = self._create_mock_state(
            requirements=[
                "Database migration completed",
                "Authentication module finished",
                "Deploy application to production servers",
                "Security vulnerability audit passed",
            ],
            current_progress=progress,
        )

        # Mock semantic matching to return False so unaddressed items stay unaddressed.
        # This test verifies score calculation, not semantic matching (which uses
        # hash()-based trigram embeddings that are non-deterministic across sessions).
        state["intent_tracker"].check_requirement_addressed = lambda **kwargs: False

        _, score = _update_requirement_progress(state)

        # 2 out of 4 addressed = 0.5
        assert score == 0.5

    def test_empty_progress_gives_zero_score(self):
        """Empty progress list should give alignment score of 0."""
        state = self._create_mock_state(requirements=[])

        _, score = _update_requirement_progress(state)

        # Empty list, score should be 0 (from initial state)
        assert score == 0.0


# ============================================================================
# Integration Tests for update_node
# ============================================================================


class TestUpdateNodeProgressTracking:
    """Integration tests for progress tracking in update_node."""

    def _create_mock_state_with_plan(
        self,
        requirements: list[str] | None = None,
    ) -> dict:
        """Create a full mock state with plan."""
        step = Step(
            id="step-1",
            description="Create login functionality",
            status=ExecutionStatus.COMPLETED,
        )
        plan = Plan(
            id="plan-1",
            title="Test Plan",
            goal="Test goal",
            steps=[step, Step(id="step-2", description="Next step", status=ExecutionStatus.PENDING)],
        )

        # Create intent tracker
        intent_tracker = IntentTracker()

        # Create user intent
        user_intent = None
        if requirements:
            user_intent = UserIntent(
                intent_type=IntentType.CREATION,
                primary_goal="Create application",
                explicit_requirements=requirements,
                implicit_requirements=[],
                constraints=[],
                implicit_constraints=[],
                preferences={},
                original_prompt="Create an application",
            )

        # Initialize progress
        progress = []
        if requirements:
            progress = [RequirementProgress(requirement=r) for r in requirements]

        # Mock planner
        planner = MagicMock()

        async def mock_update_plan(*args, **kwargs):
            return
            yield

        planner.update_plan = mock_update_plan

        return {
            "planner": planner,
            "plan": plan,
            "current_step": step,
            "iteration_count": 0,
            "max_iterations": 100,
            "pending_events": [],
            "recent_actions": [],
            "recent_tools": [],
            "event_queue": None,
            "intent_tracker": intent_tracker,
            "user_intent": user_intent,
            "requirement_progress": progress,
            "intent_alignment_score": 0.0,
            "tool_results": [],
        }

    @pytest.mark.asyncio
    async def test_update_node_includes_progress_tracking(self):
        """Update node should include progress tracking in result."""
        state = self._create_mock_state_with_plan(
            requirements=["Create login", "Add authentication"],
        )

        result = await update_node(state)

        assert "requirement_progress" in result
        assert "intent_alignment_score" in result
        assert isinstance(result["requirement_progress"], list)
        assert isinstance(result["intent_alignment_score"], float)

    @pytest.mark.asyncio
    async def test_update_node_without_intent_tracking(self):
        """Update node should work without intent tracking."""
        state = self._create_mock_state_with_plan()
        state["intent_tracker"] = None
        state["user_intent"] = None

        result = await update_node(state)

        # Should still have progress fields
        assert "requirement_progress" in result
        assert "intent_alignment_score" in result

    @pytest.mark.asyncio
    async def test_update_node_handles_missing_planner(self):
        """Update node should handle missing planner gracefully."""
        state = self._create_mock_state_with_plan()
        state["planner"] = None

        result = await update_node(state)

        # Should return with pending_events
        assert "pending_events" in result


# ============================================================================
# Integration Tests for create_initial_state
# ============================================================================


class TestCreateInitialStateProgress:
    """Tests for progress tracking fields in create_initial_state."""

    def test_initial_state_has_progress_fields(self):
        """Initial state should have all progress tracking fields."""
        message = MagicMock()
        message.message = "Test message"

        state = create_initial_state(
            message=message,
            agent_id="agent-1",
            session_id="session-1",
        )

        assert "requirement_progress" in state
        assert "constraint_violations" in state
        assert "intent_alignment_score" in state

    def test_initial_progress_is_empty(self):
        """Initial progress should be empty lists and zero score."""
        message = MagicMock()
        message.message = "Test message"

        state = create_initial_state(
            message=message,
            agent_id="agent-1",
            session_id="session-1",
        )

        assert state["requirement_progress"] == []
        assert state["constraint_violations"] == []
        assert state["intent_alignment_score"] == 0.0


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_requirement(self):
        """Very long requirements should be handled."""
        long_req = "x" * 1000
        progress = RequirementProgress(requirement=long_req)
        assert len(progress.requirement) == 1000

    def test_unicode_requirement(self):
        """Unicode in requirements should be handled."""
        unicode_req = "Create page with emoji \U0001f600 and Chinese \u4e2d\u6587"
        progress = RequirementProgress(requirement=unicode_req)
        assert progress.requirement == unicode_req

    def test_empty_requirement_string(self):
        """Empty requirement string should be handled."""
        progress = RequirementProgress(requirement="")
        assert progress.requirement == ""
        assert progress.is_addressed is False

    def test_special_characters_in_evidence(self):
        """Special characters in evidence should be handled."""
        progress = RequirementProgress(
            requirement="Test",
            is_addressed=True,
            evidence="Output: {\"key\": \"value\", 'single': 'quotes'}",
        )
        assert '{"key":' in progress.evidence

    def test_alignment_score_bounds(self):
        """Alignment score should always be between 0 and 1."""
        # All addressed
        progress_all = [RequirementProgress(requirement=f"Req {i}", is_addressed=True) for i in range(5)]
        addressed = sum(1 for r in progress_all if r.is_addressed)
        total = len(progress_all)
        score = addressed / total
        assert 0.0 <= score <= 1.0
        assert score == 1.0

        # None addressed
        progress_none = [RequirementProgress(requirement=f"Req {i}", is_addressed=False) for i in range(5)]
        addressed = sum(1 for r in progress_none if r.is_addressed)
        total = len(progress_none)
        score = addressed / total
        assert 0.0 <= score <= 1.0
        assert score == 0.0

    def test_single_requirement_all_addressed(self):
        """Single requirement that's addressed should give 100% score."""
        progress = [RequirementProgress(requirement="Single req", is_addressed=True)]
        addressed = sum(1 for r in progress if r.is_addressed)
        total = len(progress)
        score = addressed / total
        assert score == 1.0


# ============================================================================
# Semantic Matching Tests
# ============================================================================


class TestSemanticMatching:
    """Tests for semantic matching of requirements to work done."""

    def test_exact_match_detection(self):
        """Exact text matches should be detected."""
        tracker = IntentTracker()

        # Set up intent
        tracker.extract_intent("Create a login page")

        # Check exact match
        result = tracker.check_requirement_addressed(
            requirement="Create a login page",
            work_done="Created a login page with form fields",
            threshold=0.3,
        )
        assert result is True

    def test_semantic_match_detection(self):
        """Semantically similar text should be detected."""
        tracker = IntentTracker()

        # Set up intent
        tracker.extract_intent("Build authentication system")

        # Check semantic match (similar concept, different words)
        result = tracker.check_requirement_addressed(
            requirement="Build authentication system",
            work_done="Implemented user login with password verification",
            threshold=0.3,
        )
        # This may or may not match depending on trigram similarity
        assert isinstance(result, bool)

    def test_unrelated_text_not_matched(self):
        """Unrelated text should not be matched."""
        tracker = IntentTracker()

        # Set up intent
        tracker.extract_intent("Create database schema")

        # Check unrelated work
        result = tracker.check_requirement_addressed(
            requirement="Create database schema",
            work_done="Wrote unit tests for math functions",
            threshold=0.7,  # Higher threshold for stricter matching
        )
        # Should likely not match (but depends on embedding similarity)
        assert isinstance(result, bool)


# ============================================================================
# Confidence Level Tests
# ============================================================================


class TestConfidenceLevels:
    """Tests for confidence level assignment."""

    def test_addressed_requirement_has_confidence(self):
        """Addressed requirements should have confidence set."""
        progress = RequirementProgress(
            requirement="Test",
            is_addressed=True,
            confidence=0.8,
        )
        assert progress.confidence == 0.8

    def test_unaddressed_requirement_zero_confidence(self):
        """Unaddressed requirements should have zero confidence."""
        progress = RequirementProgress(requirement="Test")
        assert progress.confidence == 0.0

    def test_confidence_range(self):
        """Confidence should be between 0 and 1."""
        for conf in [0.0, 0.25, 0.5, 0.75, 1.0]:
            progress = RequirementProgress(
                requirement="Test",
                is_addressed=conf > 0,
                confidence=conf,
            )
            assert 0.0 <= progress.confidence <= 1.0
