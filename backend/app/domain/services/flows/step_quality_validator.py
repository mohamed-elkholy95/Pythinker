"""Step quality validator (2026-02-13 agent robustness plan Phase 2)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.plan import Step
    from app.domain.models.request_contract import RequestContract

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BANNED_VERBS = frozenset({"handle", "do", "process", "finalize", "consolidate"})


def validate_step_quality(
    step: Step,
    contract: RequestContract | None = None,
) -> tuple[bool, list[str]]:
    """Validate step naming quality. Deterministic, no LLM.

    Returns:
        (passed, list of violation messages)
    """
    violations: list[str] = []
    settings = get_settings()
    if not settings.enable_structured_step_model:
        return True, []

    # Check action_verb
    verb = (step.action_verb or "").strip().lower()
    if not verb:
        violations.append("empty_verb")
    elif verb in BANNED_VERBS:
        violations.append("banned_verb")

    # Check target_object
    target = (step.target_object or "").strip()
    if not target and step.description:
        violations.append("empty_target")

    # Check locked entity presence (advisory)
    if contract and contract.locked_entities and target:
        target_lower = target.lower()
        has_entity = any(e.lower() in target_lower for e in contract.locked_entities)
        if not has_entity:
            violations.append("missing_locked_entity")

    passed = len(violations) == 0
    return passed, violations


def repair_step_from_description(step: Step) -> Step:
    """Attempt to fill structured fields from description via regex."""
    desc = (step.description or "").strip()
    if not desc:
        return step

    updates: dict[str, str | None] = {}
    # Common pattern: "Verb noun phrase" e.g. "Search for Python docs"
    verb_match = re.match(r"^(\w+)\s+(?:for\s+)?(.+)$", desc, re.IGNORECASE)
    if verb_match:
        if not step.action_verb:
            updates["action_verb"] = verb_match.group(1).strip()
        if not step.target_object:
            updates["target_object"] = verb_match.group(2).strip()

    # Fallback: first word as verb, rest as target
    if "action_verb" not in updates and "target_object" not in updates:
        parts = desc.split(maxsplit=1)
        if parts and not step.action_verb:
            updates["action_verb"] = parts[0]
        if len(parts) > 1 and not step.target_object:
            updates["target_object"] = parts[1]

    if updates:
        return step.model_copy(update=updates)
    return step
