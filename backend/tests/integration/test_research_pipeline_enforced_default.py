"""Tests verifying the research pipeline defaults to enforced mode."""

from __future__ import annotations

from types import SimpleNamespace


class TestResearchPipelineEnforcedDefault:
    """Verify the pipeline defaults to enforced, not shadow."""

    def test_config_default_is_enforced(self):
        """The config mixin default must be 'enforced' so the synthesis gate blocks."""
        from app.core.config_research_pipeline import ResearchPipelineSettingsMixin

        mixin = ResearchPipelineSettingsMixin()
        assert mixin.research_pipeline_mode == "enforced"

    def test_synthesis_gate_blocks_in_enforced_mode(self):
        """In enforced mode, _check_synthesis_gate returns a result (not None)."""
        from unittest.mock import MagicMock, patch

        from app.domain.models.evidence import SynthesisGateVerdict

        mock_policy = MagicMock()
        mock_result = MagicMock()
        mock_result.verdict = SynthesisGateVerdict.hard_fail
        mock_result.reasons = ["too few sources"]
        mock_result.thresholds_applied = {}
        mock_policy.can_synthesize.return_value = mock_result

        mock_settings = SimpleNamespace(research_pipeline_mode="enforced")
        with patch("app.core.config.get_settings", return_value=mock_settings):
            from app.domain.services.agents.execution import ExecutionAgent

            agent = ExecutionAgent.__new__(ExecutionAgent)
            agent._research_execution_policy = mock_policy
            result = agent._check_synthesis_gate()

        assert result is not None
        assert result.verdict == SynthesisGateVerdict.hard_fail

    def test_synthesis_step_detection(self):
        """_is_synthesis_step should detect synthesis keywords."""
        from app.domain.services.agents.execution import ExecutionAgent

        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent._research_execution_policy = None
        assert agent._is_synthesis_step("Compile findings and synthesize report")
        assert agent._is_synthesis_step("write summary of the research")
        assert agent._is_synthesis_step("Generate report from collected data")
        assert not agent._is_synthesis_step("Search for Python frameworks")
