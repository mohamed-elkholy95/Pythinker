"""GEPA-compatible scoring service for optimization cases.

Computes a weighted scalar score (0..1) and a human-readable feedback string
that GEPA uses as a training signal.  The score is composite:

Planner:
  0.45 * deterministic_structure
  0.35 * llm_plan_quality         (placeholder when LLM judge disabled)
  0.20 * tool_feasibility

Execution:
  0.30 * deterministic_constraints
  0.30 * llm_response_quality     (placeholder when LLM judge disabled)
  0.20 * hallucination_check
  0.10 * latency_score
  0.10 * token_efficiency

The scorer is intentionally *pure* (no I/O) so it can be called from DSPy
metric functions inside dspy.Evaluate or GEPA compile loops.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.domain.models.prompt_optimization import OptimizationCase, OptimizationScore
from app.domain.models.prompt_profile import PromptTarget

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _contains_all(text: str, required: list[str]) -> float:
    """Fraction of required strings present in text (case-insensitive)."""
    if not required:
        return 1.0
    hits = sum(1 for s in required if s.lower() in text.lower())
    return hits / len(required)


def _contains_none(text: str, forbidden: list[str]) -> float:
    """1.0 if none of the forbidden strings appear, else 0.0."""
    for s in forbidden:
        if s.lower() in text.lower():
            return 0.0
    return 1.0


def _tool_recall(called: list[str], required: list[str]) -> float:
    """Fraction of required tools that appear in the called list."""
    if not required:
        return 1.0
    called_set = {t.lower() for t in called}
    hits = sum(1 for t in required if t.lower() in called_set)
    return hits / len(required)


def _citation_score(text: str, min_citations: int) -> float:
    """Estimate citation presence.  Looks for URL-like patterns or bracketed refs."""
    if min_citations == 0:
        return 1.0
    url_count = len(re.findall(r"https?://\S+", text))
    bracket_count = len(re.findall(r"\[\d+\]", text))
    found = url_count + bracket_count
    return min(1.0, found / max(1, min_citations))


def _step_count_score(step_count: int, min_steps: int, max_steps: int) -> float:
    """Score for correct step count range."""
    if min_steps == 0 and max_steps == 0:
        return 1.0
    if min_steps > 0 and step_count < min_steps:
        deficit = (min_steps - step_count) / min_steps
        return max(0.0, 1.0 - deficit)
    if max_steps > 0 and step_count > max_steps:
        excess = (step_count - max_steps) / max(1, max_steps)
        return max(0.0, 1.0 - excess * 0.5)
    return 1.0


# ---------------------------------------------------------------------------
# Planner scoring
# ---------------------------------------------------------------------------


def _score_planner(
    case: OptimizationCase,
    output: dict[str, Any],
) -> OptimizationScore:
    """Compute planner score from structured plan output.

    Args:
        case:   The optimization case with expected constraints.
        output: Dict with keys like ``steps`` (list of step dicts) and
                ``available_tools`` (list of tool names).
    """
    feedback_parts: list[str] = []
    components: dict[str, float] = {}

    steps = output.get("steps", [])
    step_count = len(steps)
    expected = case.expected

    # --- Deterministic structure (0.45) ---
    structure_parts: list[float] = []

    # Step count within bounds
    step_score = _step_count_score(step_count, expected.min_steps, expected.max_steps)
    structure_parts.append(step_score)
    if step_score < 1.0:
        if expected.min_steps > 0 and step_count < expected.min_steps:
            feedback_parts.append(f"Plan has too few steps ({step_count} < {expected.min_steps}).")
        elif expected.max_steps > 0 and step_count > expected.max_steps:
            feedback_parts.append(f"Plan has too many steps ({step_count} > {expected.max_steps}).")

    # All steps have non-empty descriptions
    non_empty = sum(1 for s in steps if s.get("description", s.get("name", "")).strip()) / max(1, step_count)
    structure_parts.append(non_empty)
    if non_empty < 1.0:
        feedback_parts.append("Some steps are missing descriptions.")

    deterministic_structure = sum(structure_parts) / max(1, len(structure_parts))
    components["deterministic_structure"] = deterministic_structure

    # --- Tool feasibility (0.20) ---
    available_tools = set(case.input.available_tools)
    if available_tools:
        steps_flat = " ".join(s.get("tool", s.get("description", "")) for s in steps).lower()
        feasibility_hits = sum(1 for t in available_tools if t.lower() in steps_flat)
        tool_feasibility = feasibility_hits / max(1, len(available_tools)) if available_tools else 1.0
    else:
        tool_feasibility = 1.0
    components["tool_feasibility"] = tool_feasibility
    if tool_feasibility < 0.6:
        feedback_parts.append("Plan references tools not in the available set.")

    # --- LLM plan quality placeholder (0.35) ---
    # In a full deployment this is computed by the LLMJudge grader.
    # We use a proxy: presence of non-trivial step descriptions.
    avg_desc_len = (
        sum(len(s.get("description", s.get("name", ""))) for s in steps) / max(1, step_count) if step_count > 0 else 0
    )
    llm_plan_quality = min(1.0, avg_desc_len / 80.0)  # 80 chars = ~1.0
    components["llm_plan_quality"] = llm_plan_quality
    if llm_plan_quality < 0.5:
        feedback_parts.append("Step descriptions are too short to be actionable.")

    score = 0.45 * deterministic_structure + 0.35 * llm_plan_quality + 0.20 * tool_feasibility

    if not feedback_parts:
        feedback_parts.append("Plan meets all structural and feasibility constraints.")

    return OptimizationScore(
        score=round(min(1.0, max(0.0, score)), 4),
        feedback=" ".join(feedback_parts),
        components=components,
    )


# ---------------------------------------------------------------------------
# Execution scoring
# ---------------------------------------------------------------------------


def _score_execution(
    case: OptimizationCase,
    output: dict[str, Any],
) -> OptimizationScore:
    """Compute execution score from agent response output.

    Args:
        case:   The optimization case with expected constraints.
        output: Dict with keys like ``response_text``, ``tools_called``
                (list of tool names), ``latency_ms``, ``token_count``.
    """
    feedback_parts: list[str] = []
    components: dict[str, float] = {}

    response_text = output.get("response_text", output.get("content", ""))
    tools_called = output.get("tools_called", [])
    latency_ms = output.get("latency_ms", 0.0)
    token_count = output.get("token_count", 0)
    expected = case.expected

    # --- Deterministic constraints (0.30) ---
    content_score = _contains_all(response_text, expected.must_contain)
    forbidden_score = _contains_none(response_text, expected.must_not_contain)
    tool_recall = _tool_recall(tools_called, expected.must_call_tools)
    citation_score = _citation_score(response_text, expected.min_citations)

    det_components = [content_score, forbidden_score, tool_recall, citation_score]
    deterministic_constraints = sum(det_components) / len(det_components)
    components["deterministic_constraints"] = deterministic_constraints

    if content_score < 1.0:
        missing = [s for s in expected.must_contain if s.lower() not in response_text.lower()]
        feedback_parts.append(f"Missing required content: {missing!r}.")
    if forbidden_score < 1.0:
        present = [s for s in expected.must_not_contain if s.lower() in response_text.lower()]
        feedback_parts.append(f"Contains forbidden content: {present!r}.")
    if tool_recall < 1.0:
        missing_tools = [t for t in expected.must_call_tools if t.lower() not in {x.lower() for x in tools_called}]
        feedback_parts.append(f"Missing required tool calls: {missing_tools!r}.")
    if citation_score < 1.0:
        feedback_parts.append(f"Insufficient citations (need ≥{expected.min_citations}).")

    # --- LLM response quality placeholder (0.30) ---
    # Proxy: response length and structural richness.
    resp_len = len(response_text)
    llm_response_quality = min(1.0, resp_len / 400.0)
    components["llm_response_quality"] = llm_response_quality
    if llm_response_quality < 0.3:
        feedback_parts.append("Response is too short to be informative.")

    # --- Hallucination check (0.20) — light proxy, full check via LLMJudge ---
    fabricated_signals = ["I believe", "I think", "as far as I know", "I'm not sure but"]
    hallucination_check = _contains_none(response_text, fabricated_signals)
    components["hallucination_check"] = hallucination_check
    if hallucination_check < 1.0:
        feedback_parts.append("Response contains hedging language that may indicate hallucination.")

    # --- Latency score (0.10) ---
    # Penalise if latency > 30s; use neutral 0.8 when no data
    latency_score = max(0.0, 1.0 - latency_ms / 30000.0) if latency_ms > 0 else 0.8
    components["latency_score"] = latency_score

    # --- Token efficiency (0.10) ---
    # Penalise very high token counts (>4000 tokens for a step response)
    token_efficiency = max(0.0, 1.0 - token_count / 4000.0) if token_count > 0 else 0.8
    components["token_efficiency"] = token_efficiency

    score = (
        0.30 * deterministic_constraints
        + 0.30 * llm_response_quality
        + 0.20 * hallucination_check
        + 0.10 * latency_score
        + 0.10 * token_efficiency
    )

    if not feedback_parts:
        feedback_parts.append("Response satisfies all constraints.")

    return OptimizationScore(
        score=round(min(1.0, max(0.0, score)), 4),
        feedback=" ".join(feedback_parts),
        components=components,
    )


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


class OptimizationScorer:
    """Stateless scorer for planner and execution optimization cases.

    Used both offline (inside the DSPy metric function) and online
    (shadow mode delta computation).
    """

    def score(
        self,
        case: OptimizationCase,
        output: dict[str, Any],
    ) -> OptimizationScore:
        """Dispatch to the appropriate scorer based on case target."""
        if case.target == PromptTarget.PLANNER:
            return _score_planner(case, output)
        if case.target == PromptTarget.EXECUTION:
            return _score_execution(case, output)
        # system prompts: use execution scorer as a proxy
        return _score_execution(case, output)

    def score_planner_case(
        self,
        case: OptimizationCase,
        output: dict[str, Any],
    ) -> OptimizationScore:
        return _score_planner(case, output)

    def score_execution_case(
        self,
        case: OptimizationCase,
        output: dict[str, Any],
    ) -> OptimizationScore:
        return _score_execution(case, output)
