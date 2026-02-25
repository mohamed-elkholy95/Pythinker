"""Text-based evaluation metrics.

Metrics for evaluating text outputs using string matching,
containment checks, and regular expressions.
"""

import re
from typing import Any

from .base import BaseMetric, MetricScore


class ExactMatchMetric(BaseMetric):
    """Checks if output exactly matches expected (case-insensitive by default)."""

    name = "exact_match"
    description = "Checks if output exactly matches expected output"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        expected_output = expected.get("expected_output")

        if not expected_output:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                message="No expected output specified, skipping exact match",
            )

        # Check for case sensitivity option
        case_sensitive = expected.get("case_sensitive", False)

        if case_sensitive:
            matches = actual_output.strip() == expected_output.strip()
        else:
            matches = actual_output.strip().lower() == expected_output.strip().lower()

        return MetricScore(
            metric_name=self.name,
            score=1.0 if matches else 0.0,
            passed=matches,
            details={
                "expected": expected_output[:200],
                "actual": actual_output[:200],
                "case_sensitive": case_sensitive,
            },
            message="Exact match" if matches else "Output does not match expected",
        )


class ContainsMetric(BaseMetric):
    """Checks if output contains required strings."""

    name = "contains"
    description = "Checks if output contains all required strings"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        required_strings = expected.get("expected_output_contains", [])

        if not required_strings:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No required strings specified")

        case_sensitive = expected.get("case_sensitive", False)
        search_text = actual_output if case_sensitive else actual_output.lower()

        found = []
        missing = []

        for s in required_strings:
            search_s = s if case_sensitive else s.lower()
            if search_s in search_text:
                found.append(s)
            else:
                missing.append(s)

        score = len(found) / len(required_strings) if required_strings else 1.0
        threshold = self.get_threshold(expected, default=1.0)
        passed = score >= threshold and not missing

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "found": found,
                "missing": missing,
                "total_required": len(required_strings),
                "threshold": threshold,
            },
            message=f"Found {len(found)}/{len(required_strings)} required strings",
        )


class NotContainsMetric(BaseMetric):
    """Checks that output does NOT contain certain strings."""

    name = "not_contains"
    description = "Checks that output does not contain forbidden strings"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        forbidden_strings = expected.get("expected_output_not_contains", [])

        if not forbidden_strings:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No forbidden strings specified")

        case_sensitive = expected.get("case_sensitive", False)
        search_text = actual_output if case_sensitive else actual_output.lower()

        found_forbidden = []
        for s in forbidden_strings:
            search_s = s if case_sensitive else s.lower()
            if search_s in search_text:
                found_forbidden.append(s)

        score = 1.0 - (len(found_forbidden) / len(forbidden_strings))
        passed = len(found_forbidden) == 0

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "found_forbidden": found_forbidden,
                "total_forbidden": len(forbidden_strings),
            },
            message="No forbidden strings found" if passed else f"Found {len(found_forbidden)} forbidden strings",
        )


class RegexMatchMetric(BaseMetric):
    """Checks if output matches a regular expression pattern."""

    name = "regex_match"
    description = "Checks if output matches specified regex patterns"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        patterns = expected.get("expected_regex_patterns", [])

        if not patterns:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No regex patterns specified")

        flags = 0
        if not expected.get("case_sensitive", False):
            flags |= re.IGNORECASE

        matched = []
        not_matched = []
        errors = []

        for pattern in patterns:
            try:
                if re.search(pattern, actual_output, flags):
                    matched.append(pattern)
                else:
                    not_matched.append(pattern)
            except re.error as e:
                errors.append({"pattern": pattern, "error": str(e)})

        total_valid = len(patterns) - len(errors)
        score = len(matched) / total_valid if total_valid > 0 else 0.0

        threshold = self.get_threshold(expected, default=1.0)
        passed = score >= threshold and not not_matched

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "matched": matched,
                "not_matched": not_matched,
                "errors": errors,
                "total_patterns": len(patterns),
                "threshold": threshold,
            },
            message=f"Matched {len(matched)}/{total_valid} patterns",
        )


class LengthMetric(BaseMetric):
    """Checks if output length is within expected range."""

    name = "length"
    description = "Checks if output length is within specified range"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        min_length = expected.get("min_length", 0)
        max_length = expected.get("max_length", float("inf"))

        actual_length = len(actual_output)
        within_range = min_length <= actual_length <= max_length

        # Calculate score based on how close to ideal range
        if within_range:
            score = 1.0
        elif actual_length < min_length:
            score = actual_length / min_length if min_length > 0 else 0.0
        else:  # actual_length > max_length
            score = max_length / actual_length if actual_length > 0 else 0.0

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=within_range,
            details={
                "actual_length": actual_length,
                "min_length": min_length,
                "max_length": max_length if max_length != float("inf") else None,
            },
            message=f"Length {actual_length} is {'within' if within_range else 'outside'} expected range",
        )
