"""Smoke tests for Phase 4: Prompt variant generation and Thompson-sampling feedback loop.

Prior bugs:
1. get_best_variant() required MIN_TRIALS=5; fresh auto-generated variants always returned None.
2. plan_act never called record_outcome(), so the bandit could never learn.

Fixes:
- get_best_variant() now accepts min_trials=0 for the bootstrap phase.
- plan_act tracks _selected_prompt_variant_id and calls record_outcome() at COMPLETED/ERROR.
"""

import pytest

from app.domain.services.agents.learning.prompt_optimizer import (
    PromptOptimizer,
    PromptOutcome,
)


@pytest.fixture
def optimizer() -> PromptOptimizer:
    """Fresh PromptOptimizer instance for each test."""
    return PromptOptimizer()


def test_auto_generate_variants_creates_three_variants(optimizer: PromptOptimizer):
    """auto_generate_variants() registers exactly num_variants variants."""
    base_prompt = "You are a helpful planning agent."
    variants = optimizer.auto_generate_variants("planner", base_prompt, num_variants=3)
    assert len(variants) == 3
    assert all(v.prompt_template != base_prompt for v in variants), (
        "Each auto-generated variant must differ from the base prompt"
    )


def test_auto_generate_variants_is_idempotent(optimizer: PromptOptimizer):
    """Calling auto_generate_variants() twice does not create duplicate variants."""
    base = "Plan carefully."
    optimizer.auto_generate_variants("planner", base)
    optimizer.auto_generate_variants("planner", base)

    all_variants = list(optimizer._variants.get("planner", {}).values())
    ids = [v.variant_id for v in all_variants]
    assert len(ids) == len(set(ids)), "Duplicate variant IDs found after two calls"


def test_get_best_variant_with_min_trials_zero_returns_variant(optimizer: PromptOptimizer):
    """get_best_variant() with min_trials=0 selects from fresh zero-trial variants.

    This tests the bootstrap-phase fix: previously min_trials defaulted to 5,
    making every fresh auto-generated variant ineligible.
    """
    optimizer.auto_generate_variants("planner", "Base prompt", num_variants=3)

    variant = optimizer.get_best_variant("planner", min_trials=0)
    assert variant is not None, (
        "get_best_variant(min_trials=0) should return a variant even when trials=0"
    )
    assert variant.prompt_template != ""


def test_get_best_variant_default_min_trials_filters_fresh_variants(optimizer: PromptOptimizer):
    """Verify that default MIN_TRIALS still filters fresh variants (guards against regression)."""
    optimizer.auto_generate_variants("planner", "Base", num_variants=3)
    # Default MIN_TRIALS=5; fresh variants have 0 trials → should return None
    variant = optimizer.get_best_variant("planner")  # uses MIN_TRIALS=5
    assert variant is None, (
        "Default get_best_variant() should still require MIN_TRIALS trials"
    )


def test_record_outcome_increments_trial_count(optimizer: PromptOptimizer):
    """record_outcome() increments total_trials on the referenced variant."""
    variants = optimizer.auto_generate_variants("planner", "Base", num_variants=1)
    v = variants[0]
    assert v.total_trials == 0

    optimizer.record_outcome(
        "planner",
        PromptOutcome(variant_id=v.variant_id, success=True),
    )
    assert v.total_trials == 1
    assert v.success_count == 1


def test_record_outcome_failure_increments_beta(optimizer: PromptOptimizer):
    """Recording a failure increases beta (penalises the variant in Thompson sampling)."""
    variants = optimizer.auto_generate_variants("planner", "Base", num_variants=1)
    v = variants[0]
    initial_beta = v.beta

    optimizer.record_outcome(
        "planner",
        PromptOutcome(variant_id=v.variant_id, success=False),
    )
    assert v.beta > initial_beta


def test_bandit_learns_after_bootstrap(optimizer: PromptOptimizer):
    """After MIN_TRIALS outcomes are recorded, get_best_variant() returns the winner."""
    optimizer.auto_generate_variants("planner", "Base", num_variants=2)
    variants = list(optimizer._variants["planner"].values())
    winner = variants[0]
    loser = variants[1]

    # Give the winner 5 successes
    for _ in range(5):
        optimizer.record_outcome(
            "planner",
            PromptOutcome(variant_id=winner.variant_id, success=True),
        )

    # Give the loser 5 failures
    for _ in range(5):
        optimizer.record_outcome(
            "planner",
            PromptOutcome(variant_id=loser.variant_id, success=False),
        )

    # With default MIN_TRIALS=5, both now have 5 trials — winner should win
    best = optimizer.get_best_variant("planner")
    assert best is not None
    assert best.variant_id == winner.variant_id, (
        "Bandit should select the variant with higher success rate after MIN_TRIALS"
    )


def test_record_outcome_noop_for_unknown_variant(optimizer: PromptOptimizer):
    """record_outcome() silently ignores unknown variant IDs (no crash)."""
    optimizer.auto_generate_variants("planner", "Base", num_variants=1)
    # Should not raise
    optimizer.record_outcome(
        "planner",
        PromptOutcome(variant_id="does-not-exist", success=True),
    )


def test_record_outcome_noop_for_unknown_category(optimizer: PromptOptimizer):
    """record_outcome() silently ignores unknown categories (no crash)."""
    optimizer.record_outcome(
        "nonexistent_category",
        PromptOutcome(variant_id="any-id", success=True),
    )
