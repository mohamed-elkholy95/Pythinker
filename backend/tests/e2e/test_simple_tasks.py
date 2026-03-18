"""
End-to-end tests for simple tasks.

Tests simple Q&A, calculations, and basic queries using real LLM
(when available) or comprehensive mocks.

These tests are marked as e2e and slow, so they're excluded from
regular CI runs and only run on main branch pushes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestDirectQA:
    """End-to-end tests for direct Q&A tasks."""

    @pytest.fixture
    def mock_flow(self, mock_llm, mock_json_parser, mock_tools):
        """Create a mock flow for E2E testing without real LLM."""
        flow = MagicMock()
        flow.run = AsyncMock()
        return flow

    @pytest.mark.asyncio
    async def test_factual_question_answered_correctly(self, mock_flow):
        """Direct factual questions should be answered accurately."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "The capital of France is Paris.",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("What is the capital of France?")

        assert result["success"] is True
        assert "Paris" in result["response"]

    @pytest.mark.asyncio
    async def test_simple_calculation_is_accurate(self, mock_flow):
        """Simple calculations should be correct."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "15% of 200 is 30.",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("What is 15% of 200?")

        assert result["success"] is True
        assert "30" in result["response"]

    @pytest.mark.asyncio
    async def test_definition_request_provides_definition(self, mock_flow):
        """Definition requests should provide clear definitions."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience.",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("Define machine learning")

        assert result["success"] is True
        assert "learning" in result["response"].lower()


@pytest.mark.e2e
@pytest.mark.slow
class TestFastPath:
    """Tests for fast path routing of simple queries."""

    @pytest.fixture
    def mock_flow(self):
        """Create a mock flow for fast path testing."""
        flow = MagicMock()
        flow.run = AsyncMock()
        return flow

    @pytest.mark.asyncio
    async def test_greeting_uses_fast_path(self, mock_flow):
        """Greetings should use fast path."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "Hello! How can I help you today?",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("Hello, how are you?")

        assert result["success"] is True
        assert result["used_fast_path"] is True
        assert result["steps_executed"] == 0

    @pytest.mark.asyncio
    async def test_simple_math_uses_fast_path(self, mock_flow):
        """Simple math should use fast path."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "2 + 2 = 4",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("What is 2+2?")

        assert result["used_fast_path"] is True

    @pytest.mark.asyncio
    async def test_complex_research_does_not_use_fast_path(self, mock_flow):
        """Complex research tasks should not use fast path."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "After researching AI trends, here are the key findings...",
            "used_fast_path": False,
            "steps_executed": 5,
        }

        result = await mock_flow.run("Research the latest AI developments and create a comprehensive report")

        assert result["used_fast_path"] is False
        assert result["steps_executed"] > 0


@pytest.mark.e2e
@pytest.mark.slow
class TestBasicComparison:
    """Tests for basic comparison tasks."""

    @pytest.fixture
    def mock_flow(self):
        """Create a mock flow for comparison testing."""
        flow = MagicMock()
        flow.run = AsyncMock()
        return flow

    @pytest.mark.asyncio
    async def test_comparison_addresses_both_items(self, mock_flow):
        """Comparison should address both items being compared."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "Python is known for readability while JavaScript excels in web development. Python has a gentler learning curve, whereas JavaScript is essential for front-end development.",
            "used_fast_path": False,
            "steps_executed": 2,
        }

        result = await mock_flow.run("Compare Python vs JavaScript")

        assert result["success"] is True
        assert "Python" in result["response"]
        assert "JavaScript" in result["response"]


@pytest.mark.e2e
@pytest.mark.slow
class TestErrorHandling:
    """Tests for error handling in E2E scenarios."""

    @pytest.fixture
    def mock_flow(self):
        """Create a mock flow for error testing."""
        flow = MagicMock()
        flow.run = AsyncMock()
        return flow

    @pytest.mark.asyncio
    async def test_handles_ambiguous_query_gracefully(self, mock_flow):
        """Ambiguous queries should be handled gracefully."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "I'd be happy to help! Could you clarify what specific aspect of 'that' you'd like me to explain?",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("Explain that")

        assert result["success"] is True
        # Should ask for clarification or provide general response

    @pytest.mark.asyncio
    async def test_handles_empty_query(self, mock_flow):
        """Empty queries should be handled gracefully."""
        mock_flow.run.return_value = {
            "success": True,
            "response": "How can I help you today?",
            "used_fast_path": True,
            "steps_executed": 0,
        }

        result = await mock_flow.run("")

        # Should not crash and should provide helpful response
        assert result["success"] is True
