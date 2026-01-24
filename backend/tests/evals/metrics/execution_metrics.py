"""Execution and performance evaluation metrics.

Metrics for evaluating tool calls, response time, token usage,
and other execution-related aspects.
"""

from typing import Dict, Any, List, Optional

from tests.evals.metrics.base import BaseMetric, MetricScore


class ToolCallMetric(BaseMetric):
    """Validates that expected tool calls were made."""

    name = "tool_call"
    description = "Verifies expected tool calls were made correctly"

    def evaluate(
        self,
        actual_output: str,
        expected: Dict[str, Any],
        context: Dict[str, Any],
    ) -> MetricScore:
        expected_calls = expected.get("expected_tool_calls", [])

        if not expected_calls:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No tool calls expected"
            )

        actual_calls = context.get("tool_calls", [])

        if not actual_calls:
            return MetricScore(
                metric_name=self.name,
                score=0.0,
                passed=False,
                details={
                    "expected_calls": len(expected_calls),
                    "actual_calls": 0,
                },
                message=f"Expected {len(expected_calls)} tool calls but none were made"
            )

        # Match expected calls to actual calls
        matched = []
        unmatched_expected = []
        extra_actual = list(range(len(actual_calls)))

        for exp in expected_calls:
            found = False
            for i, act in enumerate(actual_calls):
                if i not in extra_actual:
                    continue
                if self._calls_match(exp, act):
                    matched.append({
                        "expected": exp,
                        "actual": act,
                    })
                    extra_actual.remove(i)
                    found = True
                    break

            if not found:
                unmatched_expected.append(exp)

        score = len(matched) / len(expected_calls) if expected_calls else 1.0

        # Check order if required
        order_correct = True
        if expected.get("tool_call_order_matters", False) and matched:
            matched_indices = [
                next(i for i, a in enumerate(actual_calls)
                     if self._calls_match(m["expected"], a))
                for m in matched
            ]
            order_correct = matched_indices == sorted(matched_indices)
            if not order_correct:
                score *= 0.8  # Penalty for wrong order

        threshold = self.get_threshold(expected, 1.0)
        passed = score >= threshold and not unmatched_expected

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "matched": len(matched),
                "expected_total": len(expected_calls),
                "actual_total": len(actual_calls),
                "unmatched_expected": unmatched_expected,
                "extra_actual": len(extra_actual),
                "order_correct": order_correct,
            },
            message=f"Matched {len(matched)}/{len(expected_calls)} expected tool calls"
        )

    def _calls_match(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
        """Check if an actual call matches expected criteria."""
        # Match function name
        exp_name = expected.get("function_name") or expected.get("name")
        act_name = actual.get("function_name") or actual.get("name") or \
                   actual.get("function", {}).get("name")

        if exp_name and act_name != exp_name:
            return False

        # Match arguments if specified
        exp_args = expected.get("arguments") or expected.get("args")
        if exp_args:
            act_args = actual.get("arguments") or actual.get("args") or \
                       actual.get("function", {}).get("arguments", {})

            # Parse args if string
            if isinstance(act_args, str):
                import json
                try:
                    act_args = json.loads(act_args)
                except json.JSONDecodeError:
                    return False

            # Check each expected argument
            for key, value in exp_args.items():
                if key not in act_args:
                    return False
                if value is not None and act_args[key] != value:
                    # Loose comparison for strings
                    if str(act_args[key]).lower() != str(value).lower():
                        return False

        return True


class ResponseTimeMetric(BaseMetric):
    """Checks that response was generated within time limit."""

    name = "response_time"
    description = "Validates response time is within acceptable limits"

    def evaluate(
        self,
        actual_output: str,
        expected: Dict[str, Any],
        context: Dict[str, Any],
    ) -> MetricScore:
        max_time = expected.get("max_response_time_seconds", 30.0)
        actual_time = context.get("duration_seconds", 0.0)

        if actual_time <= 0:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                details={"note": "No timing data available"},
                message="No timing data available"
            )

        # Calculate score (1.0 at half the limit, decreasing after)
        if actual_time <= max_time / 2:
            score = 1.0
        elif actual_time <= max_time:
            # Linear decrease from 1.0 to 0.5 between half and full limit
            score = 1.0 - 0.5 * (actual_time - max_time / 2) / (max_time / 2)
        else:
            # Below 0.5 for over limit
            score = 0.5 * max_time / actual_time

        passed = actual_time <= max_time

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "actual_seconds": actual_time,
                "max_seconds": max_time,
                "percent_of_limit": (actual_time / max_time * 100) if max_time > 0 else 0,
            },
            message=f"Response time: {actual_time:.2f}s (limit: {max_time}s)"
        )


class TokenCountMetric(BaseMetric):
    """Validates token usage is within limits."""

    name = "token_count"
    description = "Checks token usage is within specified limits"

    def evaluate(
        self,
        actual_output: str,
        expected: Dict[str, Any],
        context: Dict[str, Any],
    ) -> MetricScore:
        max_tokens = expected.get("max_tokens", 10000)

        input_tokens = context.get("input_tokens", 0)
        output_tokens = context.get("output_tokens", 0)
        total_tokens = context.get("total_tokens", input_tokens + output_tokens)

        if total_tokens <= 0:
            # Estimate tokens if not provided (rough: ~4 chars per token)
            total_tokens = len(actual_output) // 4

        # Calculate score based on token usage efficiency
        if total_tokens <= max_tokens * 0.5:
            score = 1.0
        elif total_tokens <= max_tokens:
            # Linear decrease from 1.0 to 0.5 between half and full limit
            score = 1.0 - 0.5 * (total_tokens - max_tokens * 0.5) / (max_tokens * 0.5)
        else:
            # Below 0.5 for over limit
            score = 0.5 * max_tokens / total_tokens

        passed = total_tokens <= max_tokens

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "max_tokens": max_tokens,
                "percent_of_limit": (total_tokens / max_tokens * 100) if max_tokens > 0 else 0,
            },
            message=f"Token usage: {total_tokens:,} (limit: {max_tokens:,})"
        )


class ErrorFreeMetric(BaseMetric):
    """Checks that no errors occurred during execution."""

    name = "error_free"
    description = "Validates that execution completed without errors"

    def evaluate(
        self,
        actual_output: str,
        expected: Dict[str, Any],
        context: Dict[str, Any],
    ) -> MetricScore:
        error = context.get("error")
        error_type = context.get("error_type")

        if error:
            return MetricScore(
                metric_name=self.name,
                score=0.0,
                passed=False,
                details={
                    "error": error,
                    "error_type": error_type,
                },
                message=f"Execution error: {error}"
            )

        # Check for error indicators in output
        error_patterns = [
            "error:", "exception:", "failed:", "traceback",
            "could not", "unable to", "invalid"
        ]

        output_lower = actual_output.lower()
        detected_errors = [p for p in error_patterns if p in output_lower]

        # Allow some error-like words if not actual errors
        if detected_errors and expected.get("allow_error_text", True):
            return MetricScore(
                metric_name=self.name,
                score=0.9,
                passed=True,
                details={
                    "warning": "Error-like text detected but no actual error",
                    "patterns_found": detected_errors,
                },
                message="Completed without errors (some error-like text present)"
            )

        return MetricScore(
            metric_name=self.name,
            score=1.0,
            passed=True,
            message="Execution completed without errors"
        )


class ToolSuccessMetric(BaseMetric):
    """Checks that all tool calls succeeded."""

    name = "tool_success"
    description = "Validates that all tool calls completed successfully"

    def evaluate(
        self,
        actual_output: str,
        expected: Dict[str, Any],
        context: Dict[str, Any],
    ) -> MetricScore:
        tool_calls = context.get("tool_calls", [])

        if not tool_calls:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No tool calls to evaluate"
            )

        successful = 0
        failed = []

        for call in tool_calls:
            result = call.get("result") or call.get("function_result")
            if result:
                if isinstance(result, dict):
                    success = result.get("success", True)
                else:
                    success = True
            else:
                success = True

            if success:
                successful += 1
            else:
                failed.append({
                    "function": call.get("function_name") or call.get("name"),
                    "result": result,
                })

        score = successful / len(tool_calls)
        passed = len(failed) == 0

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "successful": successful,
                "failed": len(failed),
                "total": len(tool_calls),
                "failed_calls": failed,
            },
            message=f"Tool success rate: {successful}/{len(tool_calls)}"
        )
