"""Offline DSPy/GEPA optimizer orchestrator.

Orchestrates a full optimization run:
  1. Load dataset (curated + session-mined cases).
  2. Split into train/val/test.
  3. Convert to dspy.Example objects.
  4. Configure DSPy LM (wrapping the configured Pythinker LLM settings).
  5. Run MIPROv2 (baseline) or GEPA optimizer.
  6. Evaluate on val set to compute baseline vs optimized scores.
  7. Serialize the optimized program.
  8. Return a structured RunResult with scores and the serialized artifact.

DSPy and all heavy deps are optional — the module guards their import so
the runtime API container does not need them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.domain.models.prompt_optimization import (
    CaseSplit,
    OptimizerType,
)
from app.domain.models.prompt_profile import PromptTarget
from app.domain.services.prompt_optimization.dataset_builder import DatasetBuilder
from app.domain.services.prompt_optimization.dspy_adapter import (
    ExecutionProgram,
    PlannerProgram,
    build_gepa_metric,
    cases_to_dspy_examples,
)
from app.domain.services.prompt_optimization.scoring import OptimizationScorer

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Result of a single optimizer invocation."""

    target: PromptTarget
    optimizer: OptimizerType
    baseline_score: float
    optimized_score: float
    train_count: int
    val_count: int
    test_count: int
    artifact_bytes: bytes  # JSON-serialized optimized DSPy program
    duration_seconds: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def improvement(self) -> float:
        return self.optimized_score - self.baseline_score


def _configure_dspy_lm(
    api_key: str,
    api_base: str,
    model_name: str,
) -> None:
    """Configure DSPy's global language model."""
    try:
        import dspy  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("dspy is required for optimization. Install dspy-ai.") from exc

    lm = dspy.LM(
        model=f"openai/{model_name}",
        api_key=api_key,
        api_base=api_base,
    )
    dspy.configure(lm=lm)
    logger.info("DSPy LM configured: %s @ %s", model_name, api_base)


def _make_scalar_metric(metric: Any) -> Any:
    """Wrap a GEPA metric (returns dspy.Prediction) into a scalar metric for dspy.Evaluate.

    dspy.Evaluate expects metrics that return a float or bool, but GEPA metrics
    return dspy.Prediction(score=..., feedback=...).  This wrapper extracts the
    scalar score so both evaluation and optimization can share the same metric.
    """

    def _scalar(example: Any, prediction: Any, trace: Any = None) -> float:
        result = metric(example, prediction, trace)
        if isinstance(result, (int, float)):
            return float(result)
        if hasattr(result, "score"):
            return float(result.score)
        return 0.0

    return _scalar


def _evaluate_program(
    program: Any,
    examples: list[Any],
    metric: Any,
) -> float:
    """Evaluate a DSPy program on examples, returning mean score."""
    try:
        import dspy  # type: ignore[import]

        scalar_metric = _make_scalar_metric(metric)
        evaluator = dspy.Evaluate(devset=examples, metric=scalar_metric, num_threads=1, display_progress=False)
        result = evaluator(program)
        if isinstance(result, (int, float)):
            return float(result)
        if hasattr(result, "score"):
            return float(result.score)
        return 0.0
    except Exception as exc:
        logger.warning("Evaluation failed: %s", exc)
        return 0.0


def _run_miprov2(
    program: Any,
    trainset: list[Any],
    valset: list[Any],
    metric: Any,
    auto: str = "light",
) -> Any:
    """Run MIPROv2 optimizer and return the optimized program."""
    try:
        from dspy.teleprompt import MIPROv2  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("dspy.teleprompt.MIPROv2 not found. Install dspy-ai>=2.4.") from exc

    optimizer = MIPROv2(metric=metric, auto=auto, verbose=False)
    return optimizer.compile(program, trainset=trainset, valset=valset)


def _run_gepa(
    program: Any,
    trainset: list[Any],
    valset: list[Any],
    metric: Any,
) -> Any:
    """Run GEPA optimizer and return the optimized program."""
    try:
        from dspy.teleprompt import GEPA  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("dspy.teleprompt.GEPA not found. Install dspy-ai>=2.5.") from exc

    optimizer = GEPA(metric=metric, verbose=False)
    return optimizer.compile(program, trainset=trainset, valset=valset)


def run_optimization(
    target: PromptTarget,
    optimizer_type: OptimizerType,
    api_key: str,
    api_base: str,
    model_name: str,
    all_session_events: list[list[dict[str, Any]]] | None = None,
    miprov2_auto: str = "light",
    split_seed: int = 42,
) -> RunResult:
    """Run a full offline optimization for the given target.

    Args:
        target:             Which prompt surface to optimize.
        optimizer_type:     GEPA or MIPROv2.
        api_key:            LLM API key for DSPy.
        api_base:           LLM API base URL.
        model_name:         LLM model name for DSPy calls.
        all_session_events: Optional list of session event streams for dataset mining.
        miprov2_auto:       "light" | "medium" | "heavy" for MIPROv2 search depth.
        split_seed:         Seed for deterministic train/val/test splits.

    Returns:
        ``RunResult`` with scores and serialized optimized program.
    """
    start = time.monotonic()
    logger.info("Starting %s optimization for target=%s", optimizer_type.value, target.value)

    # 1. Build dataset
    builder = DatasetBuilder(split_seed=split_seed)
    cases = builder.build_combined(all_session_events)
    split_map = builder.split(cases, target=target)

    trainset_cases = split_map[CaseSplit.TRAIN]
    valset_cases = split_map[CaseSplit.VAL]
    testset_cases = split_map[CaseSplit.TEST]

    logger.info(
        "Dataset: train=%d val=%d test=%d",
        len(trainset_cases),
        len(valset_cases),
        len(testset_cases),
    )

    if len(trainset_cases) < 5:
        raise ValueError(
            f"Insufficient training cases for target={target.value}: "
            f"need ≥5, got {len(trainset_cases)}. "
            "Add more cases to tests/evals/datasets/prompt_optimization_cases.json."
        )

    # 2. Convert to dspy.Example
    trainset = cases_to_dspy_examples(trainset_cases)
    valset = cases_to_dspy_examples(valset_cases)

    # 3. Configure DSPy LM
    _configure_dspy_lm(api_key=api_key, api_base=api_base, model_name=model_name)

    # 4. Build program and metric
    scorer = OptimizationScorer()
    metric = build_gepa_metric(scorer, target)

    program = PlannerProgram.build() if target == PromptTarget.PLANNER else ExecutionProgram.build()

    # 5. Evaluate baseline
    logger.info("Evaluating baseline program...")
    baseline_score = _evaluate_program(program, valset or trainset[:10], metric)
    logger.info("Baseline score: %.4f", baseline_score)

    # 6. Optimize
    logger.info("Running %s optimizer...", optimizer_type.value)
    if optimizer_type == OptimizerType.GEPA:
        optimized_program = _run_gepa(program, trainset, valset, metric)
    elif optimizer_type in (OptimizerType.MIPROV2, OptimizerType.MIPROV2_LIGHT):
        auto = "light" if optimizer_type == OptimizerType.MIPROV2_LIGHT else miprov2_auto
        optimized_program = _run_miprov2(program, trainset, valset, metric, auto=auto)
    else:
        raise ValueError(f"Unknown optimizer type: {optimizer_type}")

    # 7. Evaluate optimized
    logger.info("Evaluating optimized program...")
    optimized_score = _evaluate_program(optimized_program, valset or trainset[:10], metric)
    logger.info(
        "Optimized score: %.4f (improvement: %+.4f)",
        optimized_score,
        optimized_score - baseline_score,
    )

    # 8. Serialize artifact (DSPy uses file-based .save(), not .dumps())
    import pathlib
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = pathlib.Path(tmp.name)
    try:
        optimized_program.save(str(tmp_path))
        artifact_bytes = tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)

    duration = time.monotonic() - start
    logger.info(
        "%s optimization complete for %s in %.1fs",
        optimizer_type.value,
        target.value,
        duration,
    )

    return RunResult(
        target=target,
        optimizer=optimizer_type,
        baseline_score=baseline_score,
        optimized_score=optimized_score,
        train_count=len(trainset_cases),
        val_count=len(valset_cases),
        test_count=len(testset_cases),
        artifact_bytes=artifact_bytes,
        duration_seconds=duration,
    )
