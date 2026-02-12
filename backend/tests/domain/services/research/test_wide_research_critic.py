"""Tests for Wide Research Orchestrator integration with CriticAgent.

Tests the synthesize_with_review method which implements the self-correction
pattern:
1. Synthesize initial result
2. Critic reviews
3. If not approved, revise and re-review (up to max_revisions)

This implements Task 7.2 of the Pythinker AI Agent patterns.
"""

from unittest.mock import AsyncMock

import pytest

from app.domain.models.research_task import ResearchTask
from app.domain.services.agents.critic_agent import CriticAgent, CriticResult
from app.domain.services.research.wide_research import WideResearchOrchestrator


@pytest.fixture
def mock_critic():
    """Mock critic that approves outputs."""
    critic = AsyncMock(spec=CriticAgent)
    critic.review = AsyncMock(
        return_value=CriticResult(
            approved=True,
            feedback="Good quality research",
            issues=[],
        )
    )
    return critic


@pytest.fixture
def mock_rejecting_critic():
    """Mock critic that rejects on first call, then approves."""
    critic = AsyncMock(spec=CriticAgent)
    call_count = 0

    async def review_with_state(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CriticResult(
                approved=False,
                feedback="Needs more detail",
                issues=["Missing citations", "Incomplete analysis"],
                suggestions=["Add more sources", "Expand on key points"],
            )
        return CriticResult(
            approved=True,
            feedback="Much improved",
            issues=[],
        )

    critic.review = AsyncMock(side_effect=review_with_state)
    return critic


@pytest.fixture
def mock_always_rejecting_critic():
    """Mock critic that always rejects."""
    critic = AsyncMock(spec=CriticAgent)
    critic.review = AsyncMock(
        return_value=CriticResult(
            approved=False,
            feedback="Still not good enough",
            issues=["Persistent issues"],
            suggestions=["Major rewrite needed"],
        )
    )
    return critic


@pytest.fixture
def mock_llm():
    """Mock LLM for testing."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Synthesized result")
    return llm


@pytest.fixture
def mock_search_tool():
    """Mock search tool for testing."""
    tool = AsyncMock()
    tool.execute = AsyncMock(return_value={"results": [{"title": "Test", "content": "Result"}]})
    return tool


@pytest.fixture
def completed_tasks() -> list[ResearchTask]:
    """Create completed research tasks for testing."""
    tasks = [
        ResearchTask(query="Q1", parent_task_id="p1", index=0, total=2),
        ResearchTask(query="Q2", parent_task_id="p1", index=1, total=2),
    ]
    tasks[0].complete("Result 1", sources=["https://source1.com"])
    tasks[1].complete("Result 2", sources=["https://source2.com"])
    return tasks


class TestOrchestratorCriticInitialization:
    """Tests for critic parameter in orchestrator initialization."""

    def test_initialization_with_critic(self, mock_critic, mock_search_tool, mock_llm):
        """Test orchestrator initializes with critic parameter."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_critic,
        )

        assert orchestrator.critic is mock_critic

    def test_initialization_without_critic(self, mock_search_tool, mock_llm):
        """Test orchestrator initializes without critic (default None)."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
        )

        assert orchestrator.critic is None


class TestSynthesizeWithReview:
    """Tests for synthesize_with_review method."""

    @pytest.mark.asyncio
    async def test_synthesize_with_review_no_critic(self, mock_search_tool, mock_llm, completed_tasks):
        """Test synthesize_with_review returns synthesis without review when no critic."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
        )

        result = await orchestrator.synthesize_with_review(completed_tasks)

        # Should return synthesis directly without review
        assert result is not None
        # Should contain task queries in output (no LLM used without prompt)
        assert "Q1" in result or "Q2" in result

    @pytest.mark.asyncio
    async def test_research_with_critic_review(self, mock_critic, mock_search_tool, mock_llm, completed_tasks):
        """Test synthesize_with_review calls critic.review when critic provided."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_critic,
        )

        result = await orchestrator.synthesize_with_review(completed_tasks)

        mock_critic.review.assert_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_synthesize_with_review_approved_immediately(
        self, mock_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test synthesize_with_review returns immediately when approved."""
        mock_llm.complete = AsyncMock(return_value="High quality synthesis")
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_critic,
        )

        result = await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize findings",
        )

        # Critic approves on first call, so only 1 review call
        assert mock_critic.review.call_count == 1
        assert result == "High quality synthesis"

    @pytest.mark.asyncio
    async def test_synthesize_with_review_revision_loop(
        self, mock_rejecting_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test synthesize_with_review revises output when critic rejects."""
        original_response = "Initial synthesis"
        revised_response = "Improved synthesis"

        # LLM returns different results on subsequent calls
        mock_llm.complete = AsyncMock(side_effect=[original_response, revised_response])

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_rejecting_critic,
        )

        result = await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize findings",
            max_revisions=2,
        )

        # Should be called twice: once for rejection, once for approval
        assert mock_rejecting_critic.review.call_count == 2
        assert result == revised_response

    @pytest.mark.asyncio
    async def test_synthesize_with_review_max_revisions_reached(
        self, mock_always_rejecting_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test synthesize_with_review stops after max_revisions."""
        mock_llm.complete = AsyncMock(return_value="Synthesis attempt")

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_always_rejecting_critic,
        )

        result = await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize findings",
            max_revisions=3,
        )

        # Should stop after max_revisions attempts
        assert mock_always_rejecting_critic.review.call_count == 3
        # Should return last attempt even if not approved
        assert result is not None

    @pytest.mark.asyncio
    async def test_synthesize_with_review_revision_prompt_includes_feedback(
        self, mock_rejecting_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test that revision prompt includes critic issues and suggestions."""
        revision_prompts_received = []

        async def capture_prompt(prompt):
            revision_prompts_received.append(prompt)
            return "Revised output"

        mock_llm.complete = AsyncMock(side_effect=capture_prompt)

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_rejecting_critic,
        )

        await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize findings",
            max_revisions=2,
        )

        # Second call should be revision prompt
        assert len(revision_prompts_received) >= 2
        revision_prompt = revision_prompts_received[1]

        # Should contain issues from the critic
        assert "Missing citations" in revision_prompt
        assert "Incomplete analysis" in revision_prompt

        # Should contain suggestions from the critic
        assert "Add more sources" in revision_prompt
        assert "Expand on key points" in revision_prompt

    @pytest.mark.asyncio
    async def test_synthesize_with_review_default_max_revisions(
        self, mock_always_rejecting_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test that default max_revisions is 2."""
        mock_llm.complete = AsyncMock(return_value="Attempt")

        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_always_rejecting_critic,
        )

        await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize",
        )

        # Default max_revisions should be 2
        assert mock_always_rejecting_critic.review.call_count == 2

    @pytest.mark.asyncio
    async def test_synthesize_with_review_no_llm_no_revision(
        self, mock_rejecting_critic, mock_search_tool, completed_tasks
    ):
        """Test synthesize_with_review handles missing LLM gracefully."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=None,  # No LLM
            critic=mock_rejecting_critic,
        )

        result = await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize",
        )

        # Should return synthesis even without LLM (just combined findings)
        assert result is not None
        # Without LLM, cannot revise, so should only review once
        assert mock_rejecting_critic.review.call_count == 1

    @pytest.mark.asyncio
    async def test_synthesize_with_review_uses_correct_criteria(
        self, mock_critic, mock_search_tool, mock_llm, completed_tasks
    ):
        """Test that critic.review is called with correct criteria."""
        orchestrator = WideResearchOrchestrator(
            session_id="test",
            search_tool=mock_search_tool,
            llm=mock_llm,
            critic=mock_critic,
        )

        await orchestrator.synthesize_with_review(
            completed_tasks,
            synthesis_prompt="Summarize findings",
        )

        # Verify review was called with the expected criteria
        mock_critic.review.assert_called_once()
        call_kwargs = mock_critic.review.call_args.kwargs

        assert call_kwargs.get("criteria") == ["accuracy", "completeness", "coherence"]
