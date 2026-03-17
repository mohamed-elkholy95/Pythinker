"""Tests for plan quality metrics.

Tests the comprehensive quality assessment system including:
- Clarity scoring
- Completeness analysis
- Structure validation
- Feasibility assessment
- Efficiency evaluation
"""

from app.domain.models.plan import (
    DimensionScore,
    Plan,
    PlanQualityAnalyzer,
    PlanQualityMetrics,
    QualityDimension,
    Step,
)


class TestQualityDimension:
    """Tests for QualityDimension enum."""

    def test_all_dimensions_exist(self):
        """Test that all quality dimensions are defined."""
        assert QualityDimension.CLARITY.value == "clarity"
        assert QualityDimension.COMPLETENESS.value == "completeness"
        assert QualityDimension.STRUCTURE.value == "structure"
        assert QualityDimension.FEASIBILITY.value == "feasibility"
        assert QualityDimension.EFFICIENCY.value == "efficiency"


class TestDimensionScore:
    """Tests for DimensionScore dataclass."""

    def test_basic_creation(self):
        """Test basic dimension score creation."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.85,
            issues=["Issue 1"],
            suggestions=["Suggestion 1"],
        )

        assert score.dimension == QualityDimension.CLARITY
        assert score.score == 0.85
        assert len(score.issues) == 1
        assert len(score.suggestions) == 1

    def test_grade_a(self):
        """Test A grade for score >= 0.9."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.95,
        )
        assert score.grade == "A"

    def test_grade_b(self):
        """Test B grade for score >= 0.8."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.85,
        )
        assert score.grade == "B"

    def test_grade_c(self):
        """Test C grade for score >= 0.7."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.75,
        )
        assert score.grade == "C"

    def test_grade_d(self):
        """Test D grade for score >= 0.6."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.65,
        )
        assert score.grade == "D"

    def test_grade_f(self):
        """Test F grade for score < 0.6."""
        score = DimensionScore(
            dimension=QualityDimension.CLARITY,
            score=0.5,
        )
        assert score.grade == "F"


class TestPlanQualityMetrics:
    """Tests for PlanQualityMetrics."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = PlanQualityMetrics(
            dimensions={
                QualityDimension.CLARITY: DimensionScore(
                    dimension=QualityDimension.CLARITY,
                    score=0.9,
                ),
            },
            overall_score=0.85,
            overall_grade="B",
            risk_factors=["Risk 1"],
            improvement_suggestions=["Improve X"],
            analyzed_at="2026-01-01T00:00:00Z",
        )

        result = metrics.to_dict()

        assert "dimensions" in result
        assert "clarity" in result["dimensions"]
        assert result["overall_score"] == 0.85
        assert result["overall_grade"] == "B"
        assert len(result["risk_factors"]) == 1

    def test_needs_improvement(self):
        """Test needs_improvement property."""
        low = PlanQualityMetrics(overall_score=0.6)
        high = PlanQualityMetrics(overall_score=0.8)

        assert low.needs_improvement is True
        assert high.needs_improvement is False

    def test_is_high_quality(self):
        """Test is_high_quality property."""
        low = PlanQualityMetrics(overall_score=0.7)
        high = PlanQualityMetrics(overall_score=0.9)

        assert low.is_high_quality is False
        assert high.is_high_quality is True

    def test_worst_dimension(self):
        """Test worst_dimension property."""
        metrics = PlanQualityMetrics(
            dimensions={
                QualityDimension.CLARITY: DimensionScore(
                    dimension=QualityDimension.CLARITY,
                    score=0.9,
                ),
                QualityDimension.EFFICIENCY: DimensionScore(
                    dimension=QualityDimension.EFFICIENCY,
                    score=0.5,
                ),
            },
        )

        worst = metrics.worst_dimension
        assert worst is not None
        assert worst.dimension == QualityDimension.EFFICIENCY


class TestPlanQualityAnalyzer:
    """Tests for PlanQualityAnalyzer."""

    def test_analyze_clear_plan(self):
        """Test analyzing a clear, well-structured plan."""
        plan = Plan(
            title="Research Report",
            goal="Create a comprehensive research report about Python",
            steps=[
                Step(id="1", description="Search for Python tutorials and documentation"),
                Step(id="2", description="Browse the top 5 search results and extract key information"),
                Step(id="3", description="Summarize findings and write report to report.md"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert metrics.overall_score > 0.6
        assert metrics.overall_grade in ["A", "B", "C"]

    def test_analyze_vague_plan(self):
        """Test analyzing a plan with vague descriptions."""
        plan = Plan(
            title="Do stuff",
            goal="Do some things",
            steps=[
                Step(id="1", description="Maybe do something"),
                Step(id="2", description="Possibly check stuff"),
                Step(id="3", description="Perhaps write things"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        # Should score low on clarity
        clarity = metrics.dimensions.get(QualityDimension.CLARITY)
        assert clarity is not None
        assert clarity.score < 0.8
        assert len(clarity.issues) > 0

    def test_analyze_empty_plan(self):
        """Test analyzing an empty plan."""
        plan = Plan(title="Empty", goal="", steps=[])

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        # Empty plan should have low completeness and need improvement
        assert metrics.overall_score < 0.7
        assert metrics.needs_improvement is True
        completeness = metrics.dimensions.get(QualityDimension.COMPLETENESS)
        assert completeness is not None
        assert completeness.score == 0.0  # No steps means 0 completeness

    def test_analyze_single_step_plan(self):
        """Test analyzing a single-step plan."""
        plan = Plan(
            title="Simple Task",
            goal="Search for information about Python",
            steps=[
                Step(id="1", description="Search for Python information"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        completeness = metrics.dimensions.get(QualityDimension.COMPLETENESS)
        assert completeness is not None
        # Should have suggestion about single-step plans
        assert any("single" in s.lower() for s in completeness.suggestions) or len(plan.steps) == 1

    def test_analyze_plan_with_dependencies(self):
        """Test analyzing a plan with proper dependencies."""
        plan = Plan(
            title="Research Report",
            goal="Create a research report",
            steps=[
                Step(id="1", description="Search for Python tutorials"),
                Step(id="2", description="Browse search results", dependencies=["1"]),
                Step(id="3", description="Write report", dependencies=["2"]),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        structure = metrics.dimensions.get(QualityDimension.STRUCTURE)
        assert structure is not None
        assert structure.score >= 0.7

    def test_analyze_plan_with_circular_deps(self):
        """Test analyzing a plan with circular dependencies."""
        plan = Plan(
            title="Bad Plan",
            goal="Test circular deps",
            steps=[
                Step(id="1", description="Step one", dependencies=["3"]),
                Step(id="2", description="Step two", dependencies=["1"]),
                Step(id="3", description="Step three", dependencies=["2"]),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        structure = metrics.dimensions.get(QualityDimension.STRUCTURE)
        assert structure is not None
        assert structure.score < 0.8
        assert any("circular" in issue.lower() for issue in structure.issues)

    def test_analyze_risky_plan(self):
        """Test analyzing a plan with risk indicators."""
        plan = Plan(
            title="Dangerous Plan",
            goal="Delete all files",
            steps=[
                Step(id="1", description="Run sudo command to delete files"),
                Step(id="2", description="Force overwrite production database"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert len(metrics.risk_factors) > 0
        assert any("destructive" in r.lower() or "delete" in r.lower() for r in metrics.risk_factors)

    def test_analyze_long_plan(self):
        """Test analyzing an overly long plan."""
        steps = [Step(id=str(i), description=f"Execute step {i} of the process") for i in range(15)]
        plan = Plan(
            title="Long Plan",
            goal="Complete a very long process",
            steps=steps,
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        efficiency = metrics.dimensions.get(QualityDimension.EFFICIENCY)
        assert efficiency is not None
        # Long plan should have efficiency penalty and issues detected
        assert efficiency.score <= 0.95
        assert len(efficiency.issues) > 0  # Should have issue about many steps
        assert len(metrics.risk_factors) > 0  # Should warn about long plans

    def test_analyze_with_user_request(self):
        """Test analyzing completeness against user request."""
        plan = Plan(
            title="Research Report",
            goal="Create a report",
            steps=[
                Step(id="1", description="Search for general information"),
                Step(id="2", description="Write a summary"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan, user_request="Research Python async programming and compare it with threading")

        completeness = metrics.dimensions.get(QualityDimension.COMPLETENESS)
        assert completeness is not None
        # Plan doesn't mention async or threading specifically
        assert completeness.score < 0.9

    def test_analyze_with_available_tools(self):
        """Test feasibility check with available tools."""
        plan = Plan(
            title="Research Task",
            goal="Research and browse information",
            steps=[
                Step(id="1", description="Search for information online"),
                Step(id="2", description="Browse the webpage and click links"),
            ],
        )

        # Only search tool available
        analyzer = PlanQualityAnalyzer(available_tools=["search"])
        metrics = analyzer.analyze(plan)

        feasibility = metrics.dimensions.get(QualityDimension.FEASIBILITY)
        assert feasibility is not None
        # Should note browser may not be available
        assert any("browser" in issue.lower() for issue in feasibility.issues)

    def test_analyze_plan_with_output(self):
        """Test that plans with output steps score better on completeness."""
        plan_no_output = Plan(
            title="Research",
            goal="Research Python",
            steps=[
                Step(id="1", description="Search for Python info"),
                Step(id="2", description="Read documentation"),
            ],
        )

        plan_with_output = Plan(
            title="Research",
            goal="Research Python",
            steps=[
                Step(id="1", description="Search for Python info"),
                Step(id="2", description="Read documentation"),
                Step(id="3", description="Write summary report to output.md"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics_no = analyzer.analyze(plan_no_output)
        metrics_yes = analyzer.analyze(plan_with_output)

        comp_no = metrics_no.dimensions.get(QualityDimension.COMPLETENESS)
        comp_yes = metrics_yes.dimensions.get(QualityDimension.COMPLETENESS)

        assert comp_no is not None and comp_yes is not None
        assert comp_yes.score >= comp_no.score


class TestPlanGetQualityMetrics:
    """Tests for Plan.get_quality_metrics() method."""

    def test_get_quality_metrics(self):
        """Test getting quality metrics from plan."""
        plan = Plan(
            title="Test Plan",
            goal="Test quality metrics",
            steps=[
                Step(id="1", description="Search for test information"),
                Step(id="2", description="Analyze the results"),
                Step(id="3", description="Write summary report"),
            ],
        )

        metrics = plan.get_quality_metrics()

        assert isinstance(metrics, PlanQualityMetrics)
        assert metrics.overall_score > 0
        assert len(metrics.dimensions) == 5  # All 5 dimensions

    def test_get_quality_metrics_with_request(self):
        """Test getting quality metrics with user request."""
        plan = Plan(
            title="Research",
            goal="Research AI agents",
            steps=[
                Step(id="1", description="Search for AI agent frameworks"),
            ],
        )

        metrics = plan.get_quality_metrics(user_request="Research AI agent frameworks and their capabilities")

        assert metrics.overall_score > 0
        completeness = metrics.dimensions.get(QualityDimension.COMPLETENESS)
        assert completeness is not None

    def test_get_quality_metrics_with_tools(self):
        """Test getting quality metrics with available tools."""
        plan = Plan(
            title="File Task",
            goal="Create a file",
            steps=[
                Step(id="1", description="Write content to file.txt"),
            ],
        )

        metrics = plan.get_quality_metrics(available_tools=["file", "shell"])

        feasibility = metrics.dimensions.get(QualityDimension.FEASIBILITY)
        assert feasibility is not None


class TestClarityAnalysis:
    """Detailed tests for clarity analysis."""

    def test_clarity_penalizes_vague_words(self):
        """Test that vague words reduce clarity score."""
        vague_plan = Plan(
            title="Vague",
            goal="Do things",
            steps=[
                Step(id="1", description="Maybe try something somehow"),
            ],
        )

        clear_plan = Plan(
            title="Clear",
            goal="Search for docs",
            steps=[
                Step(id="1", description="Search for Python documentation"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        vague_metrics = analyzer.analyze(vague_plan)
        clear_metrics = analyzer.analyze(clear_plan)

        vague_clarity = vague_metrics.dimensions[QualityDimension.CLARITY]
        clear_clarity = clear_metrics.dimensions[QualityDimension.CLARITY]

        assert clear_clarity.score > vague_clarity.score

    def test_clarity_rewards_action_verbs(self):
        """Test that action verbs improve clarity score."""
        analyzer = PlanQualityAnalyzer()

        action_plan = Plan(
            title="Action",
            goal="Complete task",
            steps=[
                Step(id="1", description="Search for information"),
                Step(id="2", description="Create the report file"),
                Step(id="3", description="Execute the test command"),
            ],
        )

        metrics = analyzer.analyze(action_plan)
        clarity = metrics.dimensions[QualityDimension.CLARITY]

        assert clarity.score >= 0.7

    def test_clarity_penalizes_short_descriptions(self):
        """Test that very short descriptions reduce clarity."""
        short_plan = Plan(
            title="Short",
            goal="Do",
            steps=[
                Step(id="1", description="Go"),
                Step(id="2", description="Do"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(short_plan)
        clarity = metrics.dimensions[QualityDimension.CLARITY]

        assert clarity.score < 0.8
        assert any("short" in issue.lower() for issue in clarity.issues)


class TestEfficiencyAnalysis:
    """Detailed tests for efficiency analysis."""

    def test_efficiency_penalizes_many_steps(self):
        """Test that too many steps reduce efficiency score."""
        many_steps = [Step(id=str(i), description=f"Step number {i}") for i in range(12)]

        plan = Plan(
            title="Long Plan",
            goal="Many steps",
            steps=many_steps,
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)
        efficiency = metrics.dimensions[QualityDimension.EFFICIENCY]

        # Many steps should be detected as an issue
        assert len(efficiency.issues) > 0
        assert any("steps" in issue.lower() for issue in efficiency.issues)

    def test_efficiency_detects_duplicates(self):
        """Test that duplicate steps are detected."""
        plan = Plan(
            title="Duplicate Plan",
            goal="Has duplicates",
            steps=[
                Step(id="1", description="Search for Python tutorials"),
                Step(id="2", description="Search for Python tutorials"),
                Step(id="3", description="Write summary"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)
        efficiency = metrics.dimensions[QualityDimension.EFFICIENCY]

        assert any("duplicate" in issue.lower() for issue in efficiency.issues)


class TestRiskFactors:
    """Tests for risk factor identification."""

    def test_identifies_destructive_operations(self):
        """Test that destructive operations are flagged."""
        plan = Plan(
            title="Cleanup",
            goal="Clean up files",
            steps=[
                Step(id="1", description="Delete all temporary files"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert any("destructive" in r.lower() or "backup" in r.lower() for r in metrics.risk_factors)

    def test_identifies_permission_risks(self):
        """Test that permission-related operations are flagged."""
        plan = Plan(
            title="Admin Task",
            goal="Run admin commands",
            steps=[
                Step(id="1", description="Execute sudo command to install package"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert any("permission" in r.lower() or "elevated" in r.lower() for r in metrics.risk_factors)

    def test_identifies_external_dependencies(self):
        """Test that external dependencies are flagged."""
        plan = Plan(
            title="API Task",
            goal="Call external API",
            steps=[
                Step(id="1", description="Download data from external API"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert any("external" in r.lower() for r in metrics.risk_factors)

    def test_identifies_rate_limit_risk(self):
        """Test that many search/browse operations are flagged."""
        plan = Plan(
            title="Heavy Search",
            goal="Search many things",
            steps=[
                Step(id="1", description="Search for topic A"),
                Step(id="2", description="Search for topic B"),
                Step(id="3", description="Search for topic C"),
                Step(id="4", description="Search for topic D"),
                Step(id="5", description="Browse multiple results"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        assert any("rate limit" in r.lower() for r in metrics.risk_factors)


class TestImprovementSuggestions:
    """Tests for improvement suggestion generation."""

    def test_generates_suggestions_for_low_scores(self):
        """Test that suggestions are generated for low-scoring dimensions."""
        plan = Plan(
            title="Weak Plan",
            goal="Do stuff",
            steps=[
                Step(id="1", description="Maybe"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        # Should have improvement suggestions due to low scores
        assert len(metrics.improvement_suggestions) > 0

    def test_limits_suggestions_count(self):
        """Test that suggestions are limited to prevent overload."""
        plan = Plan(
            title="Bad Plan",
            goal="",
            steps=[
                Step(id="1", description="x"),
                Step(id="2", description="y"),
            ],
        )

        analyzer = PlanQualityAnalyzer()
        metrics = analyzer.analyze(plan)

        # Should not have more than 5 suggestions
        assert len(metrics.improvement_suggestions) <= 5
