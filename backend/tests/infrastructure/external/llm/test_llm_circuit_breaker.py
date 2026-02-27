"""Tests for semantic failure tracking in LLM JSON output.

Validates that llm_json_parse_failures_total is incremented when:
- ask_json returns None (no valid JSON found)
- ask_json_validated exhausts all retries
- ask_structured (OpenAI) exhausts all retries with JSONDecodeError
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUniversalLLMJsonTracking:
    """Test semantic failure tracking in UniversalLLM."""

    @pytest.mark.asyncio
    async def test_ask_json_increments_counter_on_failure(self):
        """ask_json should increment llm_json_parse_failures_total when no JSON found."""
        mock_counter = MagicMock()

        with patch(
            "app.core.prometheus_metrics.llm_json_parse_failures_total",
            mock_counter,
        ):
            from app.infrastructure.external.llm.universal_llm import UniversalLLM

            llm = UniversalLLM.__new__(UniversalLLM)
            llm._model_name = "test-model"
            llm._provider_name = "openai"
            llm._temperature = 0.7
            llm._max_tokens = 1024

            # Mock ask() to return non-JSON content
            llm.ask = AsyncMock(return_value={"content": "This is not JSON at all."})

            result = await llm.ask_json(messages=[{"role": "user", "content": "test"}])

            assert result is None
            mock_counter.inc.assert_called_once_with(
                {"model": "test-model", "method": "ask_json"}
            )

    @pytest.mark.asyncio
    async def test_ask_json_no_counter_on_success(self):
        """ask_json should NOT increment counter when valid JSON is returned."""
        mock_counter = MagicMock()

        with patch(
            "app.core.prometheus_metrics.llm_json_parse_failures_total",
            mock_counter,
        ):
            from app.infrastructure.external.llm.universal_llm import UniversalLLM

            llm = UniversalLLM.__new__(UniversalLLM)
            llm._model_name = "test-model"
            llm._provider_name = "openai"
            llm._temperature = 0.7
            llm._max_tokens = 1024

            # Mock ask() to return valid JSON
            llm.ask = AsyncMock(return_value={"content": '{"key": "value"}'})

            result = await llm.ask_json(messages=[{"role": "user", "content": "test"}])

            assert result == {"key": "value"}
            mock_counter.inc.assert_not_called()


class TestAskJsonValidatedTracking:
    """Test tracking in ask_json_validated on all retries exhausted."""

    @pytest.mark.asyncio
    async def test_ask_json_validated_increments_on_exhaustion(self):
        """ask_json_validated should increment counter when all retries fail."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            name: str

        mock_counter = MagicMock()

        with patch(
            "app.core.prometheus_metrics.llm_json_parse_failures_total",
            mock_counter,
        ):
            from app.infrastructure.external.llm.universal_llm import UniversalLLM

            llm = UniversalLLM.__new__(UniversalLLM)
            llm._model_name = "test-model"
            llm._provider_name = "openai"
            llm._temperature = 0.7
            llm._max_tokens = 1024

            # Mock ask() to always return non-JSON
            llm.ask = AsyncMock(return_value={"content": "Not valid JSON"})

            with pytest.raises(ValueError, match="ask_json_validated failed"):
                await llm.ask_json_validated(
                    messages=[{"role": "user", "content": "test"}],
                    response_model=TestModel,
                    max_retries=0,  # No retries - fail immediately
                )

            mock_counter.inc.assert_called_once_with(
                {"model": "test-model", "method": "ask_json_validated"}
            )
