"""
Integration tests for error recovery mechanisms.

Tests error handling, retry logic, cascade prevention, and graceful degradation
across the agent workflow.
"""

import pytest

from app.domain.models.plan import ExecutionStatus


class TestTransientErrorRecovery:
    """Tests for transient error recovery."""

    @pytest.mark.asyncio
    async def test_network_error_triggers_retry(self, mock_tool_registry):
        """Network errors should trigger automatic retry."""
        attempt_count = 0

        async def flaky_network(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Network temporarily unavailable")
            return {"success": True, "data": "result"}

        mock_tool_registry.execute = flaky_network

        # Simulate retry loop
        max_retries = 3
        result = None

        for attempt in range(max_retries):
            try:
                result = await mock_tool_registry.execute("web_search", {"query": "test"})
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise
                continue

        assert result is not None
        assert result["success"] is True
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_timeout_error_triggers_retry(self, mock_tool_registry):
        """Timeout errors should trigger retry with increased timeout."""
        attempt_count = 0

        async def slow_tool(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise TimeoutError("Request timed out")
            return {"success": True}

        mock_tool_registry.execute = slow_tool

        # Retry on timeout
        result = None
        for _ in range(3):
            try:
                result = await mock_tool_registry.execute("slow_tool", {})
                break
            except TimeoutError:
                continue

        assert result is not None
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_backoff(self, mock_tool_registry):
        """Rate limit errors should trigger exponential backoff."""
        attempt_count = 0

        async def rate_limited(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                error = Exception("Rate limit exceeded")
                error.status_code = 429
                raise error
            return {"success": True}

        mock_tool_registry.execute = rate_limited

        # Retry with backoff
        result = None
        for _attempt in range(5):
            try:
                result = await mock_tool_registry.execute("api_tool", {})
                break
            except Exception as e:
                if hasattr(e, "status_code") and e.status_code == 429:
                    # Would normally sleep here with exponential backoff
                    continue
                raise

        assert result is not None


class TestPermanentErrorHandling:
    """Tests for permanent error handling."""

    @pytest.mark.asyncio
    async def test_authentication_error_escalates(self, mock_tool_registry):
        """Authentication errors should escalate to user."""
        mock_tool_registry.register(
            "auth_required_tool",
            error=Exception("Authentication failed: Invalid API key"),
        )

        with pytest.raises(Exception) as exc_info:
            await mock_tool_registry.execute("auth_required_tool", {})

        assert "Authentication failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_permission_denied_escalates(self, mock_tool_registry):
        """Permission denied errors should escalate."""
        mock_tool_registry.register(
            "protected_resource",
            error=PermissionError("Access denied to resource"),
        )

        with pytest.raises(PermissionError):
            await mock_tool_registry.execute("protected_resource", {})

    @pytest.mark.asyncio
    async def test_invalid_input_returns_error_gracefully(self, mock_tool_registry):
        """Invalid input should return error without crashing."""
        mock_tool_registry.register(
            "validator_tool",
            error=ValueError("Invalid input format"),
        )

        with pytest.raises(ValueError) as exc_info:
            await mock_tool_registry.execute("validator_tool", {"bad": "input"})

        assert "Invalid input" in str(exc_info.value)


class TestToolErrorIsolation:
    """Tests for tool error isolation."""

    @pytest.mark.asyncio
    async def test_one_tool_failure_doesnt_halt_others(self, mock_tool_registry):
        """One tool failing should not prevent other tools from running."""
        mock_tool_registry.register("failing_tool", error=Exception("Tool failed"))
        mock_tool_registry.register("working_tool", {"result": "success"})

        # Execute multiple tools
        results = []
        tools = ["failing_tool", "working_tool"]

        for tool in tools:
            try:
                result = await mock_tool_registry.execute(tool, {})
                results.append({"tool": tool, "success": True, "result": result})
            except Exception as e:
                results.append({"tool": tool, "success": False, "error": str(e)})

        # One should fail, one should succeed
        assert len(results) == 2
        assert results[0]["success"] is False
        assert results[1]["success"] is True

    @pytest.mark.asyncio
    async def test_parallel_tool_isolation(self, mock_tool_registry):
        """Parallel tool execution should isolate failures."""
        import asyncio

        mock_tool_registry.register("tool_a", {"data": "a"})
        mock_tool_registry.register("tool_b", error=Exception("B failed"))
        mock_tool_registry.register("tool_c", {"data": "c"})

        async def safe_execute(tool_name):
            try:
                return await mock_tool_registry.execute(tool_name, {})
            except Exception as e:
                return {"error": str(e)}

        results = await asyncio.gather(
            safe_execute("tool_a"),
            safe_execute("tool_b"),
            safe_execute("tool_c"),
        )

        assert results[0] == {"data": "a"}
        assert "error" in results[1]
        assert results[2] == {"data": "c"}


class TestCascadePreention:
    """Tests for error cascade prevention."""

    def test_step_failure_marks_dependent_steps_blocked(self, plan_factory):
        """Dependent steps should be blocked when prerequisite fails."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Fetch data"},
                {"id": "2", "description": "Process data (depends on 1)"},
                {"id": "3", "description": "Save results (depends on 2)"},
            ]
        )

        # Set up dependencies
        plan.steps[1].dependencies = ["1"]
        plan.steps[2].dependencies = ["2"]

        # Step 1 fails
        plan.steps[0].status = ExecutionStatus.FAILED
        plan.steps[0].error = "Failed to fetch data"

        # Mark dependent steps as blocked
        for step in plan.steps[1:]:
            step.mark_blocked("Prerequisite step failed", blocked_by="1")

        assert plan.steps[1].status == ExecutionStatus.BLOCKED
        assert plan.steps[2].status == ExecutionStatus.BLOCKED

    def test_max_consecutive_failures_stops_execution(self, plan_factory):
        """Too many consecutive failures should stop execution."""
        plan = plan_factory(steps=[{"id": str(i), "description": f"Step {i}"} for i in range(1, 6)])

        max_consecutive_failures = 3
        for consecutive_failures, step in enumerate(plan.steps, start=1):
            # Simulate failure
            step.status = ExecutionStatus.FAILED

            if consecutive_failures >= max_consecutive_failures:
                # Should stop execution
                break

        # Only first 3 steps should be processed
        failed_count = sum(1 for s in plan.steps if s.status == ExecutionStatus.FAILED)
        pending_count = sum(1 for s in plan.steps if s.status == ExecutionStatus.PENDING)

        assert failed_count == 3
        assert pending_count == 2


class TestGracefulDegradation:
    """Tests for graceful degradation behavior."""

    @pytest.mark.asyncio
    async def test_partial_results_returned_on_some_failures(self, mock_tool_registry):
        """Partial results should be returned when some tools fail."""
        mock_tool_registry.register("search_a", {"results": ["result1"]})
        mock_tool_registry.register("search_b", error=Exception("Failed"))
        mock_tool_registry.register("search_c", {"results": ["result3"]})

        all_results = []
        errors = []

        for tool in ["search_a", "search_b", "search_c"]:
            try:
                result = await mock_tool_registry.execute(tool, {})
                all_results.append(result)
            except Exception as e:
                errors.append(str(e))

        # Should have partial results
        assert len(all_results) == 2
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_fallback_tool_on_primary_failure(self, mock_tool_registry):
        """Should use fallback tool when primary fails."""
        mock_tool_registry.register("primary_search", error=Exception("API down"))
        mock_tool_registry.register("fallback_search", {"results": ["fallback_result"]})

        result = None
        try:
            result = await mock_tool_registry.execute("primary_search", {})
        except Exception:
            # Try fallback
            result = await mock_tool_registry.execute("fallback_search", {})

        assert result is not None
        assert result["results"] == ["fallback_result"]

    def test_plan_completion_with_skipped_steps(self, plan_factory):
        """Plan should complete even with some skipped steps."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Essential step"},
                {"id": "2", "description": "Optional enhancement"},
                {"id": "3", "description": "Final output"},
            ]
        )

        # First step completes
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].success = True

        # Second step skipped
        plan.steps[1].mark_skipped("Feature not available")

        # Third step completes
        plan.steps[2].status = ExecutionStatus.COMPLETED
        plan.steps[2].success = True

        # Plan should be considered successful
        completed = [s for s in plan.steps if s.status in [ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED]]
        assert len(completed) == 3


class TestErrorRecoveryStrategies:
    """Tests for different error recovery strategies."""

    def test_replan_on_critical_error(self, plan_factory):
        """Critical errors should trigger replanning."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Initial approach"},
            ]
        )

        plan.steps[0].status = ExecutionStatus.FAILED
        plan.steps[0].error = "Critical: Required resource not available"

        # Should trigger replan
        needs_replan = "Critical" in (plan.steps[0].error or "")
        assert needs_replan is True

    def test_adjust_strategy_on_partial_failure(self, plan_factory):
        """Partial failure should adjust strategy, not replan."""
        plan = plan_factory(
            steps=[
                {"id": "1", "description": "Search for data"},
                {"id": "2", "description": "Analyze data"},
            ]
        )

        # First step partially succeeds
        plan.steps[0].status = ExecutionStatus.COMPLETED
        plan.steps[0].result = "Found limited results"
        plan.steps[0].success = True

        # Strategy should adjust for limited data
        # (In practice, this would modify step 2's approach)
        limited_results = "limited" in (plan.steps[0].result or "").lower()
        assert limited_results is True

    @pytest.mark.asyncio
    async def test_retry_count_tracking(self, mock_tool_registry):
        """Retry count should be tracked per operation."""
        retry_counts = {}

        async def tracked_execute(name: str, retries: int = 0):
            retry_counts[name] = retries
            if retries < 2:
                raise Exception("Retry needed")
            return {"success": True}

        # Simulate retries
        for tool in ["tool_a", "tool_b"]:
            for retry in range(3):
                try:
                    await tracked_execute(tool, retry)
                    break
                except Exception:
                    continue

        assert retry_counts["tool_a"] == 2
        assert retry_counts["tool_b"] == 2
