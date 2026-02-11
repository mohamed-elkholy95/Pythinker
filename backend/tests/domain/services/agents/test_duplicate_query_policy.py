"""Tests for Duplicate Query Suppression Policy (Workstream D)

Test coverage for duplicate query detection and quality-aware override.
"""

import time

import pytest

from app.domain.services.agents.duplicate_query_policy import DuplicateQueryPolicy
from app.infrastructure.observability.agent_metrics import (
    agent_duplicate_query_blocked,
    agent_duplicate_query_override,
)


class TestDuplicateQueryPolicy:
    """Test suite for duplicate query suppression policy."""

    @pytest.fixture
    def policy(self):
        """Create policy instance with 5-minute window."""
        return DuplicateQueryPolicy(window_minutes=5, quality_threshold=0.5)

    def test_generate_signature_deterministic(self, policy):
        """Test signature generation is deterministic."""
        args1 = {"query": "test", "limit": 10}
        args2 = {"limit": 10, "query": "test"}  # Different order

        sig1 = policy.generate_signature("search", args1)
        sig2 = policy.generate_signature("search", args2)

        # Should be identical (order-independent)
        assert sig1 == sig2

    def test_generate_signature_unique(self, policy):
        """Test different queries generate different signatures."""
        args1 = {"query": "test1"}
        args2 = {"query": "test2"}

        sig1 = policy.generate_signature("search", args1)
        sig2 = policy.generate_signature("search", args2)

        assert sig1 != sig2

    def test_non_duplicate_allowed(self, policy):
        """Test non-duplicate queries are allowed."""
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=False)

        assert should_suppress is False
        assert reason == "not_duplicate"

    def test_duplicate_detection_within_window(self, policy):
        """Test duplicate queries detected within time window."""
        # First execution - record it
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.9,  # High quality
        )

        # Second execution - should be suppressed
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=False)

        assert should_suppress is True
        assert reason == "duplicate_within_window"

    def test_quality_aware_override_low_quality(self, policy):
        """Test override when previous result quality was low."""
        # Record low-quality result
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.2,  # Low quality (< 0.5 threshold)
        )

        # Should allow retry due to low quality
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=False)

        assert should_suppress is False
        assert reason == "low_quality_result"

    def test_quality_aware_override_high_quality(self, policy):
        """Test suppression when previous result quality was high."""
        # Record high-quality result
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.9,  # High quality
        )

        # Should suppress due to high quality
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=False)

        assert should_suppress is True
        assert reason == "duplicate_within_window"

    def test_previous_failure_override(self, policy):
        """Test override when previous execution failed."""
        # Record failed execution
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=False,  # Failed
            quality_score=0.0,
        )

        # Should allow retry due to previous failure
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=False)

        assert should_suppress is False
        assert reason == "previous_failure"

    def test_explicit_retry_override(self, policy):
        """Test force_retry parameter overrides suppression."""
        # Record successful execution
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.9,
        )

        # Should allow due to explicit retry flag
        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, force_retry=True)

        assert should_suppress is False
        assert reason == "explicit_retry"

    def test_bounded_window_expiration(self, policy):
        """Test suppression window is bounded (entries expire)."""
        # Create policy with very short window for testing
        short_policy = DuplicateQueryPolicy(window_minutes=0.01, quality_threshold=0.5)  # ~0.6 seconds

        # Record execution
        short_policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.9,
        )

        # Immediately: should suppress
        should_suppress, _ = short_policy.should_suppress("search", {"query": "test"}, force_retry=False)
        assert should_suppress is True

        # Wait for expiration
        time.sleep(1)

        # After window: should allow
        should_suppress, reason = short_policy.should_suppress("search", {"query": "test"}, force_retry=False)
        assert should_suppress is False
        assert reason == "not_duplicate"

    def test_cleanup_expired_entries(self, policy):
        """Test cleanup removes expired entries."""
        # Use short window policy
        short_policy = DuplicateQueryPolicy(window_minutes=0.01)

        # Add multiple entries
        for i in range(5):
            short_policy.record_execution(
                "search",
                {"query": f"test{i}"},
                True,
                0.9,
            )

        assert len(short_policy._cache._cache) == 5

        # Wait for expiration
        time.sleep(1)

        # Cleanup
        removed = short_policy.cleanup()

        assert removed == 5
        assert len(short_policy._cache._cache) == 0

    def test_suppression_metrics_incremented(self, policy):
        """Test suppression metrics are tracked."""
        initial_count = agent_duplicate_query_blocked.get(
            {"tool_name": "search", "suppression_reason": "duplicate_within_window"}
        )

        # Record and suppress
        policy.record_execution("search", {"query": "test"}, True, 0.9)
        policy.should_suppress("search", {"query": "test"}, False)

        final_count = agent_duplicate_query_blocked.get(
            {"tool_name": "search", "suppression_reason": "duplicate_within_window"}
        )

        assert final_count > initial_count

    def test_override_metrics_incremented(self, policy):
        """Test override metrics track reason labels."""
        initial_count = agent_duplicate_query_override.get({"override_reason": "low_quality_result"})

        # Record low quality and check override
        policy.record_execution("search", {"query": "test"}, True, 0.2)
        policy.should_suppress("search", {"query": "test"}, False)

        final_count = agent_duplicate_query_override.get({"override_reason": "low_quality_result"})

        assert final_count > initial_count

    def test_different_tools_different_signatures(self, policy):
        """Test same args for different tools generate different signatures."""
        args = {"query": "test"}

        sig1 = policy.generate_signature("search", args)
        sig2 = policy.generate_signature("database", args)

        assert sig1 != sig2

    def test_record_execution_with_result_data(self, policy):
        """Test recording execution with optional result data."""
        policy.record_execution(
            tool_name="search",
            args={"query": "test"},
            success=True,
            quality_score=0.9,
            result_data={"results": ["item1", "item2"]},
        )

        # Should be recorded and retrievable
        signature = policy.generate_signature("search", {"query": "test"})
        cached = policy._cache.get(signature)

        assert cached is not None
        assert cached.result_data == {"results": ["item1", "item2"]}

    def test_get_stats(self, policy):
        """Test get_stats returns policy information."""
        # Add some entries
        policy.record_execution("search", {"query": "test1"}, True, 0.9)
        policy.record_execution("search", {"query": "test2"}, True, 0.8)

        stats = policy.get_stats()

        assert stats["window_minutes"] == 5
        assert stats["quality_threshold"] == 0.5
        assert stats["cached_queries"] == 2

    def test_quality_threshold_boundary(self, policy):
        """Test quality threshold boundary conditions."""
        # Exactly at threshold (0.5)
        policy.record_execution("search", {"query": "test"}, True, 0.5)

        should_suppress, reason = policy.should_suppress("search", {"query": "test"}, False)

        # At threshold, should NOT override (>= threshold suppresses)
        assert should_suppress is True

        # Just below threshold
        policy.record_execution("search", {"query": "test2"}, True, 0.49)

        should_suppress, reason = policy.should_suppress("search", {"query": "test2"}, False)

        # Below threshold, should override
        assert should_suppress is False
        assert reason == "low_quality_result"
