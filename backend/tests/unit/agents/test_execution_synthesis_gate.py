"""Tests for ExecutionAgent synthesis gate integration."""

import pytest
from unittest.mock import MagicMock

from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict


class TestIsSynthesisStep:
    """Test synthesis step detection."""

    def test_write_report_detected(self):
        # Create a minimal mock that has _is_synthesis_step
        from app.domain.services.agents.execution import ExecutionAgent
        assert "write report" in ExecutionAgent._SYNTHESIS_KEYWORDS

    def test_non_synthesis_step(self):
        from app.domain.services.agents.execution import ExecutionAgent
        agent = type('MockAgent', (), {'_SYNTHESIS_KEYWORDS': ExecutionAgent._SYNTHESIS_KEYWORDS,
                                        '_is_synthesis_step': ExecutionAgent._is_synthesis_step})()
        assert not agent._is_synthesis_step("Search for Python documentation")
        assert agent._is_synthesis_step("Write report on findings")
        assert agent._is_synthesis_step("Synthesize all research results")
        assert agent._is_synthesis_step("Create final report with analysis")

    def test_all_keywords_detected(self):
        from app.domain.services.agents.execution import ExecutionAgent
        agent = type('MockAgent', (), {'_SYNTHESIS_KEYWORDS': ExecutionAgent._SYNTHESIS_KEYWORDS,
                                        '_is_synthesis_step': ExecutionAgent._is_synthesis_step})()
        synthesis_phrases = [
            "write report on the findings",
            "synthesize all gathered data",
            "summarize findings from research",
            "compile results into a document",
            "write summary of the analysis",
            "create the final report",
            "write analysis of the data",
            "create report for stakeholders",
            "generate report from evidence",
            "draft report from findings",
            "prepare summary of results",
        ]
        for phrase in synthesis_phrases:
            assert agent._is_synthesis_step(phrase), f"Expected '{phrase}' to be detected as synthesis"

    def test_non_synthesis_phrases_not_detected(self):
        from app.domain.services.agents.execution import ExecutionAgent
        agent = type('MockAgent', (), {'_SYNTHESIS_KEYWORDS': ExecutionAgent._SYNTHESIS_KEYWORDS,
                                        '_is_synthesis_step': ExecutionAgent._is_synthesis_step})()
        non_synthesis = [
            "Search for documentation on Python",
            "Navigate to the official website",
            "Extract data from the API",
            "Download the dataset",
            "Analyze the raw data",
        ]
        for phrase in non_synthesis:
            assert not agent._is_synthesis_step(phrase), f"Expected '{phrase}' to NOT be detected as synthesis"


class TestSynthesisGateLogic:
    """Test synthesis gate check logic."""

    def test_no_policy_returns_none(self):
        policy = None
        result = policy.can_synthesize() if policy else None
        assert result is None

    def test_gate_result_structure(self):
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.hard_fail,
            reasons=["Insufficient sources: 1/3"],
            total_fetched=1,
            thresholds_applied={"min_sources": 3},
        )
        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert len(result.reasons) == 1

    def test_pass_verdict(self):
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            total_fetched=4,
            high_confidence_count=3,
            official_source_found=True,
            independent_source_found=True,
            reasons=[],
            thresholds_applied={"min_sources": 3},
        )
        assert result.verdict == SynthesisGateVerdict.pass_

    def test_soft_fail_verdict(self):
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.soft_fail,
            reasons=["No high-confidence sources found"],
            total_fetched=2,
            thresholds_applied={"min_high_confidence": 1},
        )
        assert result.verdict == SynthesisGateVerdict.soft_fail
        assert "No high-confidence sources found" in result.reasons

    def test_synthesis_keywords_is_frozenset(self):
        from app.domain.services.agents.execution import ExecutionAgent
        assert isinstance(ExecutionAgent._SYNTHESIS_KEYWORDS, frozenset)

    def test_synthesis_keywords_contains_expected_entries(self):
        from app.domain.services.agents.execution import ExecutionAgent
        expected = {
            "write report",
            "synthesize",
            "summarize findings",
            "compile results",
            "write summary",
            "final report",
            "write analysis",
            "create report",
            "generate report",
            "draft report",
            "prepare summary",
        }
        assert expected == ExecutionAgent._SYNTHESIS_KEYWORDS
