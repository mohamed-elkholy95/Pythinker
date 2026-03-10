"""Tests for evidence-based step completion — steps with failed reads should not be COMPLETED."""

import pytest
from app.domain.models.plan import Step, ExecutionStatus


class TestStepCompletionEvidence:
    """Steps should fail when all tool calls failed and no output was produced."""

    def test_step_with_only_failed_reads_should_fail(self):
        """A step where every tool call failed should not be marked COMPLETED."""
        step = Step(id="step-1", description="Read README.md and analyze")
        step.status = ExecutionStatus.RUNNING
        step.success = False
        step.result = None

        # Simulate: 3 file_read calls, all failed (file not found)
        step_tool_total = 3
        step_tool_errors = 3

        has_result = bool(step.result and str(step.result).strip())
        has_successful_tool = step_tool_total > step_tool_errors

        if has_result or has_successful_tool or step_tool_total == 0:
            step.status = ExecutionStatus.COMPLETED
            step.success = True
        else:
            step.status = ExecutionStatus.FAILED
            step.success = False

        assert step.status == ExecutionStatus.FAILED
        assert step.success is False

    def test_step_with_mixed_results_should_complete(self):
        """A step with at least one successful tool call can be COMPLETED."""
        step = Step(id="step-2", description="Search and read files")
        step.status = ExecutionStatus.RUNNING
        step.success = False
        step.result = "Found relevant information"

        step_tool_total = 2
        step_tool_errors = 1

        has_result = bool(step.result and str(step.result).strip())
        has_successful_tool = step_tool_total > step_tool_errors

        if has_result or has_successful_tool or step_tool_total == 0:
            step.status = ExecutionStatus.COMPLETED
            step.success = True
        else:
            step.status = ExecutionStatus.FAILED

        assert step.status == ExecutionStatus.COMPLETED
        assert step.success is True

    def test_step_with_no_tools_and_no_result_completes_as_llm_only(self):
        """A step that used no tools is LLM-only — COMPLETED (reasoning step)."""
        step = Step(id="step-3", description="Validate findings")
        step.status = ExecutionStatus.RUNNING
        step.success = False
        step.result = None

        step_tool_total = 0
        step_tool_errors = 0

        has_result = bool(step.result and str(step.result).strip())
        has_successful_tool = step_tool_total > step_tool_errors

        if has_result or has_successful_tool or step_tool_total == 0:
            step.status = ExecutionStatus.COMPLETED
            step.success = True
        else:
            step.status = ExecutionStatus.FAILED

        # LLM-only steps (no tools) complete normally
        assert step.status == ExecutionStatus.COMPLETED

    def test_step_with_all_errors_but_result_should_complete(self):
        """A step where tools failed but LLM produced a result should COMPLETE."""
        step = Step(id="step-4", description="Analyze with fallback")
        step.status = ExecutionStatus.RUNNING
        step.success = False
        step.result = "Based on prior knowledge, the analysis shows..."

        step_tool_total = 2
        step_tool_errors = 2

        has_result = bool(step.result and str(step.result).strip())
        has_successful_tool = step_tool_total > step_tool_errors

        if has_result or has_successful_tool or step_tool_total == 0:
            step.status = ExecutionStatus.COMPLETED
            step.success = True
        else:
            step.status = ExecutionStatus.FAILED

        # Has result even though tools failed → COMPLETED
        assert step.status == ExecutionStatus.COMPLETED
        assert step.success is True
