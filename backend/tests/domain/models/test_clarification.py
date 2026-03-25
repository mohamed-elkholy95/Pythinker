"""Tests for ClarificationRequest domain model."""

from app.domain.models.clarification import ClarificationRequest, ClarificationType


class TestClarificationType:
    def test_values(self) -> None:
        expected = {"missing_info", "ambiguous_requirement", "approach_choice", "risk_confirmation", "suggestion"}
        assert {t.value for t in ClarificationType} == expected


class TestClarificationRequest:
    def test_minimal(self) -> None:
        cr = ClarificationRequest(
            question="What format?",
            clarification_type=ClarificationType.MISSING_INFO,
        )
        assert cr.context is None
        assert cr.options is None

    def test_format_simple(self) -> None:
        cr = ClarificationRequest(
            question="What format do you need?",
            clarification_type=ClarificationType.MISSING_INFO,
        )
        formatted = cr.format()
        assert "[?]" in formatted
        assert "format" in formatted

    def test_format_with_context(self) -> None:
        cr = ClarificationRequest(
            question="Which approach?",
            clarification_type=ClarificationType.APPROACH_CHOICE,
            context="Multiple strategies available",
        )
        formatted = cr.format()
        assert "[>]" in formatted
        assert "Multiple strategies" in formatted
        assert "Which approach?" in formatted

    def test_format_with_options(self) -> None:
        cr = ClarificationRequest(
            question="Choose a method:",
            clarification_type=ClarificationType.APPROACH_CHOICE,
            options=["Option A", "Option B", "Option C"],
        )
        formatted = cr.format()
        assert "1. Option A" in formatted
        assert "2. Option B" in formatted
        assert "3. Option C" in formatted

    def test_format_risk(self) -> None:
        cr = ClarificationRequest(
            question="This will delete data. Proceed?",
            clarification_type=ClarificationType.RISK_CONFIRMATION,
        )
        formatted = cr.format()
        assert "[!]" in formatted

    def test_format_suggestion(self) -> None:
        cr = ClarificationRequest(
            question="Consider using a database",
            clarification_type=ClarificationType.SUGGESTION,
        )
        formatted = cr.format()
        assert "[*]" in formatted
