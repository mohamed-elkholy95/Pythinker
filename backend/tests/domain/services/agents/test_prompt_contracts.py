"""Tests for prompt contract language used by agent prompts."""

from app.domain.services.agents.execution import SKILL_AWARENESS_PROMPT, SKILL_ENFORCEMENT_PROMPT
from app.domain.services.prompts.planner import ENHANCED_PLANNER_SYSTEM_PROMPT
from app.domain.services.prompts.verifier import VERIFIER_SYSTEM_PROMPT


def test_execution_skill_prompts_are_idempotent_and_active_skill_aware() -> None:
    assert "already active" in SKILL_AWARENESS_PROMPT
    assert "continue with the loaded instructions" in SKILL_AWARENESS_PROMPT
    assert "IDEMPOTENCE" in SKILL_ENFORCEMENT_PROMPT
    assert "unless that skill is already active" in SKILL_ENFORCEMENT_PROMPT


def test_planner_prompt_requires_clear_step_ownership_and_cross_validation() -> None:
    assert "Plan Shape" in ENHANCED_PLANNER_SYSTEM_PROMPT
    assert "one clear responsibility" in ENHANCED_PLANNER_SYSTEM_PROMPT
    assert "cross-validation step" in ENHANCED_PLANNER_SYSTEM_PROMPT
    assert "Handoff Discipline" in ENHANCED_PLANNER_SYSTEM_PROMPT


def test_verifier_prompt_is_adversarial_and_revision_biased_for_borderline_plans() -> None:
    assert "try to break the plan" in VERIFIER_SYSTEM_PROMPT
    assert "Adversarial Read" in VERIFIER_SYSTEM_PROMPT
    assert "prefer REVISE" in VERIFIER_SYSTEM_PROMPT
