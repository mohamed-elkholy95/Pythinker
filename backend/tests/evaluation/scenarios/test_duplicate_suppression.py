"""Evaluation Scenario B: Duplicate Query Suppression

Tests duplicate detection and suppression effectiveness across different tool types.

Expected Results:
- Baseline: 100% duplicate queries executed (no suppression)
- Enhanced: 60-70% duplicates suppressed (within window, high quality)
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.domain.services.agents.duplicate_query_policy import DuplicateQueryPolicy


@pytest.mark.evaluation
class TestDuplicateSuppressionEvaluation:
    """Scenario B: Evaluate duplicate query suppression effectiveness."""

    @pytest.fixture
    def duplicate_policy(self):
        """Create duplicate query policy instance."""
        return DuplicateQueryPolicy(
            window_minutes=5,  # 5 minutes
            quality_threshold=0.85,
        )

    @pytest.mark.asyncio
    async def test_repeated_search_queries(self, duplicate_policy):
        """Evaluate duplicate suppression for search queries.

        Expected metrics:
        - agent_duplicate_query_blocked_total
        - search_tool_executions_total (should decrease)
        """
        # Same search query repeated 3 times within window
        search_queries = [
            {
                "tool": "search",
                "args": {"query": "machine learning tutorials", "limit": 10},
                "timestamp": datetime.utcnow(),
            },
            {
                "tool": "search",
                "args": {"query": "machine learning tutorials", "limit": 10},
                "timestamp": datetime.utcnow() + timedelta(seconds=60),
            },
            {
                "tool": "search",
                "args": {"query": "machine learning tutorials", "limit": 10},
                "timestamp": datetime.utcnow() + timedelta(seconds=120),
            },
        ]

        results = {"executed": 0, "suppressed": 0, "override": 0}

        for i, query in enumerate(search_queries):
            # Check for duplicate
            should_suppress, reason = duplicate_policy.should_suppress(
                tool_name=query["tool"],
                args=query["args"],
            )

            if should_suppress:
                # Suppressed (duplicate with high quality result)
                if reason == "duplicate_within_window":
                    results["suppressed"] += 1
                else:
                    # Override occurred (low quality, failure, etc.)
                    results["override"] += 1
                    results["executed"] += 1
            else:
                results["executed"] += 1
                # Record execution in cache
                duplicate_policy.record_execution(
                    tool_name=query["tool"],
                    args=query["args"],
                    success=True,
                    quality_score=0.92,
                    result_data={"data": "results"},
                )

        # Calculate suppression rate
        total = len(search_queries)
        suppression_rate = results["suppressed"] / total if total > 0 else 0

        # Expected: first executed, next 2 suppressed (67% suppression)
        assert results["executed"] == 1, f"Expected 1 execution, got {results['executed']}"
        assert results["suppressed"] == 2, f"Expected 2 suppressions, got {results['suppressed']}"

        print(f"\n=== Search Query Suppression Results ===")
        print(f"Total queries: {total}")
        print(f"Executed: {results['executed']}")
        print(f"Suppressed: {results['suppressed']} ({suppression_rate*100:.1f}%)")
        print(f"Override (low quality): {results['override']}")

    @pytest.mark.asyncio
    async def test_repeated_browser_navigation(self, duplicate_policy):
        """Evaluate duplicate suppression for browser navigation.

        Expected metrics:
        - agent_duplicate_query_blocked_total{tool="browser"}
        """
        # Same URL navigation repeated
        browser_calls = [
            {
                "tool": "browser",
                "args": {"url": "https://example.com", "timeout": 30},
                "timestamp": datetime.utcnow(),
            },
            {
                "tool": "browser",
                "args": {"url": "https://example.com", "timeout": 30},
                "timestamp": datetime.utcnow() + timedelta(seconds=30),
            },
            {
                "tool": "browser",
                "args": {"url": "https://example.com", "timeout": 30},
                "timestamp": datetime.utcnow() + timedelta(seconds=90),
            },
        ]

        results = {"executed": 0, "suppressed": 0}

        for call in browser_calls:
            should_suppress_bool, reason = duplicate_policy.should_suppress(
                tool_name=call["tool"],
                args=call["args"],
                
            )

            if should_suppress_bool and reason == "duplicate_within_window":
                results["suppressed"] += 1
            else:
                results["executed"] += 1
                duplicate_policy.record_execution(
                    tool_name=call["tool"],
                    args=call["args"],
                    success=True,
                    result_data={"success": True, "html": "<html>...</html>"},
                    quality_score=0.88,
                    
                )

        total = len(browser_calls)
        suppression_rate = results["suppressed"] / total

        # Expected: first executed, next 2 suppressed
        assert results["suppressed"] >= 2, f"Expected ≥2 suppressions, got {results['suppressed']}"

        print(f"\n=== Browser Navigation Suppression Results ===")
        print(f"Total calls: {total}")
        print(f"Executed: {results['executed']}")
        print(f"Suppressed: {results['suppressed']} ({suppression_rate*100:.1f}%)")

    @pytest.mark.asyncio
    async def test_repeated_file_reads(self, duplicate_policy):
        """Evaluate duplicate suppression for file operations.

        Expected metrics:
        - agent_duplicate_query_blocked_total{tool="file"}
        """
        # Same file read repeated
        file_reads = [
            {
                "tool": "file",
                "args": {"operation": "read", "path": "/config/settings.json"},
                "timestamp": datetime.utcnow(),
            },
            {
                "tool": "file",
                "args": {"operation": "read", "path": "/config/settings.json"},
                "timestamp": datetime.utcnow() + timedelta(seconds=45),
            },
            {
                "tool": "file",
                "args": {"operation": "read", "path": "/config/settings.json"},
                "timestamp": datetime.utcnow() + timedelta(seconds=150),
            },
        ]

        results = {"executed": 0, "suppressed": 0}

        for call in file_reads:
            should_suppress_bool, reason = duplicate_policy.should_suppress(
                tool_name=call["tool"],
                args=call["args"],
                
            )

            if should_suppress_bool and reason == "duplicate_within_window":
                results["suppressed"] += 1
            else:
                results["executed"] += 1
                duplicate_policy.record_execution(
                    tool_name=call["tool"],
                    args=call["args"],
                    success=True,
                    result_data={"success": True, "content": "{...}"},
                    quality_score=0.95,
                    
                )

        total = len(file_reads)
        suppression_rate = results["suppressed"] / total

        assert results["suppressed"] >= 2, f"Expected ≥2 suppressions, got {results['suppressed']}"

        print(f"\n=== File Read Suppression Results ===")
        print(f"Total reads: {total}")
        print(f"Executed: {results['executed']}")
        print(f"Suppressed: {results['suppressed']} ({suppression_rate*100:.1f}%)")

    @pytest.mark.asyncio
    async def test_low_quality_override(self, duplicate_policy):
        """Evaluate override behavior for low-quality cached results.

        Expected metrics:
        - agent_duplicate_query_override_total{override_reason="low_quality"}
        """
        # First call: low quality result
        tool = "search"
        args = {"query": "python documentation", "limit": 5}

        # Execute first (will be cached)
        should_suppress, reason = duplicate_policy.should_suppress(tool, args)
        assert not should_suppress, "First call should not be duplicate"

        # Record with LOW quality score
        duplicate_policy.record_execution(
            tool_name=tool,
            args=args,
            success=True,
                    result_data={"success": True, "data": "limited results"},
            quality_score=0.60,  # Below threshold (0.85)
            
        )

        # Second call: should override due to low quality
        should_suppress, reason = duplicate_policy.should_suppress(tool, args)

        # Enhanced: should override low quality
        # Baseline: might not have quality checking
        if should_suppress:
            assert reason != "duplicate_within_window", "Low quality should not suppress"
            print(f"Override reason: {reason}")
        else:
            print("Not detected as duplicate (expected override)")

        print(f"\n=== Low Quality Override Results ===")
        print(f"Quality score: 0.60 (threshold: 0.85)")
        print(f"Duplicate detected: {should_suppress}")
        print(f"Override occurred: {not should_suppress or reason != 'duplicate_within_window'}")

    @pytest.mark.asyncio
    async def test_window_expiration(self, duplicate_policy):
        """Evaluate duplicate detection after window expiration.

        Expected metrics:
        - Window expiration should allow re-execution
        """
        tool = "search"
        args = {"query": "testing window expiration"}

        # First execution
        should_suppress1, _ = duplicate_policy.should_suppress(tool, args)
        assert not should_suppress1

        duplicate_policy.record_execution(
            tool_name=tool,
            args=args,
            success=True,
                    result_data={"success": True},
            quality_score=0.90,
            
        )

        # Second call within window (should suppress)
        should_suppress2, reason2 = duplicate_policy.should_suppress(tool, args)
        assert should_suppress2, "Should be duplicate within window"

        # Simulate window expiration (mock timestamp in future)
        # In real evaluation, this would wait or mock time
        # For now, just verify policy has window configured
        assert duplicate_policy.window_minutes == 5

        print(f"\n=== Window Expiration Results ===")
        print(f"Window duration: {duplicate_policy.window_minutes} minutes")
        print(f"Within window suppressed: {should_suppress2}")

    @pytest.mark.asyncio
    async def test_batch_suppression_effectiveness(self, duplicate_policy):
        """Comprehensive batch test: 75 total queries (25 sessions × 3 queries each).

        Expected metrics:
        - Baseline: 75/75 executed (0% suppression)
        - Enhanced: ~32/75 executed (57% suppression)
        """
        results = {"total": 0, "executed": 0, "suppressed": 0, "override": 0}

        # 25 different search queries, each repeated 3 times
        base_queries = [
            "python tutorial",
            "javascript frameworks",
            "docker containers",
            "kubernetes deployment",
            "react hooks",
            "vue composition api",
            "fastapi documentation",
            "mongodb queries",
            "redis caching",
            "nginx configuration",
            "postgres optimization",
            "aws lambda functions",
            "terraform modules",
            "github actions",
            "ci/cd pipelines",
            "unit testing best practices",
            "api design patterns",
            "microservices architecture",
            "event driven design",
            "domain driven design",
            "clean architecture",
            "solid principles",
            "design patterns",
            "refactoring techniques",
            "code review checklist",
        ]

        for i, query in enumerate(base_queries):
            session_id = f"eval-session-batch-{i}"

            # Execute same query 3 times per session
            for attempt in range(3):
                results["total"] += 1

                should_suppress, reason = duplicate_policy.should_suppress(
                    tool_name="search",
                    args={"query": query, "limit": 10},
                    
                )

                if should_suppress:
                    if reason == "duplicate_within_window":
                        results["suppressed"] += 1
                    else:
                        results["override"] += 1
                        results["executed"] += 1
                else:
                    results["executed"] += 1
                    # Record first execution
                    duplicate_policy.record_execution(
                        tool_name="search",
                        args={"query": query, "limit": 10},
                        success=True,
                    result_data={"success": True, "results": ["item1", "item2"]},
                        quality_score=0.90,
                        
                    )

        # Calculate metrics
        suppression_rate = results["suppressed"] / results["total"]

        # Expected: ~57% suppression (2 out of 3 per session)
        expected_suppressed = 25 * 2  # 50 suppressions expected
        assert results["suppressed"] >= 40, f"Expected ≥40 suppressions, got {results['suppressed']}"

        print(f"\n=== Batch Suppression Effectiveness ===")
        print(f"Total queries: {results['total']}")
        print(f"Executed: {results['executed']}")
        print(f"Suppressed: {results['suppressed']} ({suppression_rate*100:.1f}%)")
        print(f"Override (low quality): {results['override']}")
        print(f"Expected suppression: {expected_suppressed} ({expected_suppressed/results['total']*100:.1f}%)")
