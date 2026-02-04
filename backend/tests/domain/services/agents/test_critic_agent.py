"""Tests for Critic Agent.

Tests the CriticAgent class implementing the quality gate pattern
for self-correction loops. The critic reviews outputs against tasks
and criteria, providing approval/rejection decisions with feedback.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.agents.critic_agent import CriticAgent, CriticResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_llm():
    """Mock LLM that returns approved response."""
    llm = AsyncMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content='{"approved": true, "feedback": "Good quality", "issues": []}'
        )
    )
    return llm


@pytest.fixture
def mock_llm_reject():
    """Mock LLM that returns rejection response."""
    llm = AsyncMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content='{"approved": false, "feedback": "Missing sources", "issues": ["No citations"]}'
        )
    )
    return llm


# =============================================================================
# CriticResult Model Tests
# =============================================================================


class TestCriticResultModel:
    """Tests for the CriticResult Pydantic model."""

    def test_critic_result_with_required_fields(self):
        """Test CriticResult with only required fields."""
        result = CriticResult(approved=True, feedback="Looks good")

        assert result.approved is True
        assert result.feedback == "Looks good"
        assert result.issues == []
        assert result.suggestions == []
        assert result.score is None

    def test_critic_result_with_all_fields(self):
        """Test CriticResult with all fields populated."""
        result = CriticResult(
            approved=False,
            feedback="Needs improvement",
            issues=["Missing source", "Incomplete answer"],
            suggestions=["Add citations", "Expand explanation"],
            score=0.65,
        )

        assert result.approved is False
        assert result.feedback == "Needs improvement"
        assert len(result.issues) == 2
        assert "Missing source" in result.issues
        assert len(result.suggestions) == 2
        assert result.score == 0.65

    def test_critic_result_score_is_optional(self):
        """Test that score field is truly optional."""
        result = CriticResult(approved=True, feedback="Good")
        assert result.score is None

        result_with_score = CriticResult(approved=True, feedback="Good", score=0.95)
        assert result_with_score.score == 0.95


# =============================================================================
# CriticAgent Basic Tests (from spec)
# =============================================================================


class TestCriticAgentBasic:
    """Basic functionality tests from specification."""

    @pytest.mark.asyncio
    async def test_critic_reviews_output(self, mock_llm):
        """Test that critic can review output and return CriticResult."""
        critic = CriticAgent(session_id="test", llm=mock_llm)
        result = await critic.review(
            output="The capital of France is Paris.",
            task="What is the capital of France?",
            criteria=["accuracy", "completeness"],
        )

        assert isinstance(result, CriticResult)
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_critic_identifies_issues(self):
        """Test that critic identifies issues when output is problematic."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='{"approved": false, "feedback": "Missing sources", "issues": ["No citations"]}'
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="The answer is 42.",
            task="Explain the meaning of life with citations",
            criteria=["citations_required"],
        )

        assert result.approved is False
        assert len(result.issues) > 0


# =============================================================================
# CriticAgent Initialization Tests
# =============================================================================


class TestCriticAgentInitialization:
    """Tests for CriticAgent initialization."""

    def test_agent_initialization(self, mock_llm):
        """Test agent initializes with required parameters."""
        critic = CriticAgent(session_id="test_session", llm=mock_llm)

        assert critic.session_id == "test_session"
        assert critic.llm is mock_llm

    def test_agent_has_system_prompt(self, mock_llm):
        """Test agent has a system prompt defined."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        assert critic.SYSTEM_PROMPT is not None
        assert len(critic.SYSTEM_PROMPT) > 0
        assert "critic" in critic.SYSTEM_PROMPT.lower() or "review" in critic.SYSTEM_PROMPT.lower()


# =============================================================================
# CriticAgent Review Method Tests
# =============================================================================


class TestCriticAgentReview:
    """Tests for the review method."""

    @pytest.mark.asyncio
    async def test_review_calls_llm_with_messages(self, mock_llm):
        """Test that review method calls LLM with proper message structure."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        await critic.review(
            output="Test output",
            task="Test task",
            criteria=["accuracy"],
        )

        mock_llm.chat.assert_called_once()
        messages = mock_llm.chat.call_args[0][0]

        # Should have system and user messages
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_review_includes_task_in_prompt(self, mock_llm):
        """Test that task is included in the user prompt."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        await critic.review(
            output="Test output",
            task="What is the capital of France?",
            criteria=None,
        )

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "What is the capital of France?" in user_content

    @pytest.mark.asyncio
    async def test_review_includes_output_in_prompt(self, mock_llm):
        """Test that output is included in the user prompt."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        await critic.review(
            output="The capital is Paris.",
            task="Test task",
            criteria=None,
        )

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "The capital is Paris." in user_content

    @pytest.mark.asyncio
    async def test_review_includes_criteria_in_prompt(self, mock_llm):
        """Test that criteria are included in the user prompt."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        await critic.review(
            output="Test output",
            task="Test task",
            criteria=["accuracy", "completeness", "clarity"],
        )

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "accuracy" in user_content
        assert "completeness" in user_content
        assert "clarity" in user_content

    @pytest.mark.asyncio
    async def test_review_works_without_criteria(self, mock_llm):
        """Test that review works when criteria is None."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        result = await critic.review(
            output="Test output",
            task="Test task",
            criteria=None,
        )

        assert isinstance(result, CriticResult)


# =============================================================================
# JSON Parsing Tests
# =============================================================================


class TestCriticAgentJsonParsing:
    """Tests for JSON response parsing."""

    @pytest.mark.asyncio
    async def test_parses_json_response(self):
        """Test that critic parses JSON response correctly."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content=json.dumps({
                    "approved": True,
                    "feedback": "Well done",
                    "issues": [],
                    "suggestions": ["Consider adding examples"],
                    "score": 0.9,
                })
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        assert result.approved is True
        assert result.feedback == "Well done"
        assert result.suggestions == ["Consider adding examples"]
        assert result.score == 0.9

    @pytest.mark.asyncio
    async def test_handles_markdown_code_blocks(self):
        """Test that critic handles JSON wrapped in markdown code blocks."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='''```json
{"approved": true, "feedback": "Good work", "issues": []}
```'''
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        assert result.approved is True
        assert result.feedback == "Good work"

    @pytest.mark.asyncio
    async def test_handles_json_code_block_without_language(self):
        """Test that critic handles JSON in code blocks without language tag."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='''```
{"approved": false, "feedback": "Needs work", "issues": ["Issue 1"]}
```'''
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        assert result.approved is False
        assert "Issue 1" in result.issues

    @pytest.mark.asyncio
    async def test_fallback_for_non_json_response(self):
        """Test fallback when LLM returns non-JSON response."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content="This looks good to me! The output is accurate and complete."
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        # Should return a valid CriticResult even for non-JSON
        assert isinstance(result, CriticResult)
        # Fallback should interpret positive language as approved
        assert result.feedback != ""

    @pytest.mark.asyncio
    async def test_handles_missing_optional_fields(self):
        """Test handling of JSON response with missing optional fields."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value=MagicMock(
                content='{"approved": true, "feedback": "Good"}'
            )
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        assert result.approved is True
        assert result.feedback == "Good"
        assert result.issues == []
        assert result.suggestions == []
        assert result.score is None


# =============================================================================
# Batch Review Tests
# =============================================================================


class TestCriticAgentBatchReview:
    """Tests for the review_batch method."""

    @pytest.mark.asyncio
    async def test_batch_review_processes_multiple_items(self, mock_llm):
        """Test that batch review processes multiple outputs."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        outputs = [
            {"output": "Paris is the capital.", "task": "What is the capital of France?"},
            {"output": "Water is H2O.", "task": "What is water?"},
            {"output": "The sun is a star.", "task": "What is the sun?"},
        ]

        results = await critic.review_batch(outputs, criteria=["accuracy"])

        assert len(results) == 3
        assert all(isinstance(r, CriticResult) for r in results)

    @pytest.mark.asyncio
    async def test_batch_review_calls_review_for_each_item(self, mock_llm):
        """Test that batch review calls review method for each item."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        outputs = [
            {"output": "Output 1", "task": "Task 1"},
            {"output": "Output 2", "task": "Task 2"},
        ]

        await critic.review_batch(outputs, criteria=["accuracy"])

        # Should call LLM twice (once per item)
        assert mock_llm.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_review_passes_criteria_to_each_review(self, mock_llm):
        """Test that criteria is passed to each individual review."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        outputs = [
            {"output": "Output 1", "task": "Task 1"},
        ]

        await critic.review_batch(outputs, criteria=["accuracy", "completeness"])

        messages = mock_llm.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "accuracy" in user_content
        assert "completeness" in user_content

    @pytest.mark.asyncio
    async def test_batch_review_works_without_criteria(self, mock_llm):
        """Test that batch review works when criteria is None."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        outputs = [
            {"output": "Output 1", "task": "Task 1"},
        ]

        results = await critic.review_batch(outputs, criteria=None)

        assert len(results) == 1
        assert isinstance(results[0], CriticResult)

    @pytest.mark.asyncio
    async def test_batch_review_empty_list(self, mock_llm):
        """Test batch review with empty list returns empty list."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        results = await critic.review_batch([], criteria=["accuracy"])

        assert results == []
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_review_with_mixed_results(self):
        """Test batch review when some items pass and others fail."""
        llm = AsyncMock()
        call_count = 0

        async def mock_chat(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(
                    content='{"approved": true, "feedback": "Good", "issues": []}'
                )
            return MagicMock(
                content='{"approved": false, "feedback": "Bad", "issues": ["Problem"]}'
            )

        llm.chat = mock_chat

        critic = CriticAgent(session_id="test", llm=llm)

        outputs = [
            {"output": "Good output", "task": "Task 1"},
            {"output": "Bad output", "task": "Task 2"},
        ]

        results = await critic.review_batch(outputs)

        assert len(results) == 2
        assert results[0].approved is True
        assert results[1].approved is False


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestCriticAgentEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_handles_empty_output(self, mock_llm):
        """Test handling of empty output string."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        result = await critic.review(
            output="",
            task="Test task",
        )

        assert isinstance(result, CriticResult)

    @pytest.mark.asyncio
    async def test_handles_empty_task(self, mock_llm):
        """Test handling of empty task string."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        result = await critic.review(
            output="Test output",
            task="",
        )

        assert isinstance(result, CriticResult)

    @pytest.mark.asyncio
    async def test_handles_very_long_output(self, mock_llm):
        """Test handling of very long output."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        long_output = "A" * 10000
        result = await critic.review(
            output=long_output,
            task="Test task",
        )

        assert isinstance(result, CriticResult)

    @pytest.mark.asyncio
    async def test_handles_special_characters(self, mock_llm):
        """Test handling of special characters in input."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        result = await critic.review(
            output='Output with "quotes" and {braces}',
            task="Task with <tags> and &entities",
            criteria=["test\nwith\nnewlines"],
        )

        assert isinstance(result, CriticResult)

    @pytest.mark.asyncio
    async def test_handles_llm_returning_string_directly(self):
        """Test handling when LLM returns string instead of object with content."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value='{"approved": true, "feedback": "Good", "issues": []}'
        )

        critic = CriticAgent(session_id="test", llm=llm)
        result = await critic.review(
            output="Test output",
            task="Test task",
        )

        assert isinstance(result, CriticResult)
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_handles_unicode_content(self, mock_llm):
        """Test handling of Unicode content."""
        critic = CriticAgent(session_id="test", llm=mock_llm)

        result = await critic.review(
            output="Unicode: cafe, resume, naive",
            task="Test Unicode",
        )

        assert isinstance(result, CriticResult)
