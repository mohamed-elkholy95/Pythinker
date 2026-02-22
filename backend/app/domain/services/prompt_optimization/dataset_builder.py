"""Dataset builder for DSPy/GEPA prompt optimization.

Produces a normalized list of ``OptimizationCase`` objects from two sources:
1. **Curated eval cases** — hand-crafted JSON in
   ``backend/tests/evals/datasets/prompt_optimization_cases.json``.
2. **Historical sessions** — mined from event-sourced MongoDB session events
   (``MessageEvent``, ``StepEvent``, ``ToolEvent``).

The combined dataset is then split deterministically into train/val/test
subsets (70/20/10) stratified by target and difficulty.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pathlib
from typing import Any

from app.domain.models.prompt_optimization import (
    CaseSplit,
    OptimizationCase,
    OptimizationCaseExpected,
    OptimizationCaseInput,
)
from app.domain.models.prompt_profile import PromptTarget

logger = logging.getLogger(__name__)

# Path to the bundled curated dataset (relative to this file's package root).
_CURATED_DATASET_PATH = (
    pathlib.Path(__file__).resolve().parents[4]  # backend/
    / "tests"
    / "evals"
    / "datasets"
    / "prompt_optimization_cases.json"
)

_SPLIT_RATIOS = {"train": 0.70, "val": 0.20, "test": 0.10}


def _case_split(case_id: str, target: str, difficulty: str, seed: int = 42) -> CaseSplit:
    """Deterministic stratified split assignment.

    Uses a hash of (case_id + target + difficulty + seed) modulo 100 to
    assign cases to splits.  Determinism guarantees reproducibility across
    optimization runs even as the dataset grows.
    """
    key = f"{case_id}:{target}:{difficulty}:{seed}"
    digest = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100  # noqa: S324
    if digest < 70:
        return CaseSplit.TRAIN
    if digest < 90:
        return CaseSplit.VAL
    return CaseSplit.TEST


def load_curated_cases(path: pathlib.Path | None = None) -> list[OptimizationCase]:
    """Load and parse the curated eval dataset JSON."""
    dataset_path = path or _CURATED_DATASET_PATH
    if not dataset_path.exists():
        logger.warning("Curated dataset not found at %s — skipping", dataset_path)
        return []

    with dataset_path.open() as fh:
        raw = json.load(fh)

    cases: list[OptimizationCase] = []
    for item in raw.get("cases", []):
        try:
            target = PromptTarget(item["target"])
            difficulty = item.get("metadata", {}).get("difficulty", "medium")
            split = _case_split(item["id"], item["target"], difficulty)

            inp = item.get("input", {})
            exp = item.get("expected", {})

            case = OptimizationCase(
                id=item["id"],
                target=target,
                input=OptimizationCaseInput(
                    user_request=inp.get("user_request", ""),
                    step_description=inp.get("step_description", ""),
                    available_tools=inp.get("available_tools", []),
                    attachments=inp.get("attachments", []),
                ),
                expected=OptimizationCaseExpected(
                    must_call_tools=exp.get("must_call_tools", []),
                    must_contain=exp.get("must_contain", []),
                    must_not_contain=exp.get("must_not_contain", []),
                    min_citations=exp.get("min_citations", 0),
                    min_steps=exp.get("min_steps", 0),
                    max_steps=exp.get("max_steps", 0),
                ),
                labels=item.get("labels", {}),
                metadata={**item.get("metadata", {}), "source": "curated"},
                split=split,
            )
            cases.append(case)
        except Exception as exc:
            logger.warning("Skipping malformed curated case %s: %s", item.get("id", "?"), exc)

    logger.info("Loaded %d curated optimization cases from %s", len(cases), dataset_path)
    return cases


def extract_cases_from_session_events(session_events: list[dict[str, Any]]) -> list[OptimizationCase]:
    """Mine optimization cases from a session's event stream.

    Extracts ``(user_request, step, tools_called)`` tuples from:
    - ``MessageEvent`` (user sender) → input.user_request
    - ``StepEvent(completed)`` → step description + execution target cases
    - ``ToolEvent`` → tool usage evidence
    - ``PlanEvent`` → planner target cases

    Args:
        session_events: Raw event dicts from MongoDB (deserialized from BSON).

    Returns:
        List of ``OptimizationCase`` objects, split not yet assigned.
    """
    cases: list[OptimizationCase] = []

    user_request = ""
    tool_calls_in_step: list[str] = []
    current_step_desc = ""

    for event in session_events:
        ev_type = event.get("type", "")

        if ev_type == "message" and event.get("sender") == "user":
            user_request = event.get("content", "")
            tool_calls_in_step = []

        elif ev_type == "plan" and event.get("status") == "created":
            plan_data = event.get("plan", {})
            steps = plan_data.get("steps", [])
            if user_request and steps:
                case = OptimizationCase(
                    target=PromptTarget.PLANNER,
                    input=OptimizationCaseInput(
                        user_request=user_request,
                        available_tools=[],
                    ),
                    expected=OptimizationCaseExpected(
                        min_steps=max(1, len(steps) - 1),
                        max_steps=len(steps) + 3,
                    ),
                    metadata={"source": "session", "session_id": event.get("session_id", "")},
                    source_session_id=event.get("session_id"),
                )
                cases.append(case)

        elif ev_type == "step" and event.get("status") == "started":
            step_data = event.get("step", {})
            current_step_desc = step_data.get("name", "")
            tool_calls_in_step = []

        elif ev_type == "tool":
            tool_name = event.get("tool_name", "")
            if tool_name:
                tool_calls_in_step.append(tool_name)

        elif ev_type == "step" and event.get("status") == "completed":
            step_data = event.get("step", {})
            if user_request and current_step_desc and tool_calls_in_step:
                case = OptimizationCase(
                    target=PromptTarget.EXECUTION,
                    input=OptimizationCaseInput(
                        user_request=user_request,
                        step_description=current_step_desc,
                        # available_tools left empty for session-derived cases
                        # (we only know what tools were called, not the full inventory)
                        available_tools=[],
                    ),
                    expected=OptimizationCaseExpected(
                        must_call_tools=list(set(tool_calls_in_step)),
                    ),
                    metadata={"source": "session", "session_id": event.get("session_id", "")},
                    source_session_id=event.get("session_id"),
                )
                cases.append(case)
            tool_calls_in_step = []
            current_step_desc = ""

    return cases


class DatasetBuilder:
    """Builds and manages the optimization dataset."""

    def __init__(
        self,
        curated_path: pathlib.Path | None = None,
        split_seed: int = 42,
    ) -> None:
        self._curated_path = curated_path
        self._split_seed = split_seed

    def build_from_curated(self) -> list[OptimizationCase]:
        """Load curated dataset only."""
        return load_curated_cases(self._curated_path)

    def build_from_sessions(
        self,
        all_session_events: list[list[dict[str, Any]]],
    ) -> list[OptimizationCase]:
        """Extract cases from a list of session event streams."""
        cases: list[OptimizationCase] = []
        for events in all_session_events:
            cases.extend(extract_cases_from_session_events(events))
        # Assign splits
        for case in cases:
            difficulty = case.metadata.get("difficulty", "medium")
            case.split = _case_split(case.id, case.target.value, str(difficulty), self._split_seed)
        return cases

    def build_combined(
        self,
        all_session_events: list[list[dict[str, Any]]] | None = None,
    ) -> list[OptimizationCase]:
        """Build combined curated + session-derived dataset."""
        cases = self.build_from_curated()
        if all_session_events:
            session_cases = self.build_from_sessions(all_session_events)
            cases.extend(session_cases)
        return cases

    def split(
        self,
        cases: list[OptimizationCase],
        target: PromptTarget | None = None,
    ) -> dict[CaseSplit, list[OptimizationCase]]:
        """Return a split→cases mapping, optionally filtered by target."""
        filtered = [c for c in cases if target is None or c.target == target]
        result: dict[CaseSplit, list[OptimizationCase]] = {
            CaseSplit.TRAIN: [],
            CaseSplit.VAL: [],
            CaseSplit.TEST: [],
        }
        for case in filtered:
            result[case.split].append(case)
        logger.info(
            "Dataset split for target=%s: train=%d val=%d test=%d",
            target.value if target else "all",
            len(result[CaseSplit.TRAIN]),
            len(result[CaseSplit.VAL]),
            len(result[CaseSplit.TEST]),
        )
        return result
