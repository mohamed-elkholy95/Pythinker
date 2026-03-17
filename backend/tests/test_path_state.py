"""
Tests for Tree-of-Thoughts path state models and complexity analyzer.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.path_state import (
    BranchingDecision,
    ComplexityAnalysis,
    PathMetrics,
    PathScoreWeights,
    PathState,
    PathStatus,
    TaskComplexity,
    TreeOfThoughtsConfig,
)
from app.domain.services.flows.complexity_analyzer import TaskComplexityAnalyzer


class TestPathMetrics:
    """Tests for PathMetrics dataclass"""

    def test_default_initialization(self):
        """Test default metrics initialization"""
        metrics = PathMetrics()
        assert metrics.steps_completed == 0
        assert metrics.errors_encountered == 0
        assert metrics.average_confidence == 0.5  # Default when empty

    def test_average_confidence(self):
        """Test average confidence calculation"""
        metrics = PathMetrics()
        metrics.confidence_scores = [0.8, 0.9, 0.7]
        assert abs(metrics.average_confidence - 0.8) < 0.01

    def test_error_rate(self):
        """Test error rate calculation"""
        metrics = PathMetrics(steps_completed=7, errors_encountered=3)
        assert abs(metrics.error_rate - 0.3) < 0.01

    def test_error_rate_zero(self):
        """Test error rate with no attempts"""
        metrics = PathMetrics()
        assert metrics.error_rate == 0.0


class TestPathState:
    """Tests for PathState dataclass"""

    def test_default_initialization(self):
        """Test default path state initialization"""
        path = PathState(description="Test path", strategy="Strategy 1")
        assert path.status == PathStatus.CREATED
        assert path.score == 0.0
        assert path.id is not None

    def test_start(self):
        """Test starting a path"""
        path = PathState(description="Test")
        path.start()

        assert path.status == PathStatus.EXPLORING
        assert path.started_at is not None

    def test_complete(self):
        """Test completing a path"""
        path = PathState(description="Test")
        path.start()
        path.complete("Final result")

        assert path.status == PathStatus.COMPLETED
        assert path.final_result == "Final result"
        assert path.completed_at is not None

    def test_fail(self):
        """Test failing a path"""
        path = PathState(description="Test")
        path.start()
        path.fail("Error occurred")

        assert path.status == PathStatus.FAILED
        assert "Failed:" in path.final_result

    def test_abandon(self):
        """Test abandoning a path"""
        path = PathState(description="Test")
        path.start()
        path.abandon("Score too low")

        assert path.status == PathStatus.ABANDONED
        assert "Abandoned:" in path.final_result

    def test_select(self):
        """Test selecting a path as winner"""
        path = PathState(description="Test")
        path.complete("Result")
        path.select()

        assert path.status == PathStatus.SELECTED

    def test_add_result(self):
        """Test adding intermediate result"""
        path = PathState(description="Test")
        path.start()
        path.add_result(step_id="1", result="Some data", confidence=0.85)

        assert len(path.intermediate_results) == 1
        assert path.intermediate_results[0]["step_id"] == "1"
        assert path.metrics.steps_completed == 1
        assert 0.85 in path.metrics.confidence_scores

    def test_record_error(self):
        """Test recording an error"""
        path = PathState(description="Test")
        path.start()
        path.record_error()

        assert path.metrics.errors_encountered == 1

    def test_to_dict(self):
        """Test dictionary conversion"""
        path = PathState(description="Test", strategy="Strategy 1")
        path.start()
        path.score = 0.75

        result = path.to_dict()

        assert result["description"] == "Test"
        assert result["strategy"] == "Strategy 1"
        assert result["score"] == 0.75
        assert result["status"] == "exploring"


class TestComplexityAnalysis:
    """Tests for ComplexityAnalysis dataclass"""

    def test_simple_linear(self):
        """Test simple complexity with linear branching"""
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE,
            confidence=0.9,
            branching_decision=BranchingDecision.LINEAR,
            estimated_steps=2,
        )
        assert analysis.should_branch() is False

    def test_complex_with_branching(self):
        """Test complex complexity with branching"""
        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["Approach A", "Approach B"],
            estimated_steps=7,
        )
        assert analysis.should_branch() is True
        assert len(analysis.suggested_strategies) == 2


class TestPathScoreWeights:
    """Tests for PathScoreWeights model"""

    def test_default_weights(self):
        """Test default weight values"""
        weights = PathScoreWeights()
        assert weights.result_quality == 0.4
        assert weights.confidence == 0.25
        assert weights.efficiency == 0.2
        assert weights.error_penalty == 0.15

    def test_custom_weights(self):
        """Test custom weight values"""
        weights = PathScoreWeights(result_quality=0.5, confidence=0.2, efficiency=0.2, error_penalty=0.1)
        assert weights.result_quality == 0.5


class TestTreeOfThoughtsConfig:
    """Tests for TreeOfThoughtsConfig"""

    def test_default_config(self):
        """Test default configuration"""
        config = TreeOfThoughtsConfig()
        assert config.enabled is True
        assert config.max_paths == 3
        assert config.min_paths == 2
        assert config.auto_abandon_threshold == 0.3

    def test_custom_config(self):
        """Test custom configuration"""
        config = TreeOfThoughtsConfig(enabled=False, max_paths=5, auto_abandon_threshold=0.4)
        assert config.enabled is False
        assert config.max_paths == 5


class TestTaskComplexityAnalyzer:
    """Tests for TaskComplexityAnalyzer"""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM"""
        llm = MagicMock()
        llm.ask = AsyncMock(return_value={"content": '{"complexity": "moderate", "confidence": 0.8}'})
        return llm

    @pytest.fixture
    def mock_json_parser(self):
        """Create mock JSON parser"""
        parser = MagicMock()
        parser.parse = AsyncMock(
            return_value={
                "complexity": "moderate",
                "confidence": 0.8,
                "branching_decision": "linear",
                "suggested_strategies": [],
                "reasoning": "Standard task",
                "estimated_steps": 4,
            }
        )
        return parser

    def test_quick_analyze_simple(self, mock_llm, mock_json_parser):
        """Test quick analysis detects simple tasks"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = analyzer.quick_analyze("read the file config.yaml")

        assert result is not None
        assert result.complexity == TaskComplexity.SIMPLE
        assert result.branching_decision == BranchingDecision.LINEAR

    def test_quick_analyze_research(self, mock_llm, mock_json_parser):
        """Test quick analysis detects research tasks.

        Uses a task that matches RESEARCH_PATTERNS (checked before COMPLEX_PATTERNS).
        RESEARCH_PATTERNS includes: "find the best", "compare options", "research ", etc.
        """
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        # Use "find the best" which is in RESEARCH_PATTERNS
        result = analyzer.quick_analyze("find the best JavaScript frameworks for React alternatives")

        assert result is not None
        assert result.complexity == TaskComplexity.RESEARCH
        assert result.branching_decision == BranchingDecision.BRANCH_STRATEGIES

    def test_quick_analyze_complex(self, mock_llm, mock_json_parser):
        """Test quick analysis detects complex tasks"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = analyzer.quick_analyze("design a system architecture for microservices")

        assert result is not None
        assert result.complexity == TaskComplexity.COMPLEX
        assert result.branching_decision == BranchingDecision.BRANCH_STRATEGIES

    def test_quick_analyze_moderate(self, mock_llm, mock_json_parser):
        """Test quick analysis detects moderate tasks"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = analyzer.quick_analyze("create a simple Python script")

        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE
        assert result.branching_decision == BranchingDecision.LINEAR

    def test_quick_analyze_ambiguous(self, mock_llm, mock_json_parser):
        """Test quick analysis returns None for ambiguous tasks"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = analyzer.quick_analyze("work on the project")

        # Should return None for ambiguous tasks
        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_with_llm(self, mock_llm, mock_json_parser):
        """Test full analysis with LLM"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = await analyzer.analyze(
            task="work on the project", context="Backend development", tools_summary="shell, file, browser"
        )

        assert result is not None
        assert result.complexity == TaskComplexity.MODERATE

    @pytest.mark.asyncio
    async def test_analyze_error_fallback(self, mock_llm, mock_json_parser):
        """Test analysis falls back on error"""
        mock_json_parser.parse = AsyncMock(side_effect=Exception("Parse error"))

        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        result = await analyzer.analyze("work on project")

        # Should default to MODERATE/LINEAR
        assert result.complexity == TaskComplexity.MODERATE
        assert result.branching_decision == BranchingDecision.LINEAR
        assert result.confidence == 0.5

    def test_should_use_tot_disabled(self, mock_llm, mock_json_parser):
        """Test ToT not used when disabled"""
        config = TreeOfThoughtsConfig(enabled=False)
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser, config=config)

        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX, confidence=0.9, branching_decision=BranchingDecision.BRANCH_STRATEGIES
        )

        assert analyzer.should_use_tot(analysis) is False

    def test_should_use_tot_simple_task(self, mock_llm, mock_json_parser):
        """Test ToT not used for simple tasks"""
        config = TreeOfThoughtsConfig(enabled=True, complexity_threshold=TaskComplexity.COMPLEX)
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser, config=config)

        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.SIMPLE, confidence=0.9, branching_decision=BranchingDecision.LINEAR
        )

        assert analyzer.should_use_tot(analysis) is False

    def test_should_use_tot_complex_task(self, mock_llm, mock_json_parser):
        """Test ToT used for complex tasks with branching"""
        config = TreeOfThoughtsConfig(enabled=True, complexity_threshold=TaskComplexity.COMPLEX)
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser, config=config)

        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX, confidence=0.9, branching_decision=BranchingDecision.BRANCH_STRATEGIES
        )

        assert analyzer.should_use_tot(analysis) is True

    def test_get_strategy_plans(self, mock_llm, mock_json_parser):
        """Test generating strategy plans from analysis"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.COMPLEX,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=["Approach A", "Approach B", "Approach C"],
            estimated_steps=5,
        )

        plans = analyzer.get_strategy_plans(analysis, max_strategies=2)

        assert len(plans) == 2
        assert plans[0]["description"] == "Approach A"
        assert plans[1]["description"] == "Approach B"

    def test_get_strategy_plans_defaults(self, mock_llm, mock_json_parser):
        """Test default strategies when none suggested"""
        analyzer = TaskComplexityAnalyzer(llm=mock_llm, json_parser=mock_json_parser)

        analysis = ComplexityAnalysis(
            complexity=TaskComplexity.RESEARCH,
            confidence=0.8,
            branching_decision=BranchingDecision.BRANCH_STRATEGIES,
            suggested_strategies=[],  # Empty
            estimated_steps=5,
        )

        plans = analyzer.get_strategy_plans(analysis)

        assert len(plans) >= 2
        # Should have default research strategies
        assert any("search" in p["description"].lower() for p in plans)
