"""
Accuracy benchmark for agent evaluation.

Measures task completion rate, response quality, and other accuracy metrics
across a suite of test cases.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    total_cases: int
    passed_cases: int
    pass_rate: float
    avg_score: float
    latency_p50: float
    latency_p95: float
    latency_avg: float
    cost_total: float
    failures: list[dict[str, Any]] = field(default_factory=list)
    case_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "pass_rate": self.pass_rate,
            "avg_score": self.avg_score,
            "latency_p50": self.latency_p50,
            "latency_p95": self.latency_p95,
            "latency_avg": self.latency_avg,
            "cost_total": self.cost_total,
            "failure_count": len(self.failures),
        }


class Grader(Protocol):
    """Protocol for graders."""

    async def grade(
        self,
        output: dict[str, Any],
        case: dict[str, Any],
    ) -> Any:
        """Grade an output against a test case."""
        ...


class AgentFlow(Protocol):
    """Protocol for agent flows."""

    async def run(self, input_text: str) -> dict[str, Any]:
        """Run the agent with input and return result."""
        ...


class AccuracyBenchmark:
    """Benchmark for measuring agent accuracy."""

    def __init__(
        self,
        flow: AgentFlow,
        graders: list[Grader],
        name: str = "accuracy",
    ):
        """Initialize the benchmark.

        Args:
            flow: The agent flow to benchmark
            graders: List of graders to apply
            name: Name of this benchmark
        """
        self.flow = flow
        self.graders = graders
        self.name = name

    async def run(
        self,
        cases: list[dict[str, Any]],
        parallel: int = 1,
    ) -> BenchmarkResult:
        """Run the benchmark on all cases.

        Args:
            cases: List of test cases with 'input' and optional constraints
            parallel: Number of cases to run in parallel

        Returns:
            BenchmarkResult with aggregate metrics
        """
        results = []

        if parallel > 1:
            # Run in batches
            for i in range(0, len(cases), parallel):
                batch = cases[i : i + parallel]
                batch_results = await asyncio.gather(
                    *[self._evaluate_case(case) for case in batch],
                    return_exceptions=True,
                )

                for result in batch_results:
                    if isinstance(result, Exception):
                        results.append(
                            {
                                "passed": False,
                                "score": 0.0,
                                "error": str(result),
                                "latency": 0.0,
                                "cost": 0.0,
                            }
                        )
                    else:
                        results.append(result)
        else:
            # Run sequentially
            for case in cases:
                try:
                    result = await self._evaluate_case(case)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Case evaluation failed: {e}")
                    results.append(
                        {
                            "passed": False,
                            "score": 0.0,
                            "error": str(e),
                            "latency": 0.0,
                            "cost": 0.0,
                        }
                    )

        return self._aggregate_results(results)

    async def _evaluate_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single test case.

        Args:
            case: Test case with 'input' and constraints

        Returns:
            Dict with case_id, passed, score, latency, cost, grades
        """
        case_id = case.get("id", "unknown")
        input_text = case.get("input", "")

        logger.debug(f"Evaluating case {case_id}: {input_text[:50]}...")

        # Run the agent
        start_time = time.time()
        try:
            output = await self.flow.run(input_text)
        except Exception as e:
            logger.error(f"Agent run failed for case {case_id}: {e}")
            return {
                "case_id": case_id,
                "passed": False,
                "score": 0.0,
                "latency": time.time() - start_time,
                "cost": 0.0,
                "error": str(e),
                "grades": [],
            }

        latency = time.time() - start_time

        # Apply all graders
        grades = []
        for grader in self.graders:
            try:
                grade = await grader.grade(output, case)
                grades.append(grade)
            except Exception as e:
                logger.error(f"Grader failed for case {case_id}: {e}")
                grades.append(type("Grade", (), {"passed": False, "score": 0.0, "feedback": str(e)})())

        # Aggregate grades
        passed = all(g.passed for g in grades if hasattr(g, "passed"))
        avg_score = sum(g.score for g in grades if hasattr(g, "score")) / len(grades) if grades else 0.0

        return {
            "case_id": case_id,
            "passed": passed,
            "score": avg_score,
            "latency": latency,
            "cost": output.get("cost", 0.0),
            "grades": [
                {"passed": g.passed, "score": g.score, "feedback": getattr(g, "feedback", "")}
                for g in grades
                if hasattr(g, "passed")
            ],
        }

    def _aggregate_results(self, results: list[dict[str, Any]]) -> BenchmarkResult:
        """Aggregate individual results into benchmark result.

        Args:
            results: List of individual case results

        Returns:
            BenchmarkResult with aggregate metrics
        """
        if not results:
            return BenchmarkResult(
                total_cases=0,
                passed_cases=0,
                pass_rate=0.0,
                avg_score=0.0,
                latency_p50=0.0,
                latency_p95=0.0,
                latency_avg=0.0,
                cost_total=0.0,
            )

        passed = [r for r in results if r.get("passed", False)]
        failures = [r for r in results if not r.get("passed", False)]
        latencies = sorted([r.get("latency", 0.0) for r in results])

        total = len(results)
        num_passed = len(passed)

        return BenchmarkResult(
            total_cases=total,
            passed_cases=num_passed,
            pass_rate=num_passed / total if total > 0 else 0.0,
            avg_score=sum(r.get("score", 0.0) for r in results) / total if total > 0 else 0.0,
            latency_p50=latencies[len(latencies) // 2] if latencies else 0.0,
            latency_p95=latencies[int(len(latencies) * 0.95)] if latencies else 0.0,
            latency_avg=sum(latencies) / len(latencies) if latencies else 0.0,
            cost_total=sum(r.get("cost", 0.0) for r in results),
            failures=failures,
            case_results=results,
        )


class TaskCompletionBenchmark(AccuracyBenchmark):
    """Specialized benchmark for task completion metrics."""

    async def run_with_retry(
        self,
        cases: list[dict[str, Any]],
        max_retries: int = 2,
    ) -> BenchmarkResult:
        """Run benchmark with retry for failed cases.

        Args:
            cases: Test cases to run
            max_retries: Maximum retries per failed case

        Returns:
            BenchmarkResult including retry statistics
        """
        all_results = []

        for case in cases:
            result = None
            retries = 0

            while retries <= max_retries:
                try:
                    result = await self._evaluate_case(case)
                    if result.get("passed", False):
                        break
                    retries += 1
                except Exception as e:
                    logger.error(f"Case failed on retry {retries}: {e}")
                    retries += 1

            if result:
                result["retries"] = retries
                all_results.append(result)
            else:
                all_results.append(
                    {
                        "case_id": case.get("id", "unknown"),
                        "passed": False,
                        "score": 0.0,
                        "latency": 0.0,
                        "cost": 0.0,
                        "retries": retries,
                        "error": "All retries exhausted",
                    }
                )

        return self._aggregate_results(all_results)


class HallucinationBenchmark:
    """Benchmark for measuring hallucination rate."""

    def __init__(self, flow: AgentFlow, hallucination_detector):
        """Initialize the hallucination benchmark.

        Args:
            flow: Agent flow to benchmark
            hallucination_detector: Detector for hallucinations
        """
        self.flow = flow
        self.detector = hallucination_detector

    async def run(
        self,
        cases: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run hallucination benchmark.

        Args:
            cases: Test cases with 'input' and 'sources'

        Returns:
            Dict with hallucination metrics
        """
        total = 0
        hallucinated = 0
        scores = []

        for case in cases:
            input_text = case.get("input", "")
            sources = case.get("sources", [])

            try:
                output = await self.flow.run(input_text)
                response = output.get("response", "")

                result = await self.detector.detect_hallucination(response, sources)

                total += 1
                if not result.passed:
                    hallucinated += 1
                scores.append(result.score)

            except Exception as e:
                logger.error(f"Hallucination check failed: {e}")
                total += 1
                hallucinated += 1
                scores.append(0.0)

        return {
            "total_cases": total,
            "hallucinated_count": hallucinated,
            "hallucination_rate": hallucinated / total if total > 0 else 0.0,
            "avg_accuracy_score": sum(scores) / len(scores) if scores else 0.0,
        }


def create_benchmark_suite(flow: AgentFlow, graders: list[Grader]) -> dict[str, AccuracyBenchmark]:
    """Create a suite of benchmarks for comprehensive evaluation.

    Args:
        flow: Agent flow to benchmark
        graders: List of graders to use

    Returns:
        Dict mapping benchmark names to benchmark instances
    """
    return {
        "accuracy": AccuracyBenchmark(flow, graders, name="accuracy"),
        "task_completion": TaskCompletionBenchmark(flow, graders, name="task_completion"),
    }
