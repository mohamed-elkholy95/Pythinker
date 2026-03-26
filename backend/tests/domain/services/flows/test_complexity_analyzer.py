"""Tests for TaskComplexityAnalyzer heuristic methods.

Covers quick_analyze, should_use_tot, and get_strategy_plans
without requiring any LLM calls.
"""

from unittest.mock import MagicMock

import pytest

from app.domain.models.path_state import (
    BranchingDecision,
    ComplexityAnalysis,
    TaskComplexity,
    TreeOfThoughtsConfig,
)
from app.domain.services.flows.complexity_analyzer import (
    COMPLEX_PATTERNS,
    MODERATE_PATTERNS,
    RESEARCH_PATTERNS,
    SIMPLE_PATTERNS,
    TaskComplexityAnalyzer,
)


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_json_parser():
    return MagicMock()


@pytest.fixture
def analyzer(mock_llm, mock_json_parser):
    return TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)


@pytest.fixture
def analyzer_disabled(mock_llm, mock_json_parser):
    config = TreeOfThoughtsConfig(enabled=False)
    return TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser, config=config)


@pytest.fixture
def analyzer_moderate_threshold(mock_llm, mock_json_parser):
    config = TreeOfThoughtsConfig(complexity_threshold=TaskComplexity.MODERATE)
    return TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser, config=config)


# ─────────────────────────────────────────────────────────────
# Pattern constants
# ─────────────────────────────────────────────────────────────


class TestPatterns:
    def test_simple_patterns_not_empty(self):
        assert len(SIMPLE_PATTERNS) > 0

    def test_moderate_patterns_not_empty(self):
        assert len(MODERATE_PATTERNS) > 0

    def test_complex_patterns_not_empty(self):
        assert len(COMPLEX_PATTERNS) > 0

    def test_research_patterns_not_empty(self):
        assert len(RESEARCH_PATTERNS) > 0


# ─────────────────────────────────────────────────────────────
# quick_analyze
# ─────────────────────────────────────────────────────────────


class TestQuickAnalyze:
    def test_simple_read_task(self, analyzer):
        result = analyzer.quick_analyze("read this file")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE
        assert result.branching_decision == BranchingDecision.LINEAR
        assert result.confidence >= 0.8

    def test_simple_show_task(self, analyzer):
        result = analyzer.quick_analyze("show me the config")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE

    def test_simple_list_task(self, analyzer):
        result = analyzer.quick_analyze("list all files")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE

    def test_simple_get_task(self, analyzer):
        result = analyzer.quick_analyze("get the latest version")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE

    def test_simple_what_is(self, analyzer):
        result = analyzer.quick_analyze("what is python")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE

    def test_simple_explain(self, analyzer):
        result = analyzer.quick_analyze("explain decorators")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE

    def test_simple_only_short_tasks(self, analyzer):
        # Simple patterns only match if < 15 words
        long_task = (
            "read this file and then process it and then do a lot of other things with the output and more stuff"
        )
        result = analyzer.quick_analyze(long_task)
        # Should NOT match as simple because it's too long
        assert result is None or result.complexity != TaskComplexity.SIMPLE

    def test_research_find_the_best(self, analyzer):
        result = analyzer.quick_analyze("find the best GPU for machine learning")
        assert result is not None
        assert result.complexity == TaskComplexity.RESEARCH
        assert result.branching_decision == BranchingDecision.BRANCH_STRATEGIES
        assert len(result.suggested_strategies) >= 2

    def test_research_compare_options(self, analyzer):
        result = analyzer.quick_analyze("compare options for cloud hosting")
        assert result is not None
        assert result.complexity == TaskComplexity.RESEARCH

    def test_research_investigate(self, analyzer):
        result = analyzer.quick_analyze("investigate the root cause of slow queries")
        assert result is not None
        assert result.complexity == TaskComplexity.RESEARCH

    def test_research_which_is_better(self, analyzer):
        result = analyzer.quick_analyze("which is better: React or Vue for this project?")
        assert result is not None
        assert result.complexity == TaskComplexity.RESEARCH

    def test_complex_compare(self, analyzer):
        result = analyzer.quick_analyze("compare React vs Vue performance benchmarks in detail")
        assert result is not None
        # Could be research or complex depending on pattern order
        assert result.complexity in (TaskComplexity.COMPLEX, TaskComplexity.RESEARCH)

    def test_complex_analyze(self, analyzer):
        result = analyzer.quick_analyze("analyze the system architecture for bottlenecks")
        assert result is not None
        assert result.complexity in (TaskComplexity.COMPLEX, TaskComplexity.RESEARCH)

    def test_complex_design(self, analyzer):
        result = analyzer.quick_analyze("design a scalable microservice architecture")
        assert result is not None
        assert result.complexity in (TaskComplexity.COMPLEX, TaskComplexity.RESEARCH)

    def test_complex_optimize(self, analyzer):
        result = analyzer.quick_analyze("optimize the database query performance")
        assert result is not None
        assert result.complexity in (TaskComplexity.COMPLEX, TaskComplexity.RESEARCH)

    def test_moderate_create(self, analyzer):
        result = analyzer.quick_analyze("create a new Python class for user management")
        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE
        assert result.branching_decision == BranchingDecision.LINEAR

    def test_moderate_write(self, analyzer):
        result = analyzer.quick_analyze("write a function to parse CSV files")
        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE

    def test_moderate_fix(self, analyzer):
        result = analyzer.quick_analyze("fix the broken login endpoint")
        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE

    def test_moderate_update(self, analyzer):
        result = analyzer.quick_analyze("update the API response format")
        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE

    def test_returns_none_for_ambiguous(self, analyzer):
        result = analyzer.quick_analyze("do something interesting with the data")
        assert result is None

    def test_estimated_steps_simple(self, analyzer):
        result = analyzer.quick_analyze("read this file")
        assert result is not None
        assert result.estimated_steps == 2

    def test_estimated_steps_research(self, analyzer):
        result = analyzer.quick_analyze("find the best tool for code review")
        assert result is not None
        assert result.estimated_steps == 5

    def test_estimated_steps_moderate(self, analyzer):
        result = analyzer.quick_analyze("create a helper function")
        assert result is not None
        assert result.estimated_steps == 4

    def test_case_insensitive(self, analyzer):
        result = analyzer.quick_analyze("READ THIS FILE")
        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE


# ─────────────────────────────────────────────────────────────
# should_use_tot
# ─────────────────────────────────────────────────────────────


class TestShouldUseTot:
    def test_disabled_config_always_false(self, analyzer_disabled):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.RESEARCH,
            confidence=0.9,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["a", "b"],
        )
        assert analyzer_disabled.should_use_tot(analysis) is False

    def test_simple_task_false(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            branching_decision=BranchingDecision.LINEAR,
        )
        assert analyzer.should_use_tot(analysis) is False

    def test_moderate_below_threshold(self, analyzer):
        # Default threshold is COMPLEX
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.MODERATE,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert analyzer.should_use_tot(analysis) is False

    def test_complex_with_branching_true(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert analyzer.should_use_tot(analysis) is True

    def test_complex_linear_false(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.LINEAR,
        )
        assert analyzer.should_use_tot(analysis) is False

    def test_research_with_branching_true(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.RESEARCH,
            confidence=0.9,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert analyzer.should_use_tot(analysis) is True

    def test_moderate_with_lower_threshold(self, analyzer_moderate_threshold):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.MODERATE,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert analyzer_moderate_threshold.should_use_tot(analysis) is True

    def test_branch_verification(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.7,
            branching_decision=BranchingDecision.BRANCH_VERIFICATION,
        )
        assert analyzer.should_use_tot(analysis) is True

    def test_branch_parameters(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.7,
            branching_decision=BranchingDecision.BRANCH_PARAMETERS,
        )
        assert analyzer.should_use_tot(analysis) is True


# ─────────────────────────────────────────────────────────────
# get_strategy_plans
# ─────────────────────────────────────────────────────────────


class TestGetStrategyPlans:
    def test_returns_provided_strategies(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["Web scraping", "API integration", "Manual parsing"],
            estimated_steps=6,
        )
        plans = analyzer.get_strategy_plans(analysis)
        assert len(plans) == 3
        assert plans[0]["strategy_id"] == 1
        assert plans[0]["description"] == "Web scraping"
        assert plans[2]["description"] == "Manual parsing"

    def test_respects_max_strategies(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["A", "B", "C", "D", "E"],
            estimated_steps=5,
        )
        plans = analyzer.get_strategy_plans(analysis, max_strategies=2)
        assert len(plans) == 2

    def test_respects_config_max_paths(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["A", "B", "C", "D", "E"],
            estimated_steps=5,
        )
        # Default config max_paths = 3
        plans = analyzer.get_strategy_plans(analysis)
        assert len(plans) == 3

    def test_default_strategies_for_research(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.RESEARCH,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=[],
            estimated_steps=5,
        )
        plans = analyzer.get_strategy_plans(analysis)
        assert len(plans) == 2
        assert "web search" in plans[0]["description"].lower() or "search" in plans[0]["description"].lower()

    def test_default_strategies_for_complex(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=[],
            estimated_steps=7,
        )
        plans = analyzer.get_strategy_plans(analysis)
        assert len(plans) == 2

    def test_default_strategies_for_simple(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            branching_decision=BranchingDecision.LINEAR,
            suggested_strategies=[],
            estimated_steps=2,
        )
        plans = analyzer.get_strategy_plans(analysis)
        assert len(plans) == 1
        assert "linear" in plans[0]["description"].lower()

    def test_strategy_plan_structure(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["Strategy A"],
            estimated_steps=5,
        )
        plans = analyzer.get_strategy_plans(analysis)
        plan = plans[0]
        assert "strategy_id" in plan
        assert "description" in plan
        assert "estimated_steps" in plan
        assert plan["estimated_steps"] == 5

    def test_strategy_ids_sequential(self, analyzer):
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["A", "B", "C"],
            estimated_steps=5,
        )
        plans = analyzer.get_strategy_plans(analysis)
        assert [p["strategy_id"] for p in plans] == [1, 2, 3]


# ─────────────────────────────────────────────────────────────
# ComplexityAnalysis.should_branch
# ─────────────────────────────────────────────────────────────


class TestComplexityAnalysisShouldBranch:
    def test_linear_should_not_branch(self):
        a = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            branching_decision=BranchingDecision.LINEAR,
        )
        assert a.should_branch() is False

    def test_branch_strategies_should_branch(self):
        a = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
        )
        assert a.should_branch() is True

    def test_branch_parameters_should_branch(self):
        a = ComplexityAnalysis(
            complexity=TaskComplexity.MODERATE,
            confidence=0.7,
            branching_decision=BranchingDecision.BRANCH_PARAMETERS,
        )
        assert a.should_branch() is True

    def test_branch_verification_should_branch(self):
        a = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.6,
            branching_decision=BranchingDecision.BRANCH_VERIFICATION,
        )
        assert a.should_branch() is True
