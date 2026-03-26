"""Tests for ragas_metrics evaluation models."""

from app.domain.services.evaluation.ragas_metrics import (
    AsymmetryIssue,
    ComparisonItem,
    DataSymmetryResult,
    EvalMetricType,
    EvalResult,
    EvaluationBatch,
    ToolSelectionResult,
)


class TestEvalMetricType:
    """Tests for EvalMetricType enum."""

    def test_all_metric_types(self):
        expected = {
            "faithfulness",
            "answer_relevance",
            "context_relevance",
            "tool_selection_accuracy",
            "response_completeness",
            "hallucination_score",
            "data_symmetry",
            "comparison_consistency",
        }
        assert {m.value for m in EvalMetricType} == expected

    def test_is_string_enum(self):
        assert isinstance(EvalMetricType.FAITHFULNESS, str)
        assert EvalMetricType.FAITHFULNESS == "faithfulness"

    def test_count(self):
        assert len(EvalMetricType) == 8


class TestEvalResult:
    """Tests for EvalResult dataclass."""

    def test_create_passing_result(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.9,
        )
        assert result.passed is True
        assert result.score == 0.9
        assert result.threshold == 0.7

    def test_create_failing_result(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.5,
        )
        assert result.passed is False

    def test_custom_threshold_passing(self):
        result = EvalResult(
            metric_type=EvalMetricType.ANSWER_RELEVANCE,
            score=0.6,
            threshold=0.5,
        )
        assert result.passed is True

    def test_custom_threshold_failing(self):
        result = EvalResult(
            metric_type=EvalMetricType.ANSWER_RELEVANCE,
            score=0.6,
            threshold=0.8,
        )
        assert result.passed is False

    def test_exact_threshold_passes(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.7,
            threshold=0.7,
        )
        assert result.passed is True

    def test_just_below_threshold_fails(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.699,
            threshold=0.7,
        )
        assert result.passed is False

    def test_default_reasoning_empty(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.9,
        )
        assert result.reasoning == ""

    def test_default_details_empty(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.9,
        )
        assert result.details == {}

    def test_with_reasoning(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.9,
            reasoning="High alignment with context",
        )
        assert result.reasoning == "High alignment with context"

    def test_to_dict(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.85,
            reasoning="Good",
            details={"claims": 5},
        )
        d = result.to_dict()
        assert d["metric_type"] == "faithfulness"
        assert d["score"] == 0.85
        assert d["passed"] is True
        assert d["threshold"] == 0.7
        assert d["reasoning"] == "Good"
        assert d["details"] == {"claims": 5}

    def test_to_dict_rounds_score(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=0.123456789,
        )
        d = result.to_dict()
        assert d["score"] == 0.1235

    def test_zero_score(self):
        result = EvalResult(
            metric_type=EvalMetricType.HALLUCINATION_SCORE,
            score=0.0,
        )
        assert result.passed is False
        assert result.score == 0.0

    def test_perfect_score(self):
        result = EvalResult(
            metric_type=EvalMetricType.FAITHFULNESS,
            score=1.0,
        )
        assert result.passed is True


class TestToolSelectionResult:
    """Tests for ToolSelectionResult dataclass."""

    def test_create_with_defaults(self):
        result = ToolSelectionResult(
            metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
            score=0.8,
        )
        assert result.expected_tools == []
        assert result.selected_tools == []
        assert result.correct_selections == []
        assert result.missed_tools == []
        assert result.unnecessary_tools == []

    def test_with_tool_data(self):
        result = ToolSelectionResult(
            metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
            score=0.75,
            expected_tools=["search", "browser"],
            selected_tools=["search", "file_read"],
            correct_selections=["search"],
            missed_tools=["browser"],
            unnecessary_tools=["file_read"],
        )
        assert result.expected_tools == ["search", "browser"]
        assert result.missed_tools == ["browser"]

    def test_post_init_sets_details(self):
        result = ToolSelectionResult(
            metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
            score=0.8,
            expected_tools=["search"],
            selected_tools=["search"],
            correct_selections=["search"],
        )
        assert "expected_tools" in result.details
        assert "selected_tools" in result.details
        assert result.details["expected_tools"] == ["search"]

    def test_inherits_passed_from_score(self):
        result = ToolSelectionResult(
            metric_type=EvalMetricType.TOOL_SELECTION_ACCURACY,
            score=0.9,
        )
        assert result.passed is True


class TestComparisonItem:
    """Tests for ComparisonItem dataclass."""

    def test_create_minimal(self):
        item = ComparisonItem(name="GPT-4")
        assert item.name == "GPT-4"
        assert item.metric_value is None
        assert item.metric_type == "none"
        assert item.metric_name is None

    def test_create_quantitative(self):
        item = ComparisonItem(
            name="GPT-4",
            metric_value="92.5%",
            metric_type="quantitative",
            metric_name="MMLU",
        )
        assert item.metric_value == "92.5%"
        assert item.metric_type == "quantitative"
        assert item.metric_name == "MMLU"

    def test_create_qualitative(self):
        item = ComparisonItem(
            name="Claude",
            metric_value="Very good performance",
            metric_type="qualitative",
        )
        assert item.metric_type == "qualitative"


class TestAsymmetryIssue:
    """Tests for AsymmetryIssue dataclass."""

    def test_create(self):
        a = ComparisonItem(name="Model A", metric_type="quantitative")
        b = ComparisonItem(name="Model B", metric_type="qualitative")
        issue = AsymmetryIssue(
            item_a=a,
            item_b=b,
            issue_description="Metric type mismatch",
        )
        assert issue.item_a.name == "Model A"
        assert issue.item_b.name == "Model B"
        assert issue.severity == "major"

    def test_custom_severity(self):
        a = ComparisonItem(name="A")
        b = ComparisonItem(name="B")
        issue = AsymmetryIssue(
            item_a=a, item_b=b, issue_description="test", severity="critical"
        )
        assert issue.severity == "critical"


class TestDataSymmetryResult:
    """Tests for DataSymmetryResult dataclass."""

    def test_create_with_defaults(self):
        result = DataSymmetryResult(
            metric_type=EvalMetricType.DATA_SYMMETRY,
            score=0.9,
        )
        assert result.comparison_items == []
        assert result.asymmetry_issues == []
        assert result.symmetric_comparisons == 0
        assert result.total_comparisons == 0

    def test_with_comparison_data(self):
        items = [
            ComparisonItem(name="A", metric_value="90%", metric_type="quantitative"),
            ComparisonItem(name="B", metric_value="85%", metric_type="quantitative"),
        ]
        result = DataSymmetryResult(
            metric_type=EvalMetricType.DATA_SYMMETRY,
            score=1.0,
            comparison_items=items,
            symmetric_comparisons=1,
            total_comparisons=1,
        )
        assert len(result.comparison_items) == 2
        assert result.symmetric_comparisons == 1

    def test_details_populated(self):
        items = [ComparisonItem(name="A", metric_value="90%", metric_type="quantitative")]
        result = DataSymmetryResult(
            metric_type=EvalMetricType.DATA_SYMMETRY,
            score=0.8,
            comparison_items=items,
        )
        assert "comparison_items" in result.details
        assert "asymmetry_issues" in result.details
        assert result.details["comparison_items"][0]["name"] == "A"


class TestEvaluationBatch:
    """Tests for EvaluationBatch dataclass."""

    def test_create_empty(self):
        batch = EvaluationBatch()
        assert batch.results == []
        assert batch.session_id is None
        assert batch.task_id is None

    def test_average_score_empty(self):
        batch = EvaluationBatch()
        assert batch.average_score == 0.0

    def test_average_score_with_results(self):
        batch = EvaluationBatch(
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.8),
                EvalResult(metric_type=EvalMetricType.ANSWER_RELEVANCE, score=0.6),
            ]
        )
        assert abs(batch.average_score - 0.7) < 1e-10

    def test_pass_rate_empty(self):
        batch = EvaluationBatch()
        assert batch.pass_rate == 0.0

    def test_pass_rate_with_results(self):
        batch = EvaluationBatch(
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.9),  # passes (>0.7)
                EvalResult(metric_type=EvalMetricType.ANSWER_RELEVANCE, score=0.5),  # fails
                EvalResult(metric_type=EvalMetricType.CONTEXT_RELEVANCE, score=0.8),  # passes
            ]
        )
        expected = 2 / 3
        assert abs(batch.pass_rate - expected) < 1e-10

    def test_get_by_metric(self):
        batch = EvaluationBatch(
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.9),
                EvalResult(metric_type=EvalMetricType.ANSWER_RELEVANCE, score=0.8),
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.7),
            ]
        )
        faith = batch.get_by_metric(EvalMetricType.FAITHFULNESS)
        assert len(faith) == 2

    def test_get_by_metric_no_match(self):
        batch = EvaluationBatch(
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.9),
            ]
        )
        result = batch.get_by_metric(EvalMetricType.HALLUCINATION_SCORE)
        assert result == []

    def test_to_dict(self):
        batch = EvaluationBatch(
            session_id="session-1",
            task_id="task-1",
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.9),
            ],
        )
        d = batch.to_dict()
        assert d["session_id"] == "session-1"
        assert d["task_id"] == "task-1"
        assert d["total_evaluations"] == 1
        assert d["average_score"] == 0.9
        assert len(d["results"]) == 1

    def test_to_dict_rounds_values(self):
        batch = EvaluationBatch(
            results=[
                EvalResult(metric_type=EvalMetricType.FAITHFULNESS, score=0.333333),
                EvalResult(metric_type=EvalMetricType.ANSWER_RELEVANCE, score=0.666666),
            ]
        )
        d = batch.to_dict()
        assert d["average_score"] == round(0.4999995, 4)

    def test_with_session_and_task(self):
        batch = EvaluationBatch(session_id="s1", task_id="t1")
        assert batch.session_id == "s1"
        assert batch.task_id == "t1"
