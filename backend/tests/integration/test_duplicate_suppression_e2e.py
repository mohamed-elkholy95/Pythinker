"""Integration Tests for Duplicate Query Suppression (E2E)

End-to-end tests for duplicate query detection and suppression.
"""

import asyncio

import pytest

from app.domain.services.agents.duplicate_query_policy import DuplicateQueryPolicy
from app.infrastructure.observability.agent_metrics import (
    agent_duplicate_query_blocked,
    agent_duplicate_query_override,
)


class TestDuplicateSuppressionE2E:
    """End-to-end test suite for duplicate query suppression."""

    @pytest.fixture
    def policy(self):
        """Create policy with 5-minute window."""
        return DuplicateQueryPolicy(window_minutes=5, quality_threshold=0.5)

    @pytest.mark.asyncio
    async def test_duplicate_query_suppressed(self, policy):
        """E2E: Duplicate search query suppressed within time window."""
        # Setup: Execute search query
        tool_name = "search"
        args = {"query": "machine learning tutorials", "limit": 10}

        # Step 1: First execution - record it
        policy.record_execution(
            tool_name=tool_name,
            args=args,
            success=True,
            quality_score=0.85,  # High quality
            result_data={"results": ["result1", "result2", "result3"]},
        )

        # Step 2: Attempt same query again (duplicate)
        should_suppress, reason = policy.should_suppress(
            tool_name=tool_name,
            args=args,
            force_retry=False,
        )

        # Verify: Duplicate suppressed
        assert should_suppress is True
        assert reason == "duplicate_within_window"

        # Step 3: Verify metrics tracked
        suppression_count = agent_duplicate_query_blocked.get(
            {
                "tool_name": tool_name,
                "suppression_reason": "duplicate_within_window",
            }
        )
        assert suppression_count > 0

        # Step 4: Different query should NOT be suppressed
        different_args = {"query": "deep learning", "limit": 10}
        should_suppress_diff, reason_diff = policy.should_suppress(
            tool_name=tool_name,
            args=different_args,
            force_retry=False,
        )

        assert should_suppress_diff is False
        assert reason_diff == "not_duplicate"

    @pytest.mark.asyncio
    async def test_duplicate_query_override_low_quality(self, policy):
        """E2E: Duplicate query allowed if previous result was low quality."""
        # Setup: Execute query with LOW quality result
        tool_name = "search"
        args = {"query": "python best practices", "limit": 5}

        # Step 1: Record low-quality result
        policy.record_execution(
            tool_name=tool_name,
            args=args,
            success=True,
            quality_score=0.25,  # Low quality (below 0.5 threshold)
            result_data={"results": ["poor_result"]},
        )

        # Step 2: Attempt same query again
        should_suppress, reason = policy.should_suppress(
            tool_name=tool_name,
            args=args,
            force_retry=False,
        )

        # Verify: NOT suppressed due to low quality
        assert should_suppress is False
        assert reason == "low_quality_result"

        # Step 3: Verify override metric
        override_count = agent_duplicate_query_override.get({"override_reason": "low_quality_result"})
        assert override_count > 0

        # Step 4: Now record HIGH quality result
        policy.record_execution(
            tool_name=tool_name,
            args=args,
            success=True,
            quality_score=0.90,  # High quality
            result_data={"results": ["good1", "good2", "good3"]},
        )

        # Step 5: Attempt again - should be suppressed now
        should_suppress_high, reason_high = policy.should_suppress(
            tool_name=tool_name,
            args=args,
            force_retry=False,
        )

        assert should_suppress_high is True
        assert reason_high == "duplicate_within_window"

    @pytest.mark.asyncio
    async def test_explicit_retry_override(self, policy):
        """E2E: force_retry bypasses suppression."""
        # Setup: Execute query successfully
        tool_name = "browser"
        args = {"url": "https://example.com", "timeout": 5000}

        # Step 1: Record successful execution
        policy.record_execution(
            tool_name=tool_name,
            args=args,
            success=True,
            quality_score=0.95,  # Very high quality
        )

        # Step 2: Attempt duplicate WITHOUT force_retry
        should_suppress, reason = policy.should_suppress(
            tool_name=tool_name,
            args=args,
            force_retry=False,
        )

        assert should_suppress is True
        assert reason == "duplicate_within_window"

        # Step 3: Attempt duplicate WITH force_retry
        should_suppress_force, reason_force = policy.should_suppress(
            tool_name=tool_name,
            args=args,
            force_retry=True,  # Explicit retry
        )

        # Verify: NOT suppressed due to explicit retry
        assert should_suppress_force is False
        assert reason_force == "explicit_retry"

        # Step 4: Verify override metric
        explicit_override_count = agent_duplicate_query_override.get({"override_reason": "explicit_retry"})
        assert explicit_override_count > 0

    @pytest.mark.asyncio
    async def test_suppression_metrics_tracked(self, policy):
        """E2E: Suppression and override metrics tracked correctly."""
        # Test various scenarios and verify all metrics

        # Scenario 1: Successful suppression
        initial_blocked = agent_duplicate_query_blocked.get(
            {
                "tool_name": "search",
                "suppression_reason": "duplicate_within_window",
            }
        )

        policy.record_execution("search", {"query": "test1"}, True, 0.9)
        policy.should_suppress("search", {"query": "test1"}, False)

        final_blocked = agent_duplicate_query_blocked.get(
            {
                "tool_name": "search",
                "suppression_reason": "duplicate_within_window",
            }
        )
        assert final_blocked > initial_blocked

        # Scenario 2: Low quality override
        initial_quality_override = agent_duplicate_query_override.get({"override_reason": "low_quality_result"})

        policy.record_execution("search", {"query": "test2"}, True, 0.3)  # Low quality
        policy.should_suppress("search", {"query": "test2"}, False)

        final_quality_override = agent_duplicate_query_override.get({"override_reason": "low_quality_result"})
        assert final_quality_override > initial_quality_override

        # Scenario 3: Previous failure override
        initial_failure_override = agent_duplicate_query_override.get({"override_reason": "previous_failure"})

        policy.record_execution("browser", {"url": "https://test.com"}, False, 0.0)  # Failed
        policy.should_suppress("browser", {"url": "https://test.com"}, False)

        final_failure_override = agent_duplicate_query_override.get({"override_reason": "previous_failure"})
        assert final_failure_override > initial_failure_override

        # Scenario 4: Explicit retry override
        initial_explicit_override = agent_duplicate_query_override.get({"override_reason": "explicit_retry"})

        policy.record_execution("file_read", {"path": "/test.txt"}, True, 0.95)
        policy.should_suppress("file_read", {"path": "/test.txt"}, True)  # force_retry

        final_explicit_override = agent_duplicate_query_override.get({"override_reason": "explicit_retry"})
        assert final_explicit_override > initial_explicit_override

    @pytest.mark.asyncio
    async def test_time_window_expiration(self, policy):
        """E2E: Suppression window expires after configured time."""
        # Use short window for testing
        short_policy = DuplicateQueryPolicy(window_minutes=0.01, quality_threshold=0.5)  # ~0.6 seconds

        # Record execution
        short_policy.record_execution(
            "search",
            {"query": "window test"},
            True,
            0.9,
        )

        # Immediately: should suppress
        should_suppress_immediate, _ = short_policy.should_suppress(
            "search",
            {"query": "window test"},
            False,
        )
        assert should_suppress_immediate is True

        # Wait for window to expire
        await asyncio.sleep(1)

        # After expiration: should NOT suppress
        should_suppress_expired, reason_expired = short_policy.should_suppress(
            "search",
            {"query": "window test"},
            False,
        )
        assert should_suppress_expired is False
        assert reason_expired == "not_duplicate"

    @pytest.mark.asyncio
    async def test_different_tools_independent(self, policy):
        """E2E: Duplicate suppression is tool-specific."""
        # Same args, different tools
        args = {"target": "example.com"}

        # Record for 'ping' tool
        policy.record_execution("ping", args, True, 0.9)

        # Query 'ping' - should suppress
        should_suppress_ping, _ = policy.should_suppress("ping", args, False)
        assert should_suppress_ping is True

        # Query 'traceroute' with same args - should NOT suppress (different tool)
        should_suppress_trace, reason_trace = policy.should_suppress("traceroute", args, False)
        assert should_suppress_trace is False
        assert reason_trace == "not_duplicate"

    @pytest.mark.asyncio
    async def test_quality_threshold_boundary(self, policy):
        """E2E: Quality threshold boundary conditions."""
        # Exactly at threshold (0.5)
        policy.record_execution("search", {"query": "boundary_test"}, True, 0.5)
        should_suppress_at, _ = policy.should_suppress("search", {"query": "boundary_test"}, False)
        # At threshold: should suppress (>= threshold)
        assert should_suppress_at is True

        # Just below threshold (0.49)
        policy.record_execution("search", {"query": "below_test"}, True, 0.49)
        should_suppress_below, reason_below = policy.should_suppress("search", {"query": "below_test"}, False)
        # Below threshold: should override
        assert should_suppress_below is False
        assert reason_below == "low_quality_result"

        # Just above threshold (0.51)
        policy.record_execution("search", {"query": "above_test"}, True, 0.51)
        should_suppress_above, _ = policy.should_suppress("search", {"query": "above_test"}, False)
        # Above threshold: should suppress
        assert should_suppress_above is True

    @pytest.mark.asyncio
    async def test_argument_order_independence(self, policy):
        """E2E: Argument order doesn't affect duplicate detection."""
        # Same args, different order
        args1 = {"query": "test", "limit": 10, "offset": 0}
        args2 = {"offset": 0, "limit": 10, "query": "test"}

        # Record first version
        policy.record_execution("search", args1, True, 0.9)

        # Query with reordered args
        should_suppress, _ = policy.should_suppress("search", args2, False)

        # Should still suppress (same semantic query)
        assert should_suppress is True

    @pytest.mark.asyncio
    async def test_result_data_storage(self, policy):
        """E2E: Result data stored and retrievable."""
        tool_name = "search"
        args = {"query": "data test"}
        result_data = {
            "results": ["result1", "result2"],
            "total_count": 2,
            "query_time_ms": 150,
        }

        # Record with result data
        policy.record_execution(
            tool_name=tool_name,
            args=args,
            success=True,
            quality_score=0.9,
            result_data=result_data,
        )

        # Retrieve cached result
        signature = policy.generate_signature(tool_name, args)
        cached = policy._cache.get(signature)

        # Verify result data stored
        assert cached is not None
        assert cached.result_data == result_data
        assert cached.result_data["results"] == ["result1", "result2"]
        assert cached.result_data["total_count"] == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, policy):
        """E2E: Cleanup removes expired entries."""
        # Use short window
        short_policy = DuplicateQueryPolicy(window_minutes=0.01)

        # Add multiple entries
        for i in range(5):
            short_policy.record_execution(
                "search",
                {"query": f"cleanup_test_{i}"},
                True,
                0.9,
            )

        # Verify entries exist
        assert len(short_policy._cache._cache) == 5

        # Wait for expiration
        await asyncio.sleep(1)

        # Cleanup
        removed = short_policy.cleanup()

        # Verify all expired entries removed
        assert removed == 5
        assert len(short_policy._cache._cache) == 0

    @pytest.mark.asyncio
    async def test_stats_reporting(self, policy):
        """E2E: Policy stats accurate."""
        # Add some entries
        policy.record_execution("search", {"query": "stats1"}, True, 0.9)
        policy.record_execution("search", {"query": "stats2"}, True, 0.8)
        policy.record_execution("browser", {"url": "test.com"}, True, 0.7)

        # Get stats
        stats = policy.get_stats()

        # Verify stats
        assert stats["window_minutes"] == 5
        assert stats["quality_threshold"] == 0.5
        assert stats["cached_queries"] == 3
