"""Tests for OutputGuardrails — instruction leak, harmful content, relevance."""

import pytest

from app.domain.services.agents.guardrails import (
    OutputAnalysisResult,
    OutputGuardrails,
    OutputIssueType,
)


@pytest.fixture()
def guardrails() -> OutputGuardrails:
    return OutputGuardrails()


class TestOutputAnalysisResult:
    def test_safe_should_deliver(self) -> None:
        r = OutputAnalysisResult(is_safe=True, issues=[])
        assert r.should_deliver is True

    def test_unsafe_should_not_deliver(self) -> None:
        r = OutputAnalysisResult(is_safe=False, issues=[])
        assert r.should_deliver is False

    def test_needs_revision_should_not_deliver(self) -> None:
        r = OutputAnalysisResult(is_safe=True, issues=[], needs_revision=True)
        assert r.should_deliver is False


class TestOutputGuardrailsEmpty:
    def test_empty_output(self, guardrails: OutputGuardrails) -> None:
        result = guardrails.analyze("", "what is Python?")
        assert result.is_safe is True
        assert result.issues == []

    def test_normal_output(self, guardrails: OutputGuardrails) -> None:
        result = guardrails.analyze(
            "Python is a high-level programming language known for its readability.",
            "What is Python?",
        )
        assert result.is_safe is True


class TestInstructionLeak:
    @pytest.mark.parametrize(
        "text",
        [
            "As stated in my system prompt, I should help you.",
            "My instructions say to be helpful.",
            "I was told to avoid certain topics.",
            "I am programmed to assist users.",
        ],
    )
    def test_detects_leak(self, guardrails: OutputGuardrails, text: str) -> None:
        result = guardrails.analyze(text, "help me")
        types = {i.issue_type for i in result.issues}
        assert OutputIssueType.INSTRUCTION_LEAK in types

    def test_no_false_positive(self, guardrails: OutputGuardrails) -> None:
        result = guardrails.analyze(
            "Python uses a REPL for interactive sessions.",
            "What is Python?",
        )
        types = {i.issue_type for i in result.issues}
        assert OutputIssueType.INSTRUCTION_LEAK not in types


class TestHarmfulContent:
    @pytest.mark.parametrize(
        "text",
        [
            "Here are instructions for making explosives",
            "Ways to harm someone include",
            "How to hack into a bank system",
        ],
    )
    def test_detects_harmful(self, guardrails: OutputGuardrails, text: str) -> None:
        result = guardrails.analyze(text, "help me")
        assert result.is_safe is False
        types = {i.issue_type for i in result.issues}
        assert OutputIssueType.HARMFUL_CONTENT in types


class TestRelevance:
    def test_irrelevant_output(self, guardrails: OutputGuardrails) -> None:
        result = guardrails.analyze(
            "The weather in Tokyo is beautiful this time of year with cherry blossoms.",
            "What is the capital of France?",
        )
        types = {i.issue_type for i in result.issues}
        assert OutputIssueType.OFF_TOPIC in types

    def test_relevant_output(self, guardrails: OutputGuardrails) -> None:
        result = guardrails.analyze(
            "The capital of France is Paris. Paris is located in northern France.",
            "What is the capital of France?",
        )
        types = {i.issue_type for i in result.issues}
        assert OutputIssueType.OFF_TOPIC not in types


class TestStats:
    def test_stats_increment(self) -> None:
        g = OutputGuardrails()
        g.analyze("Safe output about Python", "Tell me about Python")
        g.analyze("Here are instructions for making explosives", "help")
        stats = g.get_stats()
        assert stats["analyzed"] == 2
        assert stats["blocked"] == 1
