"""Tests for benchmark models and BenchmarkSuite."""

from datetime import UTC, datetime

from app.domain.services.agents.benchmarks import (
    AgentBenchmarks,
    BenchmarkCategory,
    BenchmarkResult,
    BenchmarkSuite,
)


class TestBenchmarkCategory:
    """Tests for BenchmarkCategory enum."""

    def test_all_categories_exist(self):
        expected = {
            "token_efficiency",
            "latency",
            "cache_performance",
            "tool_selection",
            "hallucination",
            "memory",
        }
        assert {c.value for c in BenchmarkCategory} == expected

    def test_is_string_enum(self):
        assert isinstance(BenchmarkCategory.TOKEN_EFFICIENCY, str)
        assert BenchmarkCategory.LATENCY == "latency"

    def test_category_count(self):
        assert len(BenchmarkCategory) == 6


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_create_minimal(self):
        result = BenchmarkResult(
            name="test_bench",
            category=BenchmarkCategory.LATENCY,
            passed=True,
            score=0.95,
        )
        assert result.name == "test_bench"
        assert result.category == BenchmarkCategory.LATENCY
        assert result.passed is True
        assert result.score == 0.95

    def test_default_metrics(self):
        result = BenchmarkResult(
            name="test", category=BenchmarkCategory.MEMORY, passed=True, score=1.0
        )
        assert result.metrics == {}

    def test_default_duration(self):
        result = BenchmarkResult(
            name="test", category=BenchmarkCategory.MEMORY, passed=True, score=1.0
        )
        assert result.duration_ms == 0

    def test_default_error(self):
        result = BenchmarkResult(
            name="test", category=BenchmarkCategory.MEMORY, passed=True, score=1.0
        )
        assert result.error is None

    def test_timestamp_auto_set(self):
        before = datetime.now(UTC)
        result = BenchmarkResult(
            name="test", category=BenchmarkCategory.MEMORY, passed=True, score=1.0
        )
        after = datetime.now(UTC)
        assert before <= result.timestamp <= after

    def test_with_metrics(self):
        result = BenchmarkResult(
            name="test",
            category=BenchmarkCategory.TOKEN_EFFICIENCY,
            passed=True,
            score=0.8,
            metrics={"tokens_saved": 500, "reduction_pct": 0.3},
        )
        assert result.metrics["tokens_saved"] == 500

    def test_with_error(self):
        result = BenchmarkResult(
            name="test",
            category=BenchmarkCategory.HALLUCINATION,
            passed=False,
            score=0.0,
            error="Test failed due to timeout",
        )
        assert result.error == "Test failed due to timeout"
        assert result.passed is False

    def test_score_boundaries(self):
        # Score 0.0
        r1 = BenchmarkResult(
            name="zero", category=BenchmarkCategory.LATENCY, passed=False, score=0.0
        )
        assert r1.score == 0.0

        # Score 1.0
        r2 = BenchmarkResult(
            name="one", category=BenchmarkCategory.LATENCY, passed=True, score=1.0
        )
        assert r2.score == 1.0

    def test_with_duration(self):
        result = BenchmarkResult(
            name="test",
            category=BenchmarkCategory.CACHE_PERFORMANCE,
            passed=True,
            score=0.9,
            duration_ms=150.5,
        )
        assert result.duration_ms == 150.5


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite dataclass."""

    def test_create_empty_suite(self):
        suite = BenchmarkSuite(name="test_suite")
        assert suite.name == "test_suite"
        assert suite.results == []
        assert suite.completed_at is None

    def test_started_at_auto_set(self):
        before = datetime.now(UTC)
        suite = BenchmarkSuite(name="test")
        after = datetime.now(UTC)
        assert before <= suite.started_at <= after

    def test_passed_count_empty(self):
        suite = BenchmarkSuite(name="test")
        assert suite.passed_count == 0

    def test_passed_count_with_results(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.LATENCY, passed=False, score=0.0),
                BenchmarkResult(name="c", category=BenchmarkCategory.LATENCY, passed=True, score=0.8),
            ],
        )
        assert suite.passed_count == 2

    def test_failed_count(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.LATENCY, passed=False, score=0.0),
                BenchmarkResult(name="c", category=BenchmarkCategory.LATENCY, passed=False, score=0.2),
            ],
        )
        assert suite.failed_count == 2

    def test_total_duration_ms_empty(self):
        suite = BenchmarkSuite(name="test")
        assert suite.total_duration_ms == 0

    def test_total_duration_ms(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(
                    name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0, duration_ms=100
                ),
                BenchmarkResult(
                    name="b", category=BenchmarkCategory.LATENCY, passed=True, score=1.0, duration_ms=200
                ),
                BenchmarkResult(
                    name="c", category=BenchmarkCategory.LATENCY, passed=True, score=1.0, duration_ms=50.5
                ),
            ],
        )
        assert suite.total_duration_ms == 350.5

    def test_average_score_empty(self):
        suite = BenchmarkSuite(name="test")
        assert suite.average_score == 0.0

    def test_average_score(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.LATENCY, passed=True, score=0.5),
                BenchmarkResult(name="c", category=BenchmarkCategory.LATENCY, passed=True, score=0.8),
            ],
        )
        expected = (1.0 + 0.5 + 0.8) / 3
        assert abs(suite.average_score - expected) < 1e-10

    def test_by_category(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.MEMORY, passed=True, score=0.9),
                BenchmarkResult(name="c", category=BenchmarkCategory.LATENCY, passed=True, score=0.8),
                BenchmarkResult(name="d", category=BenchmarkCategory.HALLUCINATION, passed=False, score=0.2),
            ],
        )
        latency_results = suite.by_category(BenchmarkCategory.LATENCY)
        assert len(latency_results) == 2
        assert all(r.category == BenchmarkCategory.LATENCY for r in latency_results)

    def test_by_category_empty(self):
        suite = BenchmarkSuite(name="test")
        results = suite.by_category(BenchmarkCategory.TOOL_SELECTION)
        assert results == []

    def test_by_category_no_match(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
            ],
        )
        results = suite.by_category(BenchmarkCategory.MEMORY)
        assert results == []

    def test_all_passed(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=1.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.MEMORY, passed=True, score=0.9),
            ],
        )
        assert suite.passed_count == 2
        assert suite.failed_count == 0

    def test_all_failed(self):
        suite = BenchmarkSuite(
            name="test",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=False, score=0.0),
                BenchmarkResult(name="b", category=BenchmarkCategory.MEMORY, passed=False, score=0.1),
            ],
        )
        assert suite.passed_count == 0
        assert suite.failed_count == 2


class TestAgentBenchmarks:
    """Tests for AgentBenchmarks class."""

    def test_init_registers_benchmarks(self):
        benchmarks = AgentBenchmarks()
        assert len(benchmarks._benchmarks) > 0

    def test_registered_benchmark_names(self):
        benchmarks = AgentBenchmarks()
        expected_names = {
            "token_dynamic_toolset",
            "token_prompt_caching",
            "token_count_cache",
            "cache_l1_performance",
            "cache_l2_performance",
            "cache_combined_hit_rate",
            "tool_category_detection",
            "tool_semantic_search",
            "tool_task_filtering",
            "hallucination_detection",
            "hallucination_suggestions",
            "memory_pressure_detection",
            "memory_token_manager",
        }
        assert set(benchmarks._benchmarks.keys()) == expected_names

    def test_all_benchmarks_are_callable(self):
        benchmarks = AgentBenchmarks()
        for name, func in benchmarks._benchmarks.items():
            assert callable(func), f"Benchmark {name} is not callable"
