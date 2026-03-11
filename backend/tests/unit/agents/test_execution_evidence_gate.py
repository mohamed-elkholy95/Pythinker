"""Tests for step-level external evidence enforcement (Fix 4A)."""

from app.domain.services.agents.execution import ExecutionAgent


class TestIsResearchStep:
    """Test research step detection by keyword matching."""

    def _make_checker(self):
        return type(
            "MockAgent",
            (),
            {
                "_RESEARCH_STEP_KEYWORDS": ExecutionAgent._RESEARCH_STEP_KEYWORDS,
                "_is_research_step": ExecutionAgent._is_research_step,
            },
        )()

    def test_research_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Research GLM-5 best practices")

    def test_investigate_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Investigate pricing models for cloud providers")

    def test_compare_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Compare React vs Vue performance benchmarks")

    def test_find_information_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Find information about Python 3.12 features")

    def test_gather_data_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Gather data on GPU benchmark results")

    def test_pricing_keyword_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Find competitive pricing for SaaS tools")

    def test_best_practices_detected(self):
        agent = self._make_checker()
        assert agent._is_research_step("Document best practices for Docker security")

    def test_non_research_step_not_detected(self):
        agent = self._make_checker()
        assert not agent._is_research_step("Write the final report")
        assert not agent._is_research_step("Create a benchmark script")
        assert not agent._is_research_step("Generate a summary of findings")

    def test_case_insensitive(self):
        agent = self._make_checker()
        assert agent._is_research_step("RESEARCH the latest AI trends")


class TestExternalEvidenceTools:
    """Verify the evidence-producing tool set matches source_tracker.py dispatch."""

    def test_evidence_tools_match_source_tracker(self):
        from app.domain.models.tool_name import ToolName

        expected = {
            ToolName.INFO_SEARCH_WEB,
            ToolName.WIDE_RESEARCH,
            ToolName.BROWSER_NAVIGATE,
            ToolName.BROWSER_GET_CONTENT,
            ToolName.BROWSER_VIEW,
        }
        assert expected == ExecutionAgent._EXTERNAL_EVIDENCE_TOOLS
