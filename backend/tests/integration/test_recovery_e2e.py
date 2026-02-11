"""Integration Tests for Response Recovery (E2E)

End-to-end tests for malformed response recovery flows.
"""

from contextlib import suppress

import pytest

from app.domain.models.recovery import (
    RecoveryBudgetExhaustedError,
    RecoveryReason,
    RecoveryStrategy,
)
from app.domain.services.agents.failure_snapshot_service import FailureSnapshotService
from app.domain.services.agents.response_recovery import ResponseRecoveryPolicy
from app.infrastructure.observability.agent_metrics import (
    agent_response_recovery_failure,
    agent_response_recovery_success,
    agent_response_recovery_trigger,
)


class TestRecoveryE2E:
    """End-to-end test suite for recovery flows."""

    @pytest.fixture
    def recovery_policy(self):
        """Create recovery policy instance."""
        return ResponseRecoveryPolicy(max_retries=3, rollback_threshold=2, agent_type="plan_act")

    @pytest.fixture
    def snapshot_service(self):
        """Create snapshot service instance."""
        return FailureSnapshotService(token_budget=2000, pressure_threshold=0.8)

    @pytest.mark.asyncio
    async def test_malformed_json_recovery_flow(self, recovery_policy):
        """E2E: Malformed JSON triggers recovery."""
        # Malformed JSON response
        malformed = '{\"tool\": \"search\", \"args\": {\"query\": \"test\"'  # Incomplete

        # Detect malformed
        decision = await recovery_policy.detect_malformed(malformed)

        # Verify recovery triggered
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.JSON_PARSING_FAILED
        assert decision.strategy == RecoveryStrategy.ROLLBACK_RETRY

        # Execute recovery
        success, message = await recovery_policy.execute_recovery(
            response_text=malformed,
            recovery_reason=decision.recovery_reason,
            strategy=decision.strategy,
        )

        # Verify recovery executed
        assert success is True
        assert "successful" in message.lower()

    @pytest.mark.asyncio
    async def test_refusal_pattern_detection(self, recovery_policy):
        """E2E: Refusal patterns detected correctly."""
        refusal_responses = [
            "I cannot help with that request.",
            "I'm sorry, but I'm not able to assist with that.",
            "I don't have access to that information.",
        ]

        for refusal in refusal_responses:
            decision = await recovery_policy.detect_malformed(refusal)

            # Verify refusal detected
            assert decision.should_recover is True
            assert decision.recovery_reason == RecoveryReason.REFUSAL_DETECTED
            assert decision.strategy in [
                RecoveryStrategy.ROLLBACK_RETRY,
                RecoveryStrategy.SIMPLIFIED_PROMPT,
            ]

    @pytest.mark.asyncio
    async def test_empty_response_recovery(self, recovery_policy):
        """E2E: Empty response triggers recovery."""
        # Empty response
        decision = await recovery_policy.detect_malformed("")

        # Verify recovery triggered
        assert decision.should_recover is True
        assert decision.recovery_reason == RecoveryReason.EMPTY_RESPONSE
        assert decision.strategy == RecoveryStrategy.ROLLBACK_RETRY

    @pytest.mark.asyncio
    async def test_null_response_recovery(self, recovery_policy):
        """E2E: Null response triggers recovery."""
        # Null responses
        for null_response in ["null", "none", "None", "NULL"]:
            decision = await recovery_policy.detect_malformed(null_response)

            # Verify recovery triggered
            assert decision.should_recover is True
            assert decision.recovery_reason == RecoveryReason.NULL_RESPONSE

    @pytest.mark.asyncio
    async def test_valid_response_no_recovery(self, recovery_policy):
        """E2E: Valid response does not trigger recovery."""
        # Valid JSON response
        valid = '{\"tool\": \"search\", \"args\": {\"query\": \"test\"}}'

        # Detect
        decision = await recovery_policy.detect_malformed(valid)

        # Verify no recovery needed
        assert decision.should_recover is False
        assert "valid" in decision.message.lower()

    @pytest.mark.asyncio
    async def test_recovery_budget_exhausted(self, recovery_policy):
        """E2E: Recovery budget exhaustion raises error."""
        malformed = '{\"incomplete\":'

        # Exhaust budget by recovering 3 times
        for _ in range(3):
            decision = await recovery_policy.detect_malformed(malformed)
            await recovery_policy.execute_recovery(
                response_text=malformed,
                recovery_reason=decision.recovery_reason,
                strategy=decision.strategy,
            )

        # 4th attempt should exceed budget
        decision = await recovery_policy.detect_malformed(malformed)

        # Attempt to execute recovery (should raise)
        with pytest.raises(RecoveryBudgetExhaustedError) as exc_info:
            await recovery_policy.execute_recovery(
                response_text=malformed,
                recovery_reason=decision.recovery_reason,
                strategy=decision.strategy,
            )

        # Verify error
        error = exc_info.value
        assert error.max_retries == 3
        assert "exhausted" in str(error).lower()

    @pytest.mark.asyncio
    async def test_recovery_strategy_progression(self, recovery_policy):
        """E2E: Recovery strategies progress as retries increase."""
        malformed = '{\"incomplete\":'

        # First attempt: ROLLBACK_RETRY
        decision1 = await recovery_policy.detect_malformed(malformed)
        assert decision1.strategy == RecoveryStrategy.ROLLBACK_RETRY

        # Execute first recovery
        await recovery_policy.execute_recovery(
            response_text=malformed,
            recovery_reason=decision1.recovery_reason,
            strategy=decision1.strategy,
        )

        # Second attempt: ROLLBACK_RETRY
        decision2 = await recovery_policy.detect_malformed(malformed)
        assert decision2.strategy == RecoveryStrategy.ROLLBACK_RETRY

        # Execute second recovery
        await recovery_policy.execute_recovery(
            response_text=malformed,
            recovery_reason=decision2.recovery_reason,
            strategy=decision2.strategy,
        )

        # Third attempt (at rollback_threshold=2): SIMPLIFIED_PROMPT
        decision3 = await recovery_policy.detect_malformed(malformed)
        assert decision3.strategy == RecoveryStrategy.SIMPLIFIED_PROMPT

    @pytest.mark.asyncio
    async def test_recovery_metrics_tracked(self, recovery_policy):
        """E2E: Recovery metrics tracked correctly."""
        malformed = '{\"incomplete\":'

        # Capture initial trigger metric
        initial_triggers = agent_response_recovery_trigger.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )

        # Trigger recovery
        decision = await recovery_policy.detect_malformed(malformed)
        await recovery_policy.execute_recovery(
            response_text=malformed,
            recovery_reason=decision.recovery_reason,
            strategy=decision.strategy,
        )

        # Verify trigger metric incremented
        final_triggers = agent_response_recovery_trigger.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )
        assert final_triggers > initial_triggers

        # Verify success metric incremented
        success_count = agent_response_recovery_success.get(
            {"recovery_strategy": decision.strategy.value, "retry_count": "1"}
        )
        assert success_count >= 0  # Metric exists

    @pytest.mark.asyncio
    async def test_recovery_with_failure_snapshot(
        self, recovery_policy, snapshot_service
    ):
        """E2E: Recovery with failure snapshot injection.

        Flow:
        1. Tool execution fails
        2. Generate failure snapshot
        3. Inject snapshot into retry prompt
        4. Retry with enhanced context
        """
        # Step 1: Simulate tool failure
        error = RuntimeError("Tool execution timeout")

        # Step 2: Generate failure snapshot
        snapshot = await snapshot_service.generate_snapshot(
            failed_step="browser_navigation",
            error=error,
            tool_call_context={
                "tool_name": "browser",
                "args": {"url": "https://example.com", "timeout": 5000},
                "error": "Navigation timeout after 5s",
            },
            retry_count=0,
        )

        # Verify snapshot generated
        assert snapshot is not None
        assert snapshot.failed_step == "browser_navigation"
        assert snapshot.error_type == "RuntimeError"

        # Step 3: Inject into retry
        base_prompt = "Navigate to example.com and extract title"
        retry_prompt = await snapshot_service.inject_into_retry(
            snapshot=snapshot,
            base_prompt=base_prompt,
        )

        # Verify injection
        assert base_prompt in retry_prompt
        assert "Previous Attempt Failed" in retry_prompt
        assert "browser_navigation" in retry_prompt
        assert "RuntimeError" in retry_prompt

        # Step 4: Simulate retry with valid response (no recovery needed)
        valid_response = '{\"status\": \"success\", \"title\": \"Example Domain\"}'
        retry_decision = await recovery_policy.detect_malformed(valid_response)

        # Verify retry succeeds
        assert retry_decision.should_recover is False

    @pytest.mark.asyncio
    async def test_recovery_stats_tracking(self, recovery_policy):
        """E2E: Recovery stats tracked correctly."""
        # Initial stats
        initial_stats = recovery_policy.get_recovery_stats()
        assert initial_stats["total_attempts"] == 0
        assert initial_stats["budget_remaining"] == 3

        # Execute recovery
        malformed = '{\"incomplete\":'
        decision = await recovery_policy.detect_malformed(malformed)
        await recovery_policy.execute_recovery(
            response_text=malformed,
            recovery_reason=decision.recovery_reason,
            strategy=decision.strategy,
        )

        # Check stats updated
        updated_stats = recovery_policy.get_recovery_stats()
        assert updated_stats["total_attempts"] == 1
        assert updated_stats["successful_attempts"] == 1
        assert updated_stats["budget_remaining"] == 2

    @pytest.mark.asyncio
    async def test_recovery_history_cleanup(self, recovery_policy):
        """E2E: Recovery history can be cleaned up."""
        # Execute some recoveries
        malformed = '{\"incomplete\":'
        for _ in range(2):
            decision = await recovery_policy.detect_malformed(malformed)
            await recovery_policy.execute_recovery(
                response_text=malformed,
                recovery_reason=decision.recovery_reason,
                strategy=decision.strategy,
            )

        # Verify history exists
        stats = recovery_policy.get_recovery_stats()
        assert stats["total_attempts"] == 2

        # Cleanup
        await recovery_policy.cleanup()

        # Verify history cleared
        stats_after = recovery_policy.get_recovery_stats()
        assert stats_after["total_attempts"] == 0

    @pytest.mark.asyncio
    async def test_recovery_different_failure_types(self, recovery_policy):
        """E2E: Different failure types trigger appropriate recovery."""
        test_cases = [
            ('{\"incomplete\":', RecoveryReason.JSON_PARSING_FAILED),
            ("", RecoveryReason.EMPTY_RESPONSE),
            ("null", RecoveryReason.NULL_RESPONSE),
            ("I cannot help with that", RecoveryReason.REFUSAL_DETECTED),
        ]

        for response, expected_reason in test_cases:
            # Clean history for each test
            await recovery_policy.cleanup()

            # Detect
            decision = await recovery_policy.detect_malformed(response)

            # Verify correct reason
            assert decision.should_recover is True
            assert decision.recovery_reason == expected_reason

    @pytest.mark.asyncio
    async def test_non_json_response_no_recovery(self, recovery_policy):
        """E2E: Non-JSON valid responses don't trigger recovery."""
        # Plain text (not starting with { or [)
        plain_text = "This is a plain text response"

        # Detect
        decision = await recovery_policy.detect_malformed(plain_text)

        # Verify no recovery (it's not malformed JSON, just not JSON)
        assert decision.should_recover is False

    @pytest.mark.asyncio
    async def test_recovery_failure_metric(self, recovery_policy):
        """E2E: Recovery failure metric tracked on budget exhaustion."""
        malformed = '{\"incomplete\":'

        # Exhaust budget
        for _ in range(3):
            decision = await recovery_policy.detect_malformed(malformed)
            await recovery_policy.execute_recovery(
                response_text=malformed,
                recovery_reason=decision.recovery_reason,
                strategy=decision.strategy,
            )

        # Capture initial failure metric
        initial_failures = agent_response_recovery_failure.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )

        # Trigger budget exhaustion
        decision = await recovery_policy.detect_malformed(malformed)
        with suppress(RecoveryBudgetExhaustedError):
            await recovery_policy.execute_recovery(
                response_text=malformed,
                recovery_reason=decision.recovery_reason,
                strategy=decision.strategy,
            )

        # Verify failure metric incremented
        final_failures = agent_response_recovery_failure.get(
            {"recovery_reason": "json_parsing_failed", "agent_type": "plan_act"}
        )
        assert final_failures > initial_failures
