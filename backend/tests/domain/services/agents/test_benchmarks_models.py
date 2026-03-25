"""Tests for benchmark data structures — BenchmarkResult, BenchmarkSuite."""

from app.domain.services.agents.benchmarks import (
    BenchmarkCategory,
    BenchmarkResult,
    BenchmarkSuite,
)


class TestBenchmarkCategory:
    def test_values(self) -> None:
        expected = {
            "token_efficiency", "latency", "cache_performance",
            "tool_selection", "hallucination", "memory",
        }
        assert {c.value for c in BenchmarkCategory} == expected


class TestBenchmarkResult:
    def test_minimal(self) -> None:
        r = BenchmarkResult(
            name="test_bench",
            category=BenchmarkCategory.LATENCY,
            passed=True,
            score=0.95,
        )
        assert r.passed is True
        assert r.error is None
        assert r.duration_ms == 0
        assert r.metrics == {}

    def test_with_error(self) -> None:
        r = BenchmarkResult(
            name="failing",
            category=BenchmarkCategory.HALLUCINATION,
            passed=False,
            score=0.2,
            error="Timeout",
        )
        assert r.passed is False
        assert r.error == "Timeout"


class TestBenchmarkSuite:
    def _make(self) -> BenchmarkSuite:
        return BenchmarkSuite(
            name="test_suite",
            results=[
                BenchmarkResult(name="a", category=BenchmarkCategory.LATENCY, passed=True, score=0.9, duration_ms=100),
                BenchmarkResult(name="b", category=BenchmarkCategory.LATENCY, passed=True, score=0.8, duration_ms=200),
                BenchmarkResult(name="c", category=BenchmarkCategory.TOKEN_EFFICIENCY, passed=False, score=0.3, duration_ms=50),
            ],
        )

    def test_passed_count(self) -> None:
        s = self._make()
        assert s.passed_count == 2

    def test_failed_count(self) -> None:
        s = self._make()
        assert s.failed_count == 1

    def test_total_duration(self) -> None:
        s = self._make()
        assert s.total_duration_ms == 350

    def test_average_score(self) -> None:
        s = self._make()
        avg = s.average_score
        assert 0.6 < avg < 0.7

    def test_average_score_empty(self) -> None:
        s = BenchmarkSuite(name="empty")
        assert s.average_score == 0.0

    def test_by_category(self) -> None:
        s = self._make()
        latency = s.by_category(BenchmarkCategory.LATENCY)
        assert len(latency) == 2
        token = s.by_category(BenchmarkCategory.TOKEN_EFFICIENCY)
        assert len(token) == 1
        memory = s.by_category(BenchmarkCategory.MEMORY)
        assert len(memory) == 0
