"""Tests for ExecutionAgent synthesis gate integration."""

from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict


class TestIsSynthesisStep:
    """Test synthesis step detection."""

    def test_write_report_detected(self):
        # Create a minimal mock that has _is_synthesis_step
        from app.domain.services.agents.execution import ExecutionAgent

        assert "write report" in ExecutionAgent._SYNTHESIS_KEYWORDS

    def test_non_synthesis_step(self):
        from app.domain.services.agents.execution import ExecutionAgent

        agent = type(
            "MockAgent",
            (),
            {
                "_SYNTHESIS_KEYWORDS": ExecutionAgent._SYNTHESIS_KEYWORDS,
                "_is_synthesis_step": ExecutionAgent._is_synthesis_step,
            },
        )()
        assert not agent._is_synthesis_step("Search for Python documentation")
        assert agent._is_synthesis_step("Write report on findings")
        assert agent._is_synthesis_step("Synthesize all research results")
        assert agent._is_synthesis_step("Create final report with analysis")

    def test_all_keywords_detected(self):
        from app.domain.services.agents.execution import ExecutionAgent

        agent = type(
            "MockAgent",
            (),
            {
                "_SYNTHESIS_KEYWORDS": ExecutionAgent._SYNTHESIS_KEYWORDS,
                "_is_synthesis_step": ExecutionAgent._is_synthesis_step,
            },
        )()
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

        agent = type(
            "MockAgent",
            (),
            {
                "_SYNTHESIS_KEYWORDS": ExecutionAgent._SYNTHESIS_KEYWORDS,
                "_is_synthesis_step": ExecutionAgent._is_synthesis_step,
            },
        )()
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


class TestSoftFailDisclaimer:
    """Soft-fail synthesis steps should inject a caveat into the prompt."""

    def test_apply_synthesis_gate_soft_fail_disclaimer_prepends_warning(self):
        from app.domain.services.agents.execution import apply_synthesis_gate_soft_fail_disclaimer

        gate_result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.soft_fail,
            reasons=["Insufficient high-confidence sources: 1/2"],
            total_fetched=2,
            thresholds_applied={"min_high_confidence": 2},
        )

        prompt = apply_synthesis_gate_soft_fail_disclaimer(
            "Write the final report.",
            gate_result,
        )

        assert prompt.startswith("NOTE: Some evidence thresholds were not fully met.")
        assert "Insufficient high-confidence sources: 1/2" in prompt
        assert prompt.endswith("Write the final report.")


class TestSynthesisGateBackstop:
    """Test the backstop: no sources + no evidence = hard_fail (Fix 4B)."""

    def test_backstop_hard_fail_no_sources_no_evidence(self):
        """When source_tracker has no sources AND policy has no evidence_records, hard_fail."""
        from unittest.mock import MagicMock, patch

        from app.domain.services.agents.execution import ExecutionAgent

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = []
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = []
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
            thresholds_applied={},
        )

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result is not None
        assert result.verdict == SynthesisGateVerdict.hard_fail
        assert any("No external evidence" in r for r in result.reasons)

    def test_backstop_passes_with_sources(self):
        """When source_tracker has sources, backstop does not fire."""
        from unittest.mock import MagicMock, patch

        from app.domain.services.agents.execution import ExecutionAgent

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = [MagicMock()]
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = []
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
            thresholds_applied={},
        )

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result.verdict == SynthesisGateVerdict.pass_

    def test_backstop_passes_with_evidence_records(self):
        """When policy has evidence_records, backstop does not fire."""
        from unittest.mock import MagicMock, patch

        from app.domain.services.agents.execution import ExecutionAgent

        agent = MagicMock()
        agent._source_tracker = MagicMock()
        agent._source_tracker.get_collected_sources.return_value = []
        agent._research_execution_policy = MagicMock()
        agent._research_execution_policy.evidence_records = [MagicMock()]
        agent._research_execution_policy.can_synthesize.return_value = SynthesisGateResult(
            verdict=SynthesisGateVerdict.pass_,
            reasons=[],
            thresholds_applied={},
        )

        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(research_pipeline_mode="enforced")
            result = ExecutionAgent._check_synthesis_gate(agent)

        assert result.verdict == SynthesisGateVerdict.pass_
