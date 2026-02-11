"""Tests for Response Recovery Policy (Workstream A)

Test coverage for malformed output detection and recovery strategies.
"""

import pytest

from app.domain.models.recovery import (
    RecoveryBudgetExhaustedError,
    RecoveryReason,
    RecoveryStrategy,
)
from app.domain.services.agents.response_recovery import ResponseRecoveryPolicy
from app.infrastructure.observability.agent_metrics import (
    agent_response_recovery_success,
    agent_response_recovery_trigger,
)


class TestResponseRecoveryPolicy:
    """Test suite for response recovery policy."""

    @pytest.fixture
    async def recovery_policy(self):
        """Create recovery policy instance for testing."""
        policy = ResponseRecoveryPolicy(max_retries=3, rollback_threshold=2)
        yield policy
        await policy.cleanup()

    @pytest.mark.asyncio
    async def test_detect_malformed_json(self, recovery_policy):
        """Test detection of malformed JSON responses."""
        # Test incomplete JSON
        decision = await recovery_policy.detect_malformed('{"incomplete":')
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.JSON_PARSING_FAILED
        assert decision.retry_count == 0

    @pytest.mark.asyncio
    async def test_detect_refusal_pattern(self, recovery_policy):
        """Test detection of refusal patterns."""
        # Test various refusal patterns
        refusal_responses = [
            "I cannot help with that",
            "I'm sorry, but I cannot provide that information",
            "I don't have access to that data",
        ]

        for response in refusal_responses:
            decision = await recovery_policy.detect_malformed(response)
            assert decision.should_recover is True
            assert decision.recovery_reason == RecoveryReason.REFUSAL_DETECTED

    @pytest.mark.asyncio
    async def test_detect_empty_response(self, recovery_policy):
        """Test detection of empty responses."""
        # Test empty string
        decision = await recovery_policy.detect_malformed("")
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.EMPTY_RESPONSE

        # Test whitespace only
        decision = await recovery_policy.detect_malformed("   ")
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.EMPTY_RESPONSE

        # Test None
        decision = await recovery_policy.detect_malformed(None)
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.EMPTY_RESPONSE

    @pytest.mark.asyncio
    async def test_detect_null_response(self, recovery_policy):
        """Test detection of null responses."""
        decision = await recovery_policy.detect_malformed("null")
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.NULL_RESPONSE

        decision = await recovery_policy.detect_malformed("None")
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.NULL_RESPONSE

    @pytest.mark.asyncio
    async def test_valid_response_not_flagged(self, recovery_policy):
        """Test that valid responses are not flagged for recovery."""
        decision = await recovery_policy.detect_malformed('{"status": "success"}')
        assert decision.should_recover is False

    @pytest.mark.asyncio
    async def test_recovery_budget_enforcement(self, recovery_policy):
        """Test retry budget limits."""
        # Simulate 3 recovery attempts
        for _i in range(3):
            success, _msg = await recovery_policy.execute_recovery(
                response_text='{"incomplete":',
                recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
                strategy=RecoveryStrategy.ROLLBACK_RETRY,
            )
            assert success is True

        # 4th attempt should raise budget exhausted
        with pytest.raises(RecoveryBudgetExhaustedError) as exc_info:
            await recovery_policy.execute_recovery(
                response_text='{"incomplete":',
                recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
                strategy=RecoveryStrategy.ROLLBACK_RETRY,
            )

        assert exc_info.value.attempt_count == 3
        assert exc_info.value.max_retries == 3

    @pytest.mark.asyncio
    async def test_recovery_success_metrics(self, recovery_policy):
        """Test recovery success metrics are incremented."""
        # Get initial count
        initial_count = agent_response_recovery_success.get({"recovery_strategy": "rollback_retry", "retry_count": "1"})

        # Execute recovery
        await recovery_policy.execute_recovery(
            response_text='{"incomplete":',
            recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
            strategy=RecoveryStrategy.ROLLBACK_RETRY,
        )

        # Verify metric incremented
        final_count = agent_response_recovery_success.get({"recovery_strategy": "rollback_retry", "retry_count": "1"})
        assert final_count > initial_count

    @pytest.mark.asyncio
    async def test_recovery_trigger_metrics(self, recovery_policy):
        """Test recovery trigger metrics are incremented."""
        # Get initial count
        initial_count = agent_response_recovery_trigger.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )

        # Execute recovery
        await recovery_policy.execute_recovery(
            response_text='{"incomplete":',
            recovery_reason=RecoveryReason.JSON_PARSING_FAILED,
            strategy=RecoveryStrategy.ROLLBACK_RETRY,
        )

        # Verify metric incremented
        final_count = agent_response_recovery_trigger.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )
        assert final_count > initial_count

    @pytest.mark.asyncio
    async def test_strategy_selection_progression(self, recovery_policy):
        """Test strategy selection changes with retry count."""
        # First attempt: rollback_retry
        decision1 = await recovery_policy.detect_malformed('{"incomplete":')
        assert decision1.strategy == RecoveryStrategy.ROLLBACK_RETRY

        # Simulate first recovery
        await recovery_policy.execute_recovery(
            '{"incomplete":',
            RecoveryReason.JSON_PARSING_FAILED,
            RecoveryStrategy.ROLLBACK_RETRY,
        )

        # Second attempt: still rollback_retry
        decision2 = await recovery_policy.detect_malformed('{"incomplete":')
        assert decision2.strategy == RecoveryStrategy.ROLLBACK_RETRY

        # Simulate second recovery
        await recovery_policy.execute_recovery(
            '{"incomplete":',
            RecoveryReason.JSON_PARSING_FAILED,
            RecoveryStrategy.ROLLBACK_RETRY,
        )

        # Third attempt: simplified_prompt (at threshold)
        decision3 = await recovery_policy.detect_malformed('{"incomplete":')
        assert decision3.strategy == RecoveryStrategy.SIMPLIFIED_PROMPT

    @pytest.mark.asyncio
    async def test_recovery_stats(self, recovery_policy):
        """Test get_recovery_stats returns correct information."""
        # Initial stats
        stats = recovery_policy.get_recovery_stats()
        assert stats["total_attempts"] == 0
        assert stats["budget_remaining"] == 3

        # After one recovery
        await recovery_policy.execute_recovery(
            '{"incomplete":',
            RecoveryReason.JSON_PARSING_FAILED,
            RecoveryStrategy.ROLLBACK_RETRY,
        )

        stats = recovery_policy.get_recovery_stats()
        assert stats["total_attempts"] == 1
        assert stats["successful_attempts"] == 1
        assert stats["budget_remaining"] == 2
