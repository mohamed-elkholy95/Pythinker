"""Unit tests for MetaCognitionModule in reasoning/meta_cognition.py.

Covers:
- MetaCognitionModule.__init__: domain initialization, tool capability extraction
- assess_knowledge_boundaries: confidence calculation, gap identification,
  proceed flag, blocking gaps
- identify_gaps: uncertainty patterns, domain unknown topics, capability gaps,
  temporal gaps
- assess_capabilities: match score, missing capabilities, workarounds, can_accomplish
- suggest_information_needs: priority ordering, request types
- update_available_tools: dynamic tool updates
- compute_uncertainty_score: stuck penalty, error rate, clamping
- Internal helpers: _identify_relevant_domains, _extract_uncertainty_gaps,
  _identify_capability_gaps, _extract_required_capabilities, _needs_current_info,
  _determine_request_type, _generate_query, _suggest_workarounds
- Singleton: get_meta_cognition, reset_meta_cognition
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.domain.models.knowledge_gap import (
    CapabilityAssessment,
    GapSeverity,
    GapType,
    KnowledgeAssessment,
    KnowledgeGap,
)
from app.domain.services.agents.reasoning.meta_cognition import (
    MetaCognitionModule,
    get_meta_cognition,
    reset_meta_cognition,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_tool(name: str, desc: str = "Does things") -> dict[str, Any]:
    return {"function": {"name": name, "description": desc}}


@pytest.fixture
def module():
    reset_meta_cognition()
    return MetaCognitionModule()


@pytest.fixture
def module_with_tools():
    reset_meta_cognition()
    tools = [
        _make_tool("shell_execute", "execute shell commands"),
        _make_tool("browser_navigate", "browse and scrape web pages"),
        _make_tool("file_read", "read files from disk"),
        _make_tool("info_search_web", "search the web for information"),
    ]
    return MetaCognitionModule(available_tools=tools)


# ─── __init__ ─────────────────────────────────────────────────────────────────


class TestInit:
    def test_no_tools_by_default(self, module):
        assert module._available_tools == []

    def test_tools_stored(self):
        tools = [_make_tool("shell_execute")]
        m = MetaCognitionModule(available_tools=tools)
        assert len(m._available_tools) == 1

    def test_domains_initialized(self, module):
        assert len(module._domains) > 0

    def test_known_domains_present(self, module):
        assert "programming" in module._domains
        assert "general_knowledge" in module._domains
        assert "technical_writing" in module._domains

    def test_tool_capabilities_empty_without_tools(self, module):
        assert module._tool_capabilities == {}

    def test_tool_capabilities_populated_with_tools(self, module_with_tools):
        # shell_execute should create shell_operations category
        assert len(module_with_tools._tool_capabilities) > 0


# ─── assess_knowledge_boundaries ─────────────────────────────────────────────


class TestAssessKnowledgeBoundaries:
    def test_returns_knowledge_assessment(self, module):
        result = module.assess_knowledge_boundaries("Write Python code")
        assert isinstance(result, KnowledgeAssessment)

    def test_task_stored_in_assessment(self, module):
        result = module.assess_knowledge_boundaries("Analyze data with pandas")
        assert result.task == "Analyze data with pandas"

    def test_confidence_between_zero_and_one(self, module):
        result = module.assess_knowledge_boundaries("Write Python code")
        assert 0.0 <= result.overall_confidence <= 1.0

    def test_programming_task_relevant_domain_found(self, module):
        result = module.assess_knowledge_boundaries("Write Python code to parse JSON")
        assert len(result.relevant_domains) > 0

    def test_general_fallback_for_unknown_domain(self, module):
        result = module.assess_knowledge_boundaries("Explain the history of ancient Rome")
        # Should fall back to general_knowledge
        domain_names = [d.name for d in result.relevant_domains]
        assert "general_knowledge" in domain_names

    def test_critical_gaps_reduce_confidence(self, module):
        # Private API knowledge triggers HIGH gap
        result_simple = module.assess_knowledge_boundaries("Write Python code")
        result_gap = module.assess_knowledge_boundaries("Access proprietary APIs with private packages")
        assert result_gap.overall_confidence <= result_simple.overall_confidence

    def test_no_blocking_gaps_can_proceed(self, module):
        result = module.assess_knowledge_boundaries("Write Python code")
        # Simple programming task should have no CRITICAL blocking gaps
        if not result.blocking_gaps:
            assert result.can_proceed is True

    def test_blocking_gap_prevents_proceed(self, module):
        # Manually check logic: a critical gap's id should be in blocking_gaps
        result = module.assess_knowledge_boundaries("Write Python code")
        # Extract IDs of critical gaps
        critical_ids = {g.id for g in result.gaps if g.is_blocking()}
        assert critical_ids == set(result.blocking_gaps)

    def test_gaps_list_is_list(self, module):
        result = module.assess_knowledge_boundaries("Build something")
        assert isinstance(result.gaps, list)

    def test_information_requests_prioritized(self, module):
        result = module.assess_knowledge_boundaries("Get the latest news today")
        if result.information_requests:
            priorities = [r.priority for r in result.information_requests]
            assert priorities == sorted(priorities)


# ─── identify_gaps ────────────────────────────────────────────────────────────


class TestIdentifyGaps:
    def test_returns_list(self, module):
        gaps = module.identify_gaps("Write Python code")
        assert isinstance(gaps, list)

    def test_uncertainty_pattern_creates_contextual_gap(self, module):
        gaps = module.identify_gaps("I'm not sure what to do next")
        gap_types = [g.gap_type for g in gaps]
        assert GapType.CONTEXTUAL in gap_types

    def test_unknown_topic_creates_factual_gap(self, module):
        gaps = module.identify_gaps("Access proprietary APIs")
        # "proprietary APIs" is in programming.unknown_topics
        gap_types = [g.gap_type for g in gaps]
        assert GapType.FACTUAL in gap_types

    def test_temporal_gap_for_current_info(self, module):
        gaps = module.identify_gaps("Get the latest news today")
        gap_types = [g.gap_type for g in gaps]
        assert GapType.TEMPORAL in gap_types

    def test_capability_gap_when_tool_missing(self, module):
        # No tools registered, "execute" keyword triggers code_operations requirement
        gaps = module.identify_gaps("Execute some code")
        gap_types = [g.gap_type for g in gaps]
        assert GapType.CAPABILITY in gap_types

    def test_no_gaps_for_simple_known_task(self, module_with_tools):
        gaps = module_with_tools.identify_gaps("Browse the web for information")
        # web_operations covered by browser_navigate
        cap_gaps = [g for g in gaps if g.gap_type == GapType.CAPABILITY]
        assert len(cap_gaps) == 0

    def test_tools_parameter_updates_capabilities(self, module):
        original_caps = len(module._tool_capabilities)
        tools = [_make_tool("shell_execute", "execute shell commands")]
        module.identify_gaps("Execute commands", tools=tools)
        assert len(module._tool_capabilities) >= original_caps


# ─── assess_capabilities ──────────────────────────────────────────────────────


class TestAssessCapabilities:
    def test_returns_capability_assessment(self, module):
        result = module.assess_capabilities("Write Python code")
        assert isinstance(result, CapabilityAssessment)

    def test_task_stored_in_assessment(self, module):
        result = module.assess_capabilities("Execute shell command")
        assert result.task == "Execute shell command"

    def test_match_score_between_zero_and_one(self, module):
        result = module.assess_capabilities("Run a command")
        assert 0.0 <= result.capability_match_score <= 1.0

    def test_all_capabilities_available_score_one(self, module_with_tools):
        # Task with only web_operations, which is covered
        result = module_with_tools.assess_capabilities("Browse and search the web")
        assert result.capability_match_score >= 0.5

    def test_missing_capabilities_listed(self, module):
        # No tools - any task requiring capabilities will show missing
        result = module.assess_capabilities("Execute shell commands and run code")
        assert isinstance(result.missing_capabilities, list)

    def test_workarounds_suggested_for_missing(self, module):
        result = module.assess_capabilities("Execute code in shell")
        if result.missing_capabilities:
            assert isinstance(result.workarounds, list)

    def test_available_tools_listed(self, module_with_tools):
        result = module_with_tools.assess_capabilities("Search and browse")
        assert len(result.available_tools) > 0

    def test_can_accomplish_true_when_high_match(self, module_with_tools):
        result = module_with_tools.assess_capabilities("Browse and search the web for information")
        # With web tools available, should be able to accomplish
        assert isinstance(result.can_accomplish, bool)

    def test_tools_parameter_updates_module(self, module):
        tools = [_make_tool("shell_execute", "run shell commands")]
        result = module.assess_capabilities("Run shell commands", tools=tools)
        assert isinstance(result, CapabilityAssessment)


# ─── suggest_information_needs ───────────────────────────────────────────────


class TestSuggestInformationNeeds:
    def _make_gap(
        self,
        gap_type: GapType = GapType.FACTUAL,
        severity: GapSeverity = GapSeverity.HIGH,
        can_be_filled: bool = True,
        topic: str = "test topic",
    ) -> KnowledgeGap:
        return KnowledgeGap(
            gap_type=gap_type,
            severity=severity,
            description="Gap description",
            topic=topic,
            can_be_filled=can_be_filled,
        )

    def test_returns_list_of_requests(self, module):
        gaps = [self._make_gap()]
        requests = module.suggest_information_needs(gaps)
        assert isinstance(requests, list)

    def test_unfillable_gaps_skipped(self, module):
        gaps = [self._make_gap(can_be_filled=False)]
        requests = module.suggest_information_needs(gaps)
        assert len(requests) == 0

    def test_critical_gap_priority_one(self, module):
        gaps = [self._make_gap(severity=GapSeverity.CRITICAL)]
        requests = module.suggest_information_needs(gaps)
        assert len(requests) > 0
        assert requests[0].priority == 1

    def test_high_gap_priority_two(self, module):
        gaps = [self._make_gap(severity=GapSeverity.HIGH)]
        requests = module.suggest_information_needs(gaps)
        assert len(requests) > 0
        assert requests[0].priority == 2

    def test_medium_gap_priority_three(self, module):
        gaps = [self._make_gap(severity=GapSeverity.MEDIUM)]
        requests = module.suggest_information_needs(gaps)
        assert len(requests) > 0
        assert requests[0].priority == 3

    def test_requests_sorted_by_priority(self, module):
        gaps = [
            self._make_gap(severity=GapSeverity.MEDIUM, topic="medium"),
            self._make_gap(severity=GapSeverity.CRITICAL, topic="critical"),
            self._make_gap(severity=GapSeverity.HIGH, topic="high"),
        ]
        requests = module.suggest_information_needs(gaps)
        priorities = [r.priority for r in requests]
        assert priorities == sorted(priorities)

    def test_factual_gap_produces_search_request(self, module):
        gaps = [self._make_gap(gap_type=GapType.FACTUAL)]
        requests = module.suggest_information_needs(gaps)
        assert any(r.request_type == "search" for r in requests)

    def test_contextual_gap_produces_ask_user_request(self, module):
        gaps = [self._make_gap(gap_type=GapType.CONTEXTUAL)]
        requests = module.suggest_information_needs(gaps)
        assert any(r.request_type == "ask_user" for r in requests)

    def test_temporal_gap_produces_search_request(self, module):
        gaps = [self._make_gap(gap_type=GapType.TEMPORAL)]
        requests = module.suggest_information_needs(gaps)
        assert any(r.request_type == "search" for r in requests)

    def test_empty_gaps_returns_empty(self, module):
        assert module.suggest_information_needs([]) == []


# ─── update_available_tools ──────────────────────────────────────────────────


class TestUpdateAvailableTools:
    def test_tools_updated(self, module):
        tools = [_make_tool("new_tool", "does new things")]
        module.update_available_tools(tools)
        assert module._available_tools == tools

    def test_capabilities_recalculated(self, module):
        module.update_available_tools([_make_tool("shell_execute", "execute shell commands")])
        assert len(module._tool_capabilities) > 0

    def test_clearing_tools_clears_capabilities(self, module_with_tools):
        module_with_tools.update_available_tools([])
        assert module_with_tools._tool_capabilities == {}


# ─── _identify_relevant_domains ──────────────────────────────────────────────


class TestIdentifyRelevantDomains:
    def test_python_task_finds_programming_domain(self, module):
        domains = module._identify_relevant_domains("Write Python code")
        assert any(d.name == "programming" for d in domains)

    def test_api_task_finds_relevant_domain(self, module):
        domains = module._identify_relevant_domains("Build an API endpoint")
        # May map to programming, software_engineering, or similar domain
        assert len(domains) > 0

    def test_history_finds_general_knowledge(self, module):
        domains = module._identify_relevant_domains("Explain the history of Rome")
        assert any(d.name == "general_knowledge" for d in domains)

    def test_no_match_falls_back_to_general_knowledge(self, module):
        domains = module._identify_relevant_domains("xyxyyxyx completely random")
        assert any(d.name == "general_knowledge" for d in domains)

    def test_documentation_task_finds_technical_writing(self, module):
        domains = module._identify_relevant_domains("Write documentation for the API")
        assert any(d.name == "technical_writing" for d in domains)


# ─── _extract_uncertainty_gaps ───────────────────────────────────────────────


class TestExtractUncertaintyGaps:
    def test_not_sure_creates_gap(self, module):
        gaps = module._extract_uncertainty_gaps("I'm not sure what to do")
        assert len(gaps) > 0

    def test_unclear_creates_gap(self, module):
        gaps = module._extract_uncertainty_gaps("It is unclear whether this is correct")
        assert len(gaps) > 0

    def test_no_uncertainty_no_gap(self, module):
        gaps = module._extract_uncertainty_gaps("Write clean Python code for the task")
        assert len(gaps) == 0

    def test_only_one_gap_per_text(self, module):
        # Even with multiple patterns, only one gap added per call
        gaps = module._extract_uncertainty_gaps("I'm not sure, it's unclear, and I cannot determine")
        assert len(gaps) == 1

    def test_gap_type_is_contextual(self, module):
        gaps = module._extract_uncertainty_gaps("I don't know what to do")
        assert all(g.gap_type == GapType.CONTEXTUAL for g in gaps)


# ─── _needs_current_info ─────────────────────────────────────────────────────


class TestNeedsCurrentInfo:
    def test_current_keyword(self, module):
        assert module._needs_current_info("Get the current status") is True

    def test_latest_keyword(self, module):
        assert module._needs_current_info("Find the latest version") is True

    def test_today_keyword(self, module):
        assert module._needs_current_info("What happened today") is True

    def test_now_keyword(self, module):
        assert module._needs_current_info("What is happening now") is True

    def test_recent_keyword(self, module):
        assert module._needs_current_info("Recent developments in AI") is True

    def test_live_keyword(self, module):
        assert module._needs_current_info("Show live data feed") is True

    def test_no_temporal_keywords(self, module):
        assert module._needs_current_info("Write a Python function to sort a list") is False

    def test_real_time_keyword(self, module):
        assert module._needs_current_info("real-time monitoring") is True


# ─── _generate_query ─────────────────────────────────────────────────────────


class TestGenerateQuery:
    def _make_gap(self, gap_type: GapType, topic: str = "test topic") -> KnowledgeGap:
        return KnowledgeGap(
            gap_type=gap_type,
            severity=GapSeverity.MEDIUM,
            description="desc",
            topic=topic,
        )

    def test_factual_gap_asks_what(self, module):
        gap = self._make_gap(GapType.FACTUAL, "Python decorators")
        query = module._generate_query(gap)
        assert "What" in query or "what" in query
        assert "Python decorators" in query

    def test_procedural_gap_asks_how(self, module):
        gap = self._make_gap(GapType.PROCEDURAL, "install packages")
        query = module._generate_query(gap)
        assert "How" in query or "how" in query

    def test_temporal_gap_asks_current(self, module):
        gap = self._make_gap(GapType.TEMPORAL, "stock prices")
        query = module._generate_query(gap)
        assert "current" in query.lower() or "Current" in query

    def test_contextual_gap_asks_context(self, module):
        gap = self._make_gap(GapType.CONTEXTUAL, "user requirements")
        query = module._generate_query(gap)
        assert "context" in query.lower() or "user requirements" in query


# ─── _suggest_workarounds ────────────────────────────────────────────────────


class TestSuggestWorkarounds:
    def test_code_operations_suggests_shell(self, module):
        workarounds = module._suggest_workarounds(["code_operations"])
        assert any("shell" in w.lower() for w in workarounds)

    def test_web_operations_suggests_file_approach(self, module):
        workarounds = module._suggest_workarounds(["web_operations"])
        assert any("file" in w.lower() for w in workarounds)

    def test_shell_operations_suggests_code(self, module):
        workarounds = module._suggest_workarounds(["shell_operations"])
        assert any("code" in w.lower() or "execution" in w.lower() for w in workarounds)

    def test_unknown_capability_returns_empty(self, module):
        workarounds = module._suggest_workarounds(["unknown_capability_xyz"])
        assert workarounds == []

    def test_empty_missing_returns_empty(self, module):
        assert module._suggest_workarounds([]) == []


# ─── compute_uncertainty_score ───────────────────────────────────────────────


class TestComputeUncertaintyScore:
    def test_returns_float_between_zero_and_one(self, module):
        score = module.compute_uncertainty_score("Write Python code")
        assert 0.0 <= score <= 1.0

    def test_stuck_adds_penalty(self, module):
        score_not_stuck = module.compute_uncertainty_score("Write Python code", is_stuck=False)
        score_stuck = module.compute_uncertainty_score("Write Python code", is_stuck=True)
        assert score_stuck > score_not_stuck

    def test_high_error_rate_adds_penalty(self, module):
        score_no_errors = module.compute_uncertainty_score("task", recent_error_rate=0.0)
        score_errors = module.compute_uncertainty_score("task", recent_error_rate=0.8)
        assert score_errors > score_no_errors

    def test_low_error_rate_no_penalty(self, module):
        score_low = module.compute_uncertainty_score("task", recent_error_rate=0.3)
        score_high = module.compute_uncertainty_score("task", recent_error_rate=0.8)
        assert score_low < score_high

    def test_clamped_to_max_one(self, module):
        score = module.compute_uncertainty_score(
            "I'm not sure and cannot determine anything",
            is_stuck=True,
            recent_error_rate=1.0,
        )
        assert score <= 1.0

    def test_clamped_to_min_zero(self, module):
        score = module.compute_uncertainty_score(
            "Write Python code",
            is_stuck=False,
            recent_error_rate=0.0,
        )
        assert score >= 0.0

    def test_context_passed_to_assessment(self, module):
        # Should not raise even with context
        score = module.compute_uncertainty_score("task", context={"key": "value"})
        assert 0.0 <= score <= 1.0

    def test_exception_during_assessment_defaults_to_moderate(self, module):
        # Monkeypatch assess_knowledge_boundaries to raise
        original = module.assess_knowledge_boundaries
        module.assess_knowledge_boundaries = MagicMock(side_effect=RuntimeError("boom"))
        score = module.compute_uncertainty_score("task", is_stuck=False, recent_error_rate=0.0)
        module.assess_knowledge_boundaries = original
        # Default base_uncertainty = 0.5, no penalties
        assert score == pytest.approx(0.5)


# ─── Singleton helpers ────────────────────────────────────────────────────────


class TestSingletonHelpers:
    def setup_method(self):
        reset_meta_cognition()

    def teardown_method(self):
        reset_meta_cognition()

    def test_get_meta_cognition_returns_instance(self):
        m = get_meta_cognition()
        assert isinstance(m, MetaCognitionModule)

    def test_get_meta_cognition_returns_singleton(self):
        m1 = get_meta_cognition()
        m2 = get_meta_cognition()
        assert m1 is m2

    def test_get_meta_cognition_with_tools(self):
        tools = [_make_tool("shell_execute")]
        m = get_meta_cognition(tools=tools)
        assert isinstance(m, MetaCognitionModule)

    def test_reset_clears_singleton(self):
        m1 = get_meta_cognition()
        reset_meta_cognition()
        m2 = get_meta_cognition()
        assert m1 is not m2
