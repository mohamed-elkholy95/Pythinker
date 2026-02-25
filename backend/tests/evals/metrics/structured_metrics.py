"""Structured output evaluation metrics.

Metrics for evaluating JSON and structured outputs against
schemas and expected values.
"""

import json
import re
from typing import Any

from .base import BaseMetric, MetricScore


class JsonSchemaMetric(BaseMetric):
    """Validates output against a JSON schema.

    Supports JSON Schema Draft 7 validation when jsonschema is available,
    falls back to basic structural validation otherwise.
    """

    name = "json_schema"
    description = "Validates output against JSON schema"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        schema = expected.get("expected_json_schema")

        if not schema:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No JSON schema specified")

        # Try to parse output as JSON
        parsed = self._extract_json(actual_output)

        if parsed is None:
            return MetricScore(
                metric_name=self.name,
                score=0.0,
                passed=False,
                details={"error": "Could not parse output as JSON"},
                message="Failed to parse output as JSON",
            )

        # Try jsonschema validation first
        try:
            import jsonschema

            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors(parsed))

            if errors:
                error_messages = [
                    f"{e.json_path}: {e.message}"
                    for e in errors[:5]  # Limit error messages
                ]
                return MetricScore(
                    metric_name=self.name,
                    score=0.0,
                    passed=False,
                    details={
                        "validation_errors": error_messages,
                        "total_errors": len(errors),
                    },
                    message=f"Schema validation failed with {len(errors)} errors",
                )

            return MetricScore(
                metric_name=self.name,
                score=1.0,
                passed=True,
                details={"validated": True},
                message="JSON schema validation passed",
            )

        except ImportError:
            # Fall back to basic validation
            return self._basic_schema_check(parsed, schema)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Try to extract JSON from text."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
            r"\{[\s\S]*\}",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if "```" in pattern else match.group(0)
                    return json.loads(json_str.strip())
                except json.JSONDecodeError:
                    continue

        return None

    def _basic_schema_check(self, data: dict[str, Any], schema: dict[str, Any]) -> MetricScore:
        """Basic schema validation without jsonschema library."""
        errors = []

        # Check required fields
        required = schema.get("required", [])
        errors.extend(f"Missing required field: {field}" for field in required if field not in data)

        # Check property types
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in data:
                expected_type = prop_schema.get("type")
                actual_value = data[prop_name]

                if not self._check_type(actual_value, expected_type):
                    errors.append(
                        f"Field '{prop_name}' has wrong type: "
                        f"expected {expected_type}, got {type(actual_value).__name__}"
                    )

        passed = len(errors) == 0
        score = 1.0 if passed else max(0, 1 - len(errors) * 0.2)

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "validation_errors": errors,
                "method": "basic",
            },
            message="Basic schema check " + ("passed" if passed else f"failed with {len(errors)} errors"),
        )

    def _check_type(self, value: Any, expected_type: str | None) -> bool:
        """Check if value matches expected JSON type."""
        if expected_type is None:
            return True

        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        expected_python_type = type_map.get(expected_type)
        if expected_python_type is None:
            return True

        return isinstance(value, expected_python_type)


class JsonFieldMetric(BaseMetric):
    """Checks specific fields in JSON output have expected values."""

    name = "json_fields"
    description = "Validates specific JSON field values"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        expected_fields = expected.get("expected_json_fields", {})

        if not expected_fields:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No JSON fields to check")

        # Parse JSON
        try:
            # Try direct parse
            parsed = json.loads(actual_output)
        except json.JSONDecodeError:
            # Try to extract JSON
            match = re.search(r"\{[\s\S]*\}", actual_output)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return MetricScore(
                        metric_name=self.name, score=0.0, passed=False, message="Could not parse JSON from output"
                    )
            else:
                return MetricScore(metric_name=self.name, score=0.0, passed=False, message="No JSON found in output")

        # Check each expected field
        matched = []
        mismatched = []
        missing = []

        for field_path, expected_value in expected_fields.items():
            actual_value = self._get_nested_value(parsed, field_path)

            if actual_value is None:
                missing.append(field_path)
            elif self._values_match(actual_value, expected_value):
                matched.append(field_path)
            else:
                mismatched.append(
                    {
                        "field": field_path,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )

        total = len(expected_fields)
        score = len(matched) / total if total > 0 else 1.0
        passed = not mismatched and not missing

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "matched": matched,
                "mismatched": mismatched,
                "missing": missing,
            },
            message=f"Matched {len(matched)}/{total} JSON fields",
        )

    def _get_nested_value(self, data: dict[str, Any], path: str) -> Any:
        """Get value from nested dict using dot notation path."""
        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list):
                try:
                    index = int(key)
                    value = value[index]
                except (ValueError, IndexError):
                    return None
            else:
                return None

        return value

    def _values_match(self, actual: Any, expected: Any) -> bool:
        """Check if values match, with type coercion."""
        if actual == expected:
            return True

        # Try string comparison
        if str(actual).lower() == str(expected).lower():
            return True

        # Try numeric comparison
        try:
            return float(actual) == float(expected)
        except (ValueError, TypeError):
            pass

        return False


class StructuredOutputMetric(BaseMetric):
    """General metric for any structured output with custom validation."""

    name = "structured_output"
    description = "Validates structured output with custom rules"

    def evaluate(
        self,
        actual_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> MetricScore:
        rules = expected.get("structured_rules", [])

        if not rules:
            return MetricScore(metric_name=self.name, score=1.0, passed=True, message="No structured rules specified")

        # Try to parse as JSON
        try:
            parsed = json.loads(actual_output)
        except json.JSONDecodeError:
            parsed = None

        passed_rules = []
        failed_rules = []

        for rule in rules:
            rule_type = rule.get("type")
            result = self._evaluate_rule(actual_output, parsed, rule)

            if result:
                passed_rules.append(rule.get("name", rule_type))
            else:
                failed_rules.append(rule.get("name", rule_type))

        total = len(rules)
        score = len(passed_rules) / total if total > 0 else 1.0
        passed = len(failed_rules) == 0

        return MetricScore(
            metric_name=self.name,
            score=score,
            passed=passed,
            details={
                "passed_rules": passed_rules,
                "failed_rules": failed_rules,
            },
            message=f"Passed {len(passed_rules)}/{total} structural rules",
        )

    def _evaluate_rule(self, text: str, parsed: dict[str, Any] | None, rule: dict[str, Any]) -> bool:
        """Evaluate a single structural rule."""
        rule_type = rule.get("type")

        if rule_type == "has_field" and parsed:
            field = rule.get("field")
            return field in parsed

        if rule_type == "field_type" and parsed:
            field = rule.get("field")
            expected_type = rule.get("expected_type")
            if field not in parsed:
                return False
            return type(parsed[field]).__name__ == expected_type

        if rule_type == "field_in" and parsed:
            field = rule.get("field")
            allowed = rule.get("allowed", [])
            if field not in parsed:
                return False
            return parsed[field] in allowed

        if rule_type == "text_contains":
            substring = rule.get("substring", "")
            return substring.lower() in text.lower()

        if rule_type == "text_format":
            pattern = rule.get("pattern", "")
            return bool(re.search(pattern, text))

        return False
