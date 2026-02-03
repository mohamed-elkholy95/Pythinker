"""
Deterministic graders for agent evaluation.

Rule-based grading for deterministic checks that don't require LLM judgment.
Provides fast, consistent evaluation of structural and content requirements.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GradeResult:
    """Result of a grading operation."""

    passed: bool
    score: float  # 0.0 to 1.0
    feedback: str
    details: dict[str, Any] = field(default_factory=dict)


class DeterministicGrader:
    """Rule-based grading for deterministic checks."""

    def grade_plan_structure(
        self,
        plan: dict[str, Any],
        constraints: dict[str, Any],
    ) -> GradeResult:
        """Check if plan meets structural constraints.

        Args:
            plan: The plan to evaluate (as dict)
            constraints: Constraints to check:
                - min_steps: Minimum number of steps
                - max_steps: Maximum number of steps
                - required_tools: List of tools that must be present
                - complexity: Expected complexity level

        Returns:
            GradeResult with pass/fail, score, and feedback
        """
        steps = plan.get("steps", [])
        issues = []
        score_deductions = 0.0

        # Check step count
        min_steps = constraints.get("min_steps", 1)
        max_steps = constraints.get("max_steps", 20)

        if len(steps) < min_steps:
            issues.append(f"Too few steps: {len(steps)} < {min_steps}")
            score_deductions += 0.3
        elif len(steps) > max_steps:
            issues.append(f"Too many steps: {len(steps)} > {max_steps}")
            score_deductions += 0.2

        # Check required tools
        required_tools = constraints.get("required_tools", [])
        if required_tools:
            plan_tools = set()
            for step in steps:
                if isinstance(step, dict):
                    tool = step.get("tool") or step.get("tools")
                    if tool:
                        if isinstance(tool, list):
                            plan_tools.update(tool)
                        else:
                            plan_tools.add(tool)

            missing_tools = set(required_tools) - plan_tools
            if missing_tools:
                issues.append(f"Missing required tools: {missing_tools}")
                score_deductions += 0.3 * len(missing_tools) / len(required_tools)

        # Check complexity matches expectation
        expected_complexity = constraints.get("complexity")
        if expected_complexity:
            plan_complexity = plan.get("complexity", "medium")
            if plan_complexity != expected_complexity:
                issues.append(f"Complexity mismatch: expected {expected_complexity}, got {plan_complexity}")
                score_deductions += 0.1

        # Calculate final score
        score = max(0.0, 1.0 - score_deductions)
        passed = len(issues) == 0

        return GradeResult(
            passed=passed,
            score=score,
            feedback="; ".join(issues) if issues else "Plan structure valid",
            details={
                "step_count": len(steps),
                "constraints": constraints,
                "issues": issues,
            },
        )

    def grade_execution_result(
        self,
        result: dict[str, Any],
        expected: dict[str, Any],
    ) -> GradeResult:
        """Check if execution result meets expectations.

        Args:
            result: The execution result to evaluate
            expected: Expected outcomes:
                - should_succeed: Whether execution should succeed
                - contains: List of strings that must be in response
                - not_contains: List of strings that must NOT be in response
                - min_length: Minimum response length

        Returns:
            GradeResult with pass/fail, score, and feedback
        """
        issues = []
        score_deductions = 0.0

        # Check success status
        should_succeed = expected.get("should_succeed", True)
        did_succeed = result.get("success", False)

        if should_succeed and not did_succeed:
            issues.append("Execution failed unexpectedly")
            return GradeResult(
                passed=False,
                score=0.0,
                feedback="Execution failed unexpectedly",
                details={"error": result.get("error")},
            )

        if not should_succeed and did_succeed:
            issues.append("Execution succeeded unexpectedly")
            score_deductions += 0.5

        # Check response content
        response = result.get("response", "") or ""
        response_lower = response.lower()

        # Check required content
        required_content = expected.get("contains", [])
        for content in required_content:
            if content.lower() not in response_lower:
                issues.append(f"Missing required content: '{content}'")
                score_deductions += 0.2

        # Check forbidden content
        forbidden_content = expected.get("not_contains", [])
        for content in forbidden_content:
            if content.lower() in response_lower:
                issues.append(f"Contains forbidden content: '{content}'")
                score_deductions += 0.3

        # Check minimum length
        min_length = expected.get("min_length", 0)
        if len(response) < min_length:
            issues.append(f"Response too short: {len(response)} < {min_length}")
            score_deductions += 0.1

        # Calculate final score
        score = max(0.0, 1.0 - score_deductions)
        passed = len(issues) == 0

        return GradeResult(
            passed=passed,
            score=score,
            feedback="; ".join(issues) if issues else "Result valid",
            details={
                "response_length": len(response),
                "expected": expected,
                "issues": issues,
            },
        )

    def grade_tool_usage(
        self,
        tool_calls: list[dict[str, Any]],
        expected: dict[str, Any],
    ) -> GradeResult:
        """Check if tool usage meets expectations.

        Args:
            tool_calls: List of tool calls made
            expected: Expected tool usage:
                - required_tools: Tools that must be called
                - forbidden_tools: Tools that must NOT be called
                - max_calls: Maximum total tool calls
                - min_calls: Minimum total tool calls

        Returns:
            GradeResult with pass/fail, score, and feedback
        """
        issues = []
        score_deductions = 0.0

        called_tools = [tc.get("name") or tc.get("function", {}).get("name") for tc in tool_calls]
        called_tools_set = set(called_tools)

        # Check required tools
        required_tools = expected.get("required_tools", [])
        for tool in required_tools:
            if tool not in called_tools_set:
                issues.append(f"Required tool not called: {tool}")
                score_deductions += 0.3

        # Check forbidden tools
        forbidden_tools = expected.get("forbidden_tools", [])
        for tool in forbidden_tools:
            if tool in called_tools_set:
                issues.append(f"Forbidden tool called: {tool}")
                score_deductions += 0.4

        # Check call count limits
        max_calls = expected.get("max_calls")
        if max_calls and len(tool_calls) > max_calls:
            issues.append(f"Too many tool calls: {len(tool_calls)} > {max_calls}")
            score_deductions += 0.2

        min_calls = expected.get("min_calls")
        if min_calls and len(tool_calls) < min_calls:
            issues.append(f"Too few tool calls: {len(tool_calls)} < {min_calls}")
            score_deductions += 0.1

        # Calculate final score
        score = max(0.0, 1.0 - score_deductions)
        passed = len(issues) == 0

        return GradeResult(
            passed=passed,
            score=score,
            feedback="; ".join(issues) if issues else "Tool usage valid",
            details={
                "called_tools": called_tools,
                "call_count": len(tool_calls),
                "issues": issues,
            },
        )

    def grade_step_completion(
        self,
        steps: list[dict[str, Any]],
        expected: dict[str, Any],
    ) -> GradeResult:
        """Check if steps completed as expected.

        Args:
            steps: List of step results
            expected: Expected step completion:
                - min_completed: Minimum steps completed
                - max_failed: Maximum steps failed
                - required_completed: Specific step IDs that must complete

        Returns:
            GradeResult with pass/fail, score, and feedback
        """
        issues = []
        score_deductions = 0.0

        completed = [s for s in steps if s.get("status") == "completed"]
        failed = [s for s in steps if s.get("status") == "failed"]

        # Check minimum completed
        min_completed = expected.get("min_completed", 0)
        if len(completed) < min_completed:
            issues.append(f"Too few steps completed: {len(completed)} < {min_completed}")
            score_deductions += 0.4

        # Check maximum failed
        max_failed = expected.get("max_failed", len(steps))
        if len(failed) > max_failed:
            issues.append(f"Too many steps failed: {len(failed)} > {max_failed}")
            score_deductions += 0.3

        # Check specific required completions
        required_completed = expected.get("required_completed", [])
        completed_ids = {s.get("id") for s in completed}
        for step_id in required_completed:
            if step_id not in completed_ids:
                issues.append(f"Required step not completed: {step_id}")
                score_deductions += 0.2

        # Calculate final score
        score = max(0.0, 1.0 - score_deductions)
        passed = len(issues) == 0

        return GradeResult(
            passed=passed,
            score=score,
            feedback="; ".join(issues) if issues else "Step completion valid",
            details={
                "completed_count": len(completed),
                "failed_count": len(failed),
                "issues": issues,
            },
        )


class CompositeGrader:
    """Combines multiple graders with configurable weights."""

    def __init__(self, graders: list[tuple[str, Any, float]]):
        """Initialize with list of (name, grader, weight) tuples."""
        self.graders = graders

    async def grade(
        self,
        data: dict[str, Any],
        expected: dict[str, Any],
    ) -> GradeResult:
        """Run all graders and combine results.

        Args:
            data: Data to grade (plan, result, tool_calls, etc.)
            expected: Expected outcomes for all graders

        Returns:
            Combined GradeResult
        """
        results = []
        total_weight = sum(w for _, _, w in self.graders)
        weighted_score = 0.0

        for name, grader, weight in self.graders:
            if name == "plan_structure" and "plan" in data:
                result = grader.grade_plan_structure(
                    data["plan"],
                    expected.get("plan_constraints", {}),
                )
            elif name == "execution_result" and "result" in data:
                result = grader.grade_execution_result(
                    data["result"],
                    expected.get("result_expected", {}),
                )
            elif name == "tool_usage" and "tool_calls" in data:
                result = grader.grade_tool_usage(
                    data["tool_calls"],
                    expected.get("tool_expected", {}),
                )
            elif name == "step_completion" and "steps" in data:
                result = grader.grade_step_completion(
                    data["steps"],
                    expected.get("step_expected", {}),
                )
            else:
                continue

            results.append((name, result))
            weighted_score += result.score * weight

        # Normalize score
        final_score = weighted_score / total_weight if total_weight > 0 else 0.0
        all_passed = all(r.passed for _, r in results)

        # Combine feedback
        feedback_parts = [f"{name}: {r.feedback}" for name, r in results if not r.passed]
        feedback = "; ".join(feedback_parts) if feedback_parts else "All checks passed"

        return GradeResult(
            passed=all_passed,
            score=final_score,
            feedback=feedback,
            details={
                "individual_results": {name: r.__dict__ for name, r in results},
                "weights": {name: w for name, _, w in self.graders},
            },
        )
