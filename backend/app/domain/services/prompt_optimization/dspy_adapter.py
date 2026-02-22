"""DSPy program definitions for planner and execution prompt optimization.

This module wraps Pythinker's prompt builder functions as DSPy ``Signature``
and ``Module`` objects so that MIPROv2 and GEPA can optimize their
instructions and few-shot exemplars.

Design constraints:
- DSPy is an *optional* dependency (only installed in the offline optimizer
  environment, not the runtime API container).  All DSPy imports are guarded
  behind try/except so this module can be imported safely in runtime code.
- No I/O is performed here; LLM calls go through DSPy's LM abstraction.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.domain.models.prompt_optimization import OptimizationCase
from app.domain.models.prompt_profile import PromptTarget

if TYPE_CHECKING:
    pass  # dspy imports below are guarded

logger = logging.getLogger(__name__)

try:
    import dspy  # type: ignore[import]

    _DSPY_AVAILABLE = True
except ImportError:
    _DSPY_AVAILABLE = False
    logger.debug("dspy not installed — DSPy adapter is offline-only")


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


def _require_dspy() -> None:
    if not _DSPY_AVAILABLE:
        raise ImportError("DSPy is not installed. Install it with: pip install dspy-ai")


class PlannerSignature:
    """DSPy signature: user_request → plan_json.

    Wraps ``build_create_plan_prompt`` as a DSPy program surface.
    """

    @staticmethod
    def build() -> Any:
        _require_dspy()

        class _PlannerSig(dspy.Signature):
            """Generate a structured execution plan from the user request."""

            user_request: str = dspy.InputField(desc="The user's task or question")
            available_tools: str = dspy.InputField(desc="Comma-separated list of available tools")
            plan_json: str = dspy.OutputField(desc="JSON array of plan steps with name and description fields")

        return _PlannerSig


class ExecutionSignature:
    """DSPy signature: user_request + step_description → response."""

    @staticmethod
    def build() -> Any:
        _require_dspy()

        class _ExecutionSig(dspy.Signature):
            """Execute a single step of the agent plan."""

            user_request: str = dspy.InputField(desc="The overall user task or question")
            step_description: str = dspy.InputField(desc="The specific step to execute")
            available_tools: str = dspy.InputField(desc="Comma-separated list of available tools")
            response: str = dspy.OutputField(desc="The agent's response for this step")

        return _ExecutionSig


# ---------------------------------------------------------------------------
# DSPy Programs (Modules)
# ---------------------------------------------------------------------------


class PlannerProgram:
    """DSPy ChainOfThought program for planner optimization."""

    @staticmethod
    def build() -> Any:
        _require_dspy()
        sig = PlannerSignature.build()

        class _PlannerProgram(dspy.Module):
            def __init__(self) -> None:
                self.generate = dspy.ChainOfThought(sig)

            def forward(self, user_request: str, available_tools: str = "") -> Any:
                return self.generate(
                    user_request=user_request,
                    available_tools=available_tools,
                )

        return _PlannerProgram()


class ExecutionProgram:
    """DSPy ChainOfThought program for execution prompt optimization."""

    @staticmethod
    def build() -> Any:
        _require_dspy()
        sig = ExecutionSignature.build()

        class _ExecutionProgram(dspy.Module):
            def __init__(self) -> None:
                self.generate = dspy.ChainOfThought(sig)

            def forward(
                self,
                user_request: str,
                step_description: str = "",
                available_tools: str = "",
            ) -> Any:
                return self.generate(
                    user_request=user_request,
                    step_description=step_description,
                    available_tools=available_tools,
                )

        return _ExecutionProgram()


# ---------------------------------------------------------------------------
# Dataset conversion
# ---------------------------------------------------------------------------


def cases_to_dspy_examples(cases: list[OptimizationCase]) -> list[Any]:
    """Convert OptimizationCase objects to ``dspy.Example`` objects.

    Each example uses ``request_payload`` as the single input field,
    carrying a dict of all input values.

    Returns an empty list if DSPy is not installed (graceful offline guard).
    """
    if not _DSPY_AVAILABLE:
        return []

    examples = []
    for case in cases:
        payload = case.to_request_payload()
        ex = dspy.Example(
            request_payload=payload,
            expected_constraints=case.expected.model_dump(),
        ).with_inputs("request_payload")
        examples.append(ex)
    return examples


# ---------------------------------------------------------------------------
# GEPA metric factory
# ---------------------------------------------------------------------------


def build_gepa_metric(scorer: Any, target: PromptTarget) -> Any:
    """Build a GEPA-compatible metric function for the given target.

    The returned function satisfies the DSPy metric contract:
    ``metric(example, prediction, trace=None) -> dspy.Prediction``

    Args:
        scorer: An ``OptimizationScorer`` instance.
        target: Which prompt surface to score.

    Returns:
        A callable suitable for ``GEPA(metric=...).compile(...)`` or
        ``dspy.Evaluate(metric=...)``.
    """
    _require_dspy()
    from app.domain.services.prompt_optimization.scoring import OptimizationScorer

    if not isinstance(scorer, OptimizationScorer):
        raise TypeError("scorer must be an OptimizationScorer instance")

    def _metric(example: Any, prediction: Any, trace: Any = None) -> Any:
        """GEPA metric: returns dspy.Prediction(score=..., feedback=...)."""
        try:
            # Build a synthetic OptimizationCase from the example
            from app.domain.models.prompt_optimization import (
                OptimizationCase,
                OptimizationCaseExpected,
                OptimizationCaseInput,
            )

            payload = example.request_payload
            case = OptimizationCase(
                target=target,
                input=OptimizationCaseInput(
                    user_request=payload.get("user_request", ""),
                    step_description=payload.get("step_description", ""),
                    available_tools=payload.get("available_tools", []),
                ),
                expected=OptimizationCaseExpected(
                    **{
                        k: v
                        for k, v in example.get("expected_constraints", {}).items()
                        if k in OptimizationCaseExpected.model_fields
                    }
                ),
            )

            # Build output dict from prediction
            output: dict[str, Any] = {}
            if hasattr(prediction, "plan_json"):
                output["steps"] = prediction.plan_json
            if hasattr(prediction, "response"):
                output["response_text"] = prediction.response
            if hasattr(prediction, "tools_called"):
                output["tools_called"] = prediction.tools_called

            opt_score = scorer.score(case, output)
            return dspy.Prediction(score=opt_score.score, feedback=opt_score.feedback)
        except Exception as exc:
            logger.warning("GEPA metric computation failed: %s", exc)
            return dspy.Prediction(score=0.0, feedback=f"Metric error: {exc}")

    return _metric
