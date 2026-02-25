"""Evaluation runner for executing test suites.

The main entry point for running evaluations against agents and LLMs.
Supports parallel execution, retries, and comprehensive reporting.
"""

import asyncio
import logging
import traceback
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from .metrics.base import get_metric
from .types import (
    EvalCase,
    EvalConfig,
    EvalDataset,
    EvalReport,
    EvalResult,
    EvalStatus,
    MetricScore,
)

logger = logging.getLogger(__name__)


class LLMProtocol(Protocol):
    """Protocol for LLM interface."""

    async def ask(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, **kwargs
    ) -> dict[str, Any]: ...


class AgentProtocol(Protocol):
    """Protocol for agent interface."""

    async def execute(self, request: str, **kwargs) -> AsyncGenerator[Any, None]: ...


# Type for custom evaluators
CustomEvaluator = Callable[[str, str, dict[str, Any]], Awaitable[MetricScore]]


class EvalRunner:
    """Main evaluation runner for testing agents and LLM outputs.

    Supports:
    - Running evaluations against raw LLM or full agents
    - Parallel and sequential execution
    - Multiple metrics per test case
    - Retries with backoff
    - Comprehensive reporting

    Example:
        runner = EvalRunner(llm=my_llm)
        report = await runner.run(dataset)
        print(f"Pass rate: {report.pass_rate}")
    """

    def __init__(
        self,
        llm: LLMProtocol | None = None,
        agent: AgentProtocol | None = None,
        config: EvalConfig | None = None,
        custom_evaluators: dict[str, CustomEvaluator] | None = None,
    ):
        """Initialize the evaluation runner.

        Args:
            llm: LLM instance for direct LLM evaluation
            agent: Agent instance for full agent evaluation
            config: Evaluation configuration
            custom_evaluators: Dictionary of custom evaluator functions
        """
        self._llm = llm
        self._agent = agent
        self._config = config or EvalConfig()
        self._custom_evaluators = custom_evaluators or {}

        if not llm and not agent:
            logger.warning("No LLM or agent provided - running in mock mode")

    async def run(
        self,
        dataset: EvalDataset,
        config: EvalConfig | None = None,
    ) -> EvalReport:
        """Run evaluation on a dataset.

        Args:
            dataset: The dataset to evaluate
            config: Optional override configuration

        Returns:
            EvalReport with all results
        """
        config = config or self._config
        run_id = str(uuid.uuid4())[:8]

        logger.info(f"Starting evaluation run {run_id} on dataset '{dataset.name}'")

        report = EvalReport(
            run_id=run_id,
            dataset_name=dataset.name,
            config=config,
        )

        # Filter cases
        cases = self._filter_cases(dataset.cases, config)

        if not cases:
            logger.warning("No test cases to run after filtering")
            report.finalize()
            return report

        logger.info(f"Running {len(cases)} test cases")

        # Run evaluations
        if config.parallel and len(cases) > 1:
            results = await self._run_parallel(cases, config)
        else:
            results = await self._run_sequential(cases, config)

        # Add results to report
        for result in results:
            report.add_result(result)

        report.finalize()

        # Log summary
        logger.info(
            f"Evaluation complete: {report.passed_cases}/{report.total_cases} passed "
            f"({report.pass_rate * 100:.1f}%), avg score: {report.average_score:.3f}"
        )

        return report

    def _filter_cases(self, cases: list[EvalCase], config: EvalConfig) -> list[EvalCase]:
        """Filter cases based on configuration."""
        filtered = []

        for case in cases:
            # Skip if marked
            if case.skip:
                logger.debug(f"Skipping case {case.id}: {case.skip_reason}")
                continue

            # Filter by case IDs
            if config.case_ids and case.id not in config.case_ids:
                continue

            # Filter by include tags
            if config.include_tags and not any(tag in case.tags for tag in config.include_tags):
                continue

            # Filter by exclude tags
            if config.exclude_tags and any(tag in case.tags for tag in config.exclude_tags):
                continue

            filtered.append(case)

        return filtered

    async def _run_parallel(self, cases: list[EvalCase], config: EvalConfig) -> list[EvalResult]:
        """Run cases in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(config.max_parallel)

        async def run_with_semaphore(case: EvalCase) -> EvalResult:
            async with semaphore:
                return await self._run_case(case, config)

        results = await asyncio.gather(*[run_with_semaphore(case) for case in cases], return_exceptions=True)

        # Convert exceptions to error results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(
                    EvalResult(
                        case_id=cases[i].id,
                        status=EvalStatus.ERROR,
                        error=str(result),
                        error_type=type(result).__name__,
                    )
                )
            else:
                final_results.append(result)

        return final_results

    async def _run_sequential(self, cases: list[EvalCase], config: EvalConfig) -> list[EvalResult]:
        """Run cases sequentially."""
        results = []

        for case in cases:
            try:
                result = await self._run_case(case, config)
                results.append(result)
            except Exception as e:
                results.append(
                    EvalResult(
                        case_id=case.id,
                        status=EvalStatus.ERROR,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                )

        return results

    async def _run_case(self, case: EvalCase, config: EvalConfig) -> EvalResult:
        """Run a single evaluation case."""
        result = EvalResult(case_id=case.id, status=EvalStatus.RUNNING)

        logger.debug(f"Running case {case.id}: {case.name or case.input[:50]}...")

        # Try with retries
        last_error = None
        for attempt in range(config.retries + 1):
            try:
                # Get output from LLM or agent
                output, context = await self._get_output(case, config)

                # Update result with context
                result.actual_output = output
                result.input_tokens = context.get("input_tokens", 0)
                result.output_tokens = context.get("output_tokens", 0)
                result.total_tokens = context.get("total_tokens", 0)
                result.tool_calls = context.get("tool_calls", [])
                result.raw_response = context.get("raw_response")

                # Run metrics
                scores = await self._evaluate_output(case, output, context, config)
                result.scores = scores

                # Complete the result
                result.complete(output)
                break

            except TimeoutError:
                last_error = "Timeout"
                if attempt < config.retries:
                    logger.warning(f"Case {case.id} timed out, retrying ({attempt + 1}/{config.retries})")
                    await asyncio.sleep(1.0)

            except Exception as e:
                last_error = str(e)
                if attempt < config.retries:
                    logger.warning(f"Case {case.id} failed: {e}, retrying ({attempt + 1}/{config.retries})")
                    await asyncio.sleep(1.0)

        if result.status == EvalStatus.RUNNING:
            result.fail(
                error=last_error or "Unknown error",
                error_type="EvaluationError",
                traceback=traceback.format_exc(),
            )

        return result

    async def _get_output(self, case: EvalCase, config: EvalConfig) -> tuple[str, dict[str, Any]]:
        """Get output from LLM or agent.

        Returns:
            Tuple of (output_text, context_dict)
        """
        timeout = case.timeout_seconds or config.timeout_seconds

        async with asyncio.timeout(timeout):
            if self._agent:
                return await self._get_agent_output(case)
            if self._llm:
                return await self._get_llm_output(case)
            # Mock mode for testing
            return self._get_mock_output(case)

    async def _get_llm_output(self, case: EvalCase) -> tuple[str, dict[str, Any]]:
        """Get output from raw LLM."""
        messages = [{"role": "user", "content": case.input}]

        if case.input_context.get("system_prompt"):
            messages.insert(0, {"role": "system", "content": case.input_context["system_prompt"]})

        start_time = datetime.now(UTC)
        response = await self._llm.ask(messages)
        end_time = datetime.now(UTC)

        output = response.get("content", "")
        context = {
            "duration_seconds": (end_time - start_time).total_seconds(),
            "input_tokens": response.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": response.get("usage", {}).get("completion_tokens", 0),
            "total_tokens": response.get("usage", {}).get("total_tokens", 0),
            "tool_calls": response.get("tool_calls", []),
            "raw_response": response,
        }

        return output, context

    async def _get_agent_output(self, case: EvalCase) -> tuple[str, dict[str, Any]]:
        """Get output from full agent execution."""
        from app.domain.models.event import ErrorEvent, MessageEvent, ToolEvent

        output_parts = []
        tool_calls = []

        start_time = datetime.now(UTC)

        async for event in self._agent.execute(case.input):
            if isinstance(event, MessageEvent):
                output_parts.append(event.message)
            elif isinstance(event, ToolEvent):
                tool_calls.append(
                    {
                        "function_name": event.function_name,
                        "arguments": event.function_args,
                        "result": event.function_result.model_dump() if event.function_result else None,
                    }
                )
            elif isinstance(event, ErrorEvent):
                raise RuntimeError(event.error)

        end_time = datetime.now(UTC)

        output = "\n".join(output_parts)
        context = {
            "duration_seconds": (end_time - start_time).total_seconds(),
            "tool_calls": tool_calls,
        }

        return output, context

    def _get_mock_output(self, case: EvalCase) -> tuple[str, dict[str, Any]]:
        """Get mock output for testing the evaluation framework."""
        # Return a simple mock based on input
        mock_output = f"Mock response to: {case.input[:50]}"

        context = {
            "duration_seconds": 0.1,
            "input_tokens": len(case.input) // 4,
            "output_tokens": len(mock_output) // 4,
            "total_tokens": (len(case.input) + len(mock_output)) // 4,
            "tool_calls": [],
        }

        return mock_output, context

    async def _evaluate_output(
        self, case: EvalCase, output: str, context: dict[str, Any], config: EvalConfig
    ) -> list[MetricScore]:
        """Evaluate output using configured metrics."""
        scores = []

        # Build expected dictionary from case
        expected = {
            "expected_output": case.expected_output,
            "expected_output_contains": case.expected_output_contains,
            "expected_output_not_contains": case.expected_output_not_contains,
            "expected_json_schema": case.expected_json_schema,
            "expected_tool_calls": case.expected_tool_calls,
            "min_similarity": case.min_similarity,
            "max_response_time_seconds": case.max_response_time_seconds,
            "max_tokens": case.max_tokens,
        }

        # Run configured metrics
        for metric_name in config.metrics:
            metric = get_metric(metric_name)
            if metric:
                try:
                    score = metric.evaluate(output, expected, context)
                    scores.append(score)
                except Exception as e:
                    logger.warning(f"Metric {metric_name} failed: {e}")
                    scores.append(
                        MetricScore(metric_name=metric_name, score=0.0, passed=False, message=f"Metric error: {e!s}")
                    )

        # Run custom evaluator if specified
        if case.custom_evaluator and case.custom_evaluator in self._custom_evaluators:
            try:
                custom_score = await self._custom_evaluators[case.custom_evaluator](
                    output, case.expected_output or "", context
                )
                scores.append(custom_score)
            except Exception as e:
                logger.warning(f"Custom evaluator {case.custom_evaluator} failed: {e}")

        return scores

    def register_custom_evaluator(self, name: str, evaluator: CustomEvaluator) -> None:
        """Register a custom evaluator function.

        Args:
            name: Name to reference the evaluator
            evaluator: Async function that returns a MetricScore
        """
        self._custom_evaluators[name] = evaluator


async def run_evaluation(
    dataset: EvalDataset,
    llm: LLMProtocol | None = None,
    agent: AgentProtocol | None = None,
    config: EvalConfig | None = None,
) -> EvalReport:
    """Convenience function for running an evaluation.

    Args:
        dataset: The dataset to evaluate
        llm: Optional LLM instance
        agent: Optional agent instance
        config: Optional configuration

    Returns:
        EvalReport with results
    """
    runner = EvalRunner(llm=llm, agent=agent, config=config)
    return await runner.run(dataset)


# CLI entry point
async def main():
    """Command-line interface for running evaluations."""
    import argparse

    parser = argparse.ArgumentParser(description="Run agent evaluations")
    parser.add_argument("dataset", help="Path to dataset JSON file")
    parser.add_argument("--output", "-o", help="Output file for report")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--parallel", action="store_true", help="Run in parallel")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    # Load dataset
    dataset = EvalDataset.from_file(args.dataset)

    # Configure
    config = EvalConfig(
        parallel=args.parallel,
        verbose=args.verbose,
    )

    # Run (mock mode without LLM/agent)
    report = await run_evaluation(dataset, config=config)

    # Output
    output = report.to_markdown() if args.format == "markdown" else report.to_json()

    if args.output:
        with open(args.output, "w") as f:  # noqa: ASYNC230
            f.write(output)
    else:
        print(output)

    # Exit with error if failed
    return 0 if report.is_passing() else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
