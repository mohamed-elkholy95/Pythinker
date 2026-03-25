"""Tests for agent_types module: AgentCapability, AgentType, AgentSpec, AgentRegistry."""

import pytest

from app.domain.services.orchestration.agent_types import (
    AgentCapability,
    AgentRegistry,
    AgentSpec,
    AgentType,
    get_agent_registry,
)

# ---------------------------------------------------------------------------
# AgentCapability
# ---------------------------------------------------------------------------


class TestAgentCapability:
    def test_member_count(self) -> None:
        assert len(AgentCapability) == 16

    def test_all_expected_members_exist(self) -> None:
        expected = {
            "PLANNING",
            "EXECUTION",
            "ANALYSIS",
            "CODE_WRITING",
            "CODE_REVIEW",
            "CODE_EXECUTION",
            "WEB_BROWSING",
            "WEB_SEARCH",
            "FILE_OPERATIONS",
            "SHELL_COMMANDS",
            "RESEARCH",
            "SUMMARIZATION",
            "TRANSLATION",
            "DATA_EXTRACTION",
            "VERIFICATION",
            "CREATIVE",
        }
        assert {m.name for m in AgentCapability} == expected

    def test_string_values(self) -> None:
        assert AgentCapability.PLANNING == "planning"
        assert AgentCapability.EXECUTION == "execution"
        assert AgentCapability.ANALYSIS == "analysis"
        assert AgentCapability.CODE_WRITING == "code_writing"
        assert AgentCapability.CODE_REVIEW == "code_review"
        assert AgentCapability.CODE_EXECUTION == "code_execution"
        assert AgentCapability.WEB_BROWSING == "web_browsing"
        assert AgentCapability.WEB_SEARCH == "web_search"
        assert AgentCapability.FILE_OPERATIONS == "file_operations"
        assert AgentCapability.SHELL_COMMANDS == "shell_commands"
        assert AgentCapability.RESEARCH == "research"
        assert AgentCapability.SUMMARIZATION == "summarization"
        assert AgentCapability.TRANSLATION == "translation"
        assert AgentCapability.DATA_EXTRACTION == "data_extraction"
        assert AgentCapability.VERIFICATION == "verification"
        assert AgentCapability.CREATIVE == "creative"

    def test_inherits_str(self) -> None:
        assert isinstance(AgentCapability.RESEARCH, str)

    def test_value_equals_string_literal(self) -> None:
        for member in AgentCapability:
            assert member == member.value
            assert isinstance(member.value, str)

    def test_lookup_by_value(self) -> None:
        assert AgentCapability("research") is AgentCapability.RESEARCH
        assert AgentCapability("code_writing") is AgentCapability.CODE_WRITING


# ---------------------------------------------------------------------------
# AgentType
# ---------------------------------------------------------------------------


class TestAgentType:
    def test_member_count(self) -> None:
        assert len(AgentType) == 12

    def test_all_expected_members_exist(self) -> None:
        expected = {
            "COORDINATOR",
            "PLANNER",
            "EXECUTOR",
            "RESEARCHER",
            "CODER",
            "REVIEWER",
            "BROWSER",
            "ANALYST",
            "WRITER",
            "VERIFIER",
            "CRITIC",
            "SUMMARIZER",
        }
        assert {m.name for m in AgentType} == expected

    def test_string_values(self) -> None:
        assert AgentType.COORDINATOR == "coordinator"
        assert AgentType.PLANNER == "planner"
        assert AgentType.EXECUTOR == "executor"
        assert AgentType.RESEARCHER == "researcher"
        assert AgentType.CODER == "coder"
        assert AgentType.REVIEWER == "reviewer"
        assert AgentType.BROWSER == "browser"
        assert AgentType.ANALYST == "analyst"
        assert AgentType.WRITER == "writer"
        assert AgentType.VERIFIER == "verifier"
        assert AgentType.CRITIC == "critic"
        assert AgentType.SUMMARIZER == "summarizer"

    def test_inherits_str(self) -> None:
        assert isinstance(AgentType.CODER, str)

    def test_lookup_by_value(self) -> None:
        assert AgentType("coder") is AgentType.CODER
        assert AgentType("summarizer") is AgentType.SUMMARIZER


# ---------------------------------------------------------------------------
# AgentSpec helpers
# ---------------------------------------------------------------------------


def _make_spec(
    agent_type: AgentType = AgentType.EXECUTOR,
    capabilities: set[AgentCapability] | None = None,
    trigger_patterns: list[str] | None = None,
    required_context: list[str] | None = None,
    priority: int = 0,
) -> AgentSpec:
    return AgentSpec(
        agent_type=agent_type,
        name="Test Agent",
        description="Agent used in tests",
        capabilities=capabilities or set(),
        tools=[],
        system_prompt_template="You are a test agent.",
        priority=priority,
        trigger_patterns=trigger_patterns or [],
        required_context=required_context or [],
    )


# ---------------------------------------------------------------------------
# AgentSpec.matches_task
# ---------------------------------------------------------------------------


class TestAgentSpecMatchesTask:
    def test_no_patterns_no_capabilities_returns_zero_with_zero_priority(self) -> None:
        spec = _make_spec()
        score = spec.matches_task("do something unrelated", {})
        assert score == 0.0

    def test_trigger_pattern_match_adds_score(self) -> None:
        spec = _make_spec(trigger_patterns=[r"research"])
        score = spec.matches_task("Please research this topic", {})
        assert score > 0.0

    def test_trigger_pattern_adds_exactly_0_3(self) -> None:
        spec = _make_spec(trigger_patterns=[r"research"])
        score = spec.matches_task("research this topic", {})
        # priority=0, no context, no capabilities → only pattern contributes 0.3
        assert score == pytest.approx(0.3)

    def test_trigger_pattern_case_insensitive(self) -> None:
        spec = _make_spec(trigger_patterns=[r"research"])
        score_lower = spec.matches_task("research something", {})
        score_upper = spec.matches_task("RESEARCH something", {})
        assert score_lower == score_upper

    def test_only_first_matching_pattern_counts(self) -> None:
        """Two matching patterns still only add 0.3 (break after first match)."""
        spec = _make_spec(trigger_patterns=[r"research", r"investigate"])
        score = spec.matches_task("research and investigate", {})
        assert score == pytest.approx(0.3)

    def test_required_context_full_match_adds_0_2(self) -> None:
        spec = _make_spec(required_context=["lang", "domain"])
        score = spec.matches_task("do a task", {"lang": "python", "domain": "ml"})
        assert score == pytest.approx(0.2)

    def test_required_context_partial_match_scales(self) -> None:
        spec = _make_spec(required_context=["lang", "domain"])
        score = spec.matches_task("do a task", {"lang": "python"})
        # 1/2 keys present → 0.5 * 0.2 = 0.1
        assert score == pytest.approx(0.1)

    def test_required_context_no_match_adds_zero(self) -> None:
        spec = _make_spec(required_context=["lang"])
        score = spec.matches_task("do a task", {})
        assert score == 0.0

    def test_empty_required_context_adds_zero(self) -> None:
        spec = _make_spec(required_context=[])
        score = spec.matches_task("do a task", {"lang": "python"})
        # required_context is falsy → no context branch entered
        assert score == 0.0

    def test_priority_contributes_capped_at_0_3(self) -> None:
        spec_low = _make_spec(priority=0)
        spec_high = _make_spec(priority=30)
        score_low = spec_low.matches_task("unrelated", {})
        score_high = spec_high.matches_task("unrelated", {})
        assert score_high > score_low
        # priority 30 → min(30/100, 0.3) = 0.3
        assert score_high == pytest.approx(0.3)

    def test_priority_capped_at_0_3_even_when_very_high(self) -> None:
        spec = _make_spec(priority=999)
        score = spec.matches_task("unrelated", {})
        # Only priority contributes: min(999/100, 0.3) = 0.3
        assert score == pytest.approx(0.3)

    def test_capability_keyword_match_adds_0_1(self) -> None:
        spec = _make_spec(capabilities={AgentCapability.CODE_WRITING})
        score = spec.matches_task("write a function", {})
        # capability keyword "write" matches → +0.1
        assert score == pytest.approx(0.1)

    def test_capability_keyword_match_case_insensitive(self) -> None:
        spec = _make_spec(capabilities={AgentCapability.CODE_WRITING})
        score_lower = spec.matches_task("write a function", {})
        score_upper = spec.matches_task("WRITE a function", {})
        assert score_lower == score_upper

    def test_only_one_keyword_per_capability_counts(self) -> None:
        """Multiple keywords for same capability: only one +0.1 added (break after first)."""
        spec = _make_spec(capabilities={AgentCapability.CODE_WRITING})
        # "code" and "implement" and "write" are all keywords for CODE_WRITING
        score = spec.matches_task("write code and implement a class", {})
        # Still only adds 0.1 for that one capability
        assert score == pytest.approx(0.1)

    def test_multiple_capabilities_each_add_0_1(self) -> None:
        spec = _make_spec(capabilities={AgentCapability.WEB_SEARCH, AgentCapability.SUMMARIZATION})
        # "search" triggers WEB_SEARCH, "summarize" triggers SUMMARIZATION
        score = spec.matches_task("search and summarize the results", {})
        assert score == pytest.approx(0.2)

    def test_capability_not_in_spec_does_not_contribute(self) -> None:
        spec = _make_spec(capabilities={AgentCapability.PLANNING})
        # "search" is a keyword for WEB_SEARCH which is not in the spec's capabilities
        score = spec.matches_task("search for something", {})
        assert score == 0.0

    def test_score_capped_at_1_0(self) -> None:
        """A spec tuned to score above 1.0 is capped."""
        spec = _make_spec(
            capabilities={
                AgentCapability.CODE_WRITING,
                AgentCapability.CODE_REVIEW,
                AgentCapability.CODE_EXECUTION,
                AgentCapability.WEB_SEARCH,
                AgentCapability.RESEARCH,
                AgentCapability.SUMMARIZATION,
                AgentCapability.VERIFICATION,
            },
            trigger_patterns=[r"research"],
            required_context=["a", "b"],
            priority=30,
        )
        context = {"a": 1, "b": 2}
        score = spec.matches_task("research, verify code, search, run code, write code, summarize, check bugs", context)
        assert score == pytest.approx(1.0)

    def test_invalid_regex_does_not_raise(self) -> None:
        spec = _make_spec(trigger_patterns=[r"[invalid(regex"])
        # Should not raise; invalid pattern is logged and skipped
        score = spec.matches_task("any description", {})
        assert isinstance(score, float)

    def test_invalid_regex_alongside_valid_pattern(self) -> None:
        spec = _make_spec(trigger_patterns=[r"[invalid", r"research"])
        score = spec.matches_task("research something", {})
        # Valid pattern "research" matches → 0.3
        assert score == pytest.approx(0.3)

    def test_no_match_returns_low_score(self) -> None:
        spec = _make_spec(
            capabilities={AgentCapability.RESEARCH},
            trigger_patterns=[r"research"],
        )
        score = spec.matches_task("bake a cake", {})
        assert score == 0.0

    def test_combined_pattern_context_capability_accumulate(self) -> None:
        spec = _make_spec(
            capabilities={AgentCapability.WEB_SEARCH},
            trigger_patterns=[r"find"],
            required_context=["topic"],
            priority=10,
        )
        score = spec.matches_task("find the best option", {"topic": "ai"})
        # pattern: 0.3 + context (1/1)*0.2: 0.2 + priority (10/100=0.1): 0.1 + capability "search" keyword: 0.1 = 0.7
        assert score == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def _empty_registry(self) -> AgentRegistry:
        """Return an AgentRegistry with no registered agents."""
        reg = AgentRegistry.__new__(AgentRegistry)
        reg._agents = {}
        return reg

    def test_default_registry_registers_expected_agents(self) -> None:
        reg = AgentRegistry()
        registered_types = {spec.agent_type for spec in reg.get_all()}
        expected_types = {
            AgentType.COORDINATOR,
            AgentType.RESEARCHER,
            AgentType.CODER,
            AgentType.REVIEWER,
            AgentType.BROWSER,
            AgentType.WRITER,
            AgentType.ANALYST,
            AgentType.VERIFIER,
            AgentType.SUMMARIZER,
        }
        assert expected_types.issubset(registered_types)

    def test_register_and_get(self) -> None:
        reg = self._empty_registry()
        spec = _make_spec(agent_type=AgentType.PLANNER)
        reg.register(spec)
        result = reg.get(AgentType.PLANNER)
        assert result is spec

    def test_get_unregistered_returns_none(self) -> None:
        reg = self._empty_registry()
        assert reg.get(AgentType.CRITIC) is None

    def test_register_overwrites_existing(self) -> None:
        reg = self._empty_registry()
        spec_a = _make_spec(agent_type=AgentType.PLANNER, priority=10)
        spec_b = _make_spec(agent_type=AgentType.PLANNER, priority=99)
        reg.register(spec_a)
        reg.register(spec_b)
        assert reg.get(AgentType.PLANNER) is spec_b

    def test_list_all_returns_all_registered(self) -> None:
        reg = self._empty_registry()
        spec_a = _make_spec(agent_type=AgentType.PLANNER)
        spec_b = _make_spec(agent_type=AgentType.CRITIC)
        reg.register(spec_a)
        reg.register(spec_b)
        all_specs = reg.get_all()
        assert len(all_specs) == 2
        assert spec_a in all_specs
        assert spec_b in all_specs

    def test_list_all_empty_registry(self) -> None:
        reg = self._empty_registry()
        assert reg.get_all() == []

    def test_select_for_task_returns_best_match_first(self) -> None:
        reg = self._empty_registry()
        low = _make_spec(agent_type=AgentType.PLANNER, trigger_patterns=[], priority=0)
        high = _make_spec(
            agent_type=AgentType.CODER,
            trigger_patterns=[r"code"],
            capabilities={AgentCapability.CODE_WRITING},
            priority=30,
        )
        reg.register(low)
        reg.register(high)
        results = reg.select_for_task("write some code", {})
        assert results[0] is high

    def test_select_for_task_empty_registry_returns_empty_list(self) -> None:
        reg = self._empty_registry()
        results = reg.select_for_task("do anything", {})
        assert results == []

    def test_select_for_task_no_match_returns_empty_list(self) -> None:
        reg = self._empty_registry()
        spec = _make_spec(agent_type=AgentType.PLANNER, trigger_patterns=[r"research"], priority=0)
        reg.register(spec)
        results = reg.select_for_task("bake a cake", {})
        assert results == []

    def test_select_for_task_excludes_specified_agent_types(self) -> None:
        reg = self._empty_registry()
        spec = _make_spec(
            agent_type=AgentType.RESEARCHER,
            trigger_patterns=[r"research"],
            priority=50,
        )
        reg.register(spec)
        results = reg.select_for_task("research something", {}, exclude={AgentType.RESEARCHER})
        assert results == []

    def test_select_for_task_filters_by_required_capabilities(self) -> None:
        reg = self._empty_registry()
        capable = _make_spec(
            agent_type=AgentType.CODER,
            capabilities={AgentCapability.CODE_WRITING, AgentCapability.CODE_EXECUTION},
            trigger_patterns=[r"code"],
            priority=50,
        )
        incapable = _make_spec(
            agent_type=AgentType.WRITER,
            capabilities={AgentCapability.CREATIVE},
            trigger_patterns=[r"code"],
            priority=50,
        )
        reg.register(capable)
        reg.register(incapable)
        results = reg.select_for_task(
            "write and run code",
            {},
            required_capabilities={AgentCapability.CODE_EXECUTION},
        )
        types_in_results = {s.agent_type for s in results}
        assert AgentType.CODER in types_in_results
        assert AgentType.WRITER not in types_in_results

    def test_get_by_capability_returns_matching_specs(self) -> None:
        reg = self._empty_registry()
        spec_a = _make_spec(
            agent_type=AgentType.CODER,
            capabilities={AgentCapability.CODE_WRITING},
        )
        spec_b = _make_spec(
            agent_type=AgentType.WRITER,
            capabilities={AgentCapability.CREATIVE},
        )
        reg.register(spec_a)
        reg.register(spec_b)
        results = reg.get_by_capability(AgentCapability.CODE_WRITING)
        assert spec_a in results
        assert spec_b not in results

    def test_get_by_capability_no_match_returns_empty(self) -> None:
        reg = self._empty_registry()
        spec = _make_spec(
            agent_type=AgentType.WRITER,
            capabilities={AgentCapability.CREATIVE},
        )
        reg.register(spec)
        assert reg.get_by_capability(AgentCapability.VERIFICATION) == []

    def test_get_agent_registry_returns_singleton(self) -> None:
        """get_agent_registry() always returns the same instance."""
        reg_a = get_agent_registry()
        reg_b = get_agent_registry()
        assert reg_a is reg_b

    def test_get_agent_registry_is_agent_registry_instance(self) -> None:
        assert isinstance(get_agent_registry(), AgentRegistry)
