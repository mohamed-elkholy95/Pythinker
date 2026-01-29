"""Evaluation Infrastructure for Agent Testing.

This module provides a comprehensive evaluation framework for testing
and benchmarking AI agents, prompts, and LLM outputs. Key components:

- EvalRunner: Main entry point for running evaluations
- EvalCase: Individual test cases with inputs and expected outputs
- EvalDataset: Collections of test cases
- EvalMetrics: Scoring functions and quality metrics
- EvalReport: Results aggregation and reporting

The framework supports:
- Automated regression testing of prompts
- Quality benchmarking of agent outputs
- A/B testing of different configurations
- CI/CD integration for continuous evaluation

Example usage:
    from tests.evals import EvalRunner, EvalDataset, EvalCase

    # Create test cases
    dataset = EvalDataset(
        name="basic_qa",
        cases=[
            EvalCase(
                id="greeting",
                input="Hello, how are you?",
                expected_output_contains=["hello", "hi"],
            ),
        ]
    )

    # Run evaluation
    runner = EvalRunner(llm=llm, agent=agent)
    report = await runner.run(dataset)

    # Check results
    assert report.pass_rate >= 0.9
"""

from tests.evals.eval_runner import (
    EvalRunner,
    run_evaluation,
)
from tests.evals.metrics import (
    BaseMetric,
    ContainsMetric,
    ExactMatchMetric,
    JsonSchemaMetric,
    ResponseTimeMetric,
    SimilarityMetric,
    TokenCountMetric,
    ToolCallMetric,
    get_metric,
    register_metric,
)
from tests.evals.types import (
    EvalCase,
    EvalConfig,
    EvalDataset,
    EvalReport,
    EvalResult,
    MetricScore,
)

__all__ = [
    # Types
    "EvalCase",
    "EvalResult",
    "EvalDataset",
    "EvalConfig",
    "EvalReport",
    "MetricScore",
    # Runner
    "EvalRunner",
    "run_evaluation",
    # Metrics
    "BaseMetric",
    "ExactMatchMetric",
    "ContainsMetric",
    "SimilarityMetric",
    "JsonSchemaMetric",
    "ToolCallMetric",
    "ResponseTimeMetric",
    "TokenCountMetric",
    "get_metric",
    "register_metric",
]
