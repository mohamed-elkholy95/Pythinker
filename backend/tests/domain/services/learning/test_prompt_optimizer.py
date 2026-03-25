"""Unit tests for PromptOptimizer domain module.

Covers PromptVariant, PromptContext, PromptOutcome, PromptOptimizer,
and the module-level singleton helpers.

numpy is used by the production code (Thompson sampling), so no mocking
is needed for it — it is a direct dependency of the module.
"""

import pytest

from app.domain.services.agents.learning.prompt_optimizer import (
    PromptContext,
    PromptOptimizer,
    PromptOutcome,
    PromptVariant,
    get_prompt_optimizer,
    reset_prompt_optimizer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TMPL = "You are a helpful assistant. Task: {task}"


def _register(optimizer: PromptOptimizer, category: str = "planning", n: int = 1) -> list[str]:
    """Register n variants and return their IDs."""
    ids = []
    for i in range(n):
        vid = f"v{i}"
        optimizer.register_variant(category, vid, f"Template {i}", description=f"Variant {i}")
        ids.append(vid)
    return ids


def _outcome(variant_id: str, success: bool = True, **kw) -> PromptOutcome:
    return PromptOutcome(variant_id=variant_id, success=success, **kw)


# ---------------------------------------------------------------------------
# PromptVariant
# ---------------------------------------------------------------------------


class TestPromptVariant:
    def test_defaults(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        assert v.alpha == pytest.approx(1.0)
        assert v.beta == pytest.approx(1.0)
        assert v.total_trials == 0
        assert v.success_count == 0
        assert v.average_quality == pytest.approx(0.0)
        assert v.average_latency_ms == pytest.approx(0.0)
        assert v.is_active is True
        assert v.description == ""

    def test_success_rate_zero_trials(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        assert v.success_rate == pytest.approx(0.5)

    def test_success_rate_with_trials(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True)
        v.update(success=False)
        assert v.success_rate == pytest.approx(0.5)

    def test_update_success_increments_alpha(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True)
        assert v.alpha == pytest.approx(2.0)
        assert v.beta == pytest.approx(1.0)
        assert v.success_count == 1

    def test_update_failure_increments_beta(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=False)
        assert v.alpha == pytest.approx(1.0)
        assert v.beta == pytest.approx(2.0)
        assert v.success_count == 0

    def test_update_increments_total_trials(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True)
        v.update(success=False)
        assert v.total_trials == 2

    def test_update_quality_ema(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True, quality_score=1.0)
        # alpha=0.2: new_quality = 0.2 * 1.0 + 0.8 * 0.0
        assert v.average_quality == pytest.approx(0.2)

    def test_update_latency_ema(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True, latency_ms=500.0)
        assert v.average_latency_ms == pytest.approx(500.0 * 0.2)

    def test_update_without_quality_does_not_change_quality(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        v.update(success=True)
        assert v.average_quality == pytest.approx(0.0)

    def test_sample_value_returns_float_in_range(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        for _ in range(20):
            s = v.sample_value()
            assert 0.0 <= s <= 1.0

    def test_last_used_updated_on_update(self):
        v = PromptVariant(variant_id="v1", prompt_template=TMPL)
        before = v.last_used
        v.update(success=True)
        assert v.last_used >= before


# ---------------------------------------------------------------------------
# PromptContext
# ---------------------------------------------------------------------------


class TestPromptContext:
    def test_defaults(self):
        ctx = PromptContext(task_type="research")
        assert ctx.complexity == "medium"
        assert ctx.agent_type == "executor"
        assert ctx.additional_context == {}

    def test_custom_fields(self):
        ctx = PromptContext(
            task_type="planning",
            complexity="high",
            agent_type="planner",
            additional_context={"depth": 3},
        )
        assert ctx.task_type == "planning"
        assert ctx.complexity == "high"
        assert ctx.additional_context == {"depth": 3}


# ---------------------------------------------------------------------------
# PromptOutcome
# ---------------------------------------------------------------------------


class TestPromptOutcome:
    def test_minimal(self):
        o = PromptOutcome(variant_id="v1", success=True)
        assert o.quality_score is None
        assert o.latency_ms is None
        assert o.error is None
        assert o.metadata == {}

    def test_with_all_fields(self):
        o = PromptOutcome(
            variant_id="v1",
            success=False,
            quality_score=0.3,
            latency_ms=1200.0,
            error="timeout",
            metadata={"step": 2},
        )
        assert o.quality_score == pytest.approx(0.3)
        assert o.error == "timeout"
        assert o.metadata == {"step": 2}


# ---------------------------------------------------------------------------
# PromptOptimizer — construction
# ---------------------------------------------------------------------------


class TestPromptOptimizerInit:
    def test_starts_empty(self):
        opt = PromptOptimizer()
        stats = opt.get_exploration_stats()
        assert stats["total_selections"] == 0
        assert stats["categories"] == 0
        assert stats["variants_by_category"] == {}

    def test_constants(self):
        assert PromptOptimizer.MIN_TRIALS == 5
        assert pytest.approx(0.1) == PromptOptimizer.EXPLORATION_BONUS
        assert PromptOptimizer.MAX_VARIANTS == 10


# ---------------------------------------------------------------------------
# PromptOptimizer — register_variant
# ---------------------------------------------------------------------------


class TestRegisterVariant:
    def test_register_creates_variant(self):
        opt = PromptOptimizer()
        v = opt.register_variant("planning", "v1", TMPL, "a description")
        assert isinstance(v, PromptVariant)
        assert v.variant_id == "v1"
        assert v.prompt_template == TMPL
        assert v.description == "a description"

    def test_register_adds_to_category(self):
        opt = PromptOptimizer()
        opt.register_variant("planning", "v1", TMPL)
        stats = opt.get_exploration_stats()
        assert stats["categories"] == 1
        assert stats["variants_by_category"]["planning"] == 1

    def test_register_multiple_categories(self):
        opt = PromptOptimizer()
        opt.register_variant("planning", "v1", TMPL)
        opt.register_variant("execution", "v2", TMPL)
        stats = opt.get_exploration_stats()
        assert stats["categories"] == 2

    def test_register_same_id_overwrites(self):
        opt = PromptOptimizer()
        opt.register_variant("planning", "v1", "first template")
        opt.register_variant("planning", "v1", "second template")
        v = opt._variants["planning"]["v1"]
        assert v.prompt_template == "second template"
        assert opt.get_exploration_stats()["variants_by_category"]["planning"] == 1

    def test_pruning_when_max_variants_exceeded(self):
        opt = PromptOptimizer()
        # Fill up to MAX_VARIANTS (10)
        for i in range(PromptOptimizer.MAX_VARIANTS):
            opt.register_variant("cat", f"v{i}", f"t{i}")
        # One more should trigger pruning — final count stays at MAX_VARIANTS
        opt.register_variant("cat", "v_extra", "extra")
        assert opt.get_exploration_stats()["variants_by_category"]["cat"] == PromptOptimizer.MAX_VARIANTS


# ---------------------------------------------------------------------------
# PromptOptimizer — select_variant
# ---------------------------------------------------------------------------


class TestSelectVariant:
    def test_returns_none_for_unknown_category(self):
        opt = PromptOptimizer()
        assert opt.select_variant("nonexistent") is None

    def test_returns_none_when_all_deactivated(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.deactivate_variant("cat", "v1")
        assert opt.select_variant("cat") is None

    def test_returns_variant_instance(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        v = opt.select_variant("cat")
        assert isinstance(v, PromptVariant)

    def test_selection_recorded_in_history(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.select_variant("cat")
        assert opt.get_exploration_stats()["total_selections"] == 1

    def test_single_variant_always_selected(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        for _ in range(5):
            v = opt.select_variant("cat")
            assert v is not None
            assert v.variant_id == "v1"

    def test_exploration_bonus_favors_underexplored(self):
        """A variant with many trials competes against an unexplored one.

        With the EXPLORATION_BONUS applied to variants below MIN_TRIALS, the
        unexplored variant's sample is bumped by 0.1, making it competitive.
        We cannot guarantee it wins every time, but after enough draws the
        unexplored one must be selected at least once.
        """
        opt = PromptOptimizer()
        opt.register_variant("cat", "explored", TMPL)
        # Drive explored variant to high confidence so its samples are typically high
        for _ in range(20):
            opt._variants["cat"]["explored"].update(success=True)
        opt.register_variant("cat", "fresh", TMPL)

        selected_ids = {opt.select_variant("cat").variant_id for _ in range(30)}  # type: ignore[union-attr]
        assert "fresh" in selected_ids


# ---------------------------------------------------------------------------
# PromptOptimizer — record_outcome
# ---------------------------------------------------------------------------


class TestRecordOutcome:
    def test_unknown_category_is_ignored(self):
        opt = PromptOptimizer()
        opt.record_outcome("ghost", _outcome("v1"))  # must not raise

    def test_unknown_variant_id_is_ignored(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.record_outcome("cat", _outcome("ghost"))  # must not raise

    def test_success_updates_alpha(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.record_outcome("cat", _outcome("v1", success=True))
        v = opt._variants["cat"]["v1"]
        assert v.alpha == pytest.approx(2.0)

    def test_failure_updates_beta(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.record_outcome("cat", _outcome("v1", success=False))
        v = opt._variants["cat"]["v1"]
        assert v.beta == pytest.approx(2.0)

    def test_quality_score_forwarded(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.record_outcome("cat", _outcome("v1", success=True, quality_score=0.9))
        v = opt._variants["cat"]["v1"]
        assert v.average_quality == pytest.approx(0.9 * 0.2)


# ---------------------------------------------------------------------------
# PromptOptimizer — get_best_variant
# ---------------------------------------------------------------------------


class TestGetBestVariant:
    def test_returns_none_for_unknown_category(self):
        opt = PromptOptimizer()
        assert opt.get_best_variant("ghost") is None

    def test_returns_none_when_no_eligible_variants(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        # 0 trials < MIN_TRIALS (5) by default
        assert opt.get_best_variant("cat") is None

    def test_returns_best_by_success_rate(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v_good", "good prompt")
        opt.register_variant("cat", "v_bad", "bad prompt")
        # Drive v_good to high success rate
        for _ in range(6):
            opt.record_outcome("cat", _outcome("v_good", success=True))
        for _ in range(6):
            opt.record_outcome("cat", _outcome("v_bad", success=False))
        best = opt.get_best_variant("cat")
        assert best is not None
        assert best.variant_id == "v_good"

    def test_min_trials_zero_returns_any_eligible(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        best = opt.get_best_variant("cat", min_trials=0)
        assert best is not None

    def test_deactivated_variant_excluded(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        for _ in range(6):
            opt.record_outcome("cat", _outcome("v1", success=True))
        opt.deactivate_variant("cat", "v1")
        assert opt.get_best_variant("cat") is None


# ---------------------------------------------------------------------------
# PromptOptimizer — get_variant_stats
# ---------------------------------------------------------------------------


class TestGetVariantStats:
    def test_returns_empty_for_unknown_category(self):
        opt = PromptOptimizer()
        assert opt.get_variant_stats("ghost") == []

    def test_returns_list_of_dicts(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL, "desc")
        stats = opt.get_variant_stats("cat")
        assert len(stats) == 1
        s = stats[0]
        assert s["variant_id"] == "v1"
        assert s["description"] == "desc"
        assert "success_rate" in s
        assert "total_trials" in s
        assert "average_quality" in s
        assert "average_latency_ms" in s
        assert "is_active" in s


# ---------------------------------------------------------------------------
# PromptOptimizer — deactivate_variant
# ---------------------------------------------------------------------------


class TestDeactivateVariant:
    def test_deactivate_sets_flag(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.deactivate_variant("cat", "v1")
        assert opt._variants["cat"]["v1"].is_active is False

    def test_deactivate_unknown_category_is_noop(self):
        opt = PromptOptimizer()
        opt.deactivate_variant("ghost", "v1")  # must not raise

    def test_deactivate_unknown_variant_is_noop(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.deactivate_variant("cat", "ghost")  # must not raise
        assert opt._variants["cat"]["v1"].is_active is True


# ---------------------------------------------------------------------------
# PromptOptimizer — register_dspy_profile
# ---------------------------------------------------------------------------


class TestRegisterDspyProfile:
    def test_creates_variant_in_dspy_category(self):
        opt = PromptOptimizer()
        v = opt.register_dspy_profile("profile-1", "planner", "Optimized prompt", 0.8)
        assert isinstance(v, PromptVariant)
        assert "dspy_planner" in opt._variants
        assert "profile-1" in opt._variants["dspy_planner"]

    def test_alpha_beta_biased_by_validation_score(self):
        opt = PromptOptimizer()
        v = opt.register_dspy_profile("p1", "execution", "prompt", validation_score=0.8)
        # 10 pseudo-obs: successes = int(0.8 * 10) = 8, failures = max(1, 2) = 2
        assert v.alpha == pytest.approx(8.0)
        assert v.beta == pytest.approx(2.0)

    def test_low_validation_score_biases_toward_failure(self):
        opt = PromptOptimizer()
        v = opt.register_dspy_profile("p2", "system", "prompt", validation_score=0.1)
        # successes = max(1, int(0.1*10)) = 1, failures = max(1, 9) = 9
        assert v.alpha == pytest.approx(1.0)
        assert v.beta == pytest.approx(9.0)

    def test_perfect_score(self):
        opt = PromptOptimizer()
        v = opt.register_dspy_profile("p3", "planner", "prompt", validation_score=1.0)
        assert v.alpha == pytest.approx(10.0)
        assert v.beta == pytest.approx(1.0)

    def test_zero_score_still_has_min_values(self):
        opt = PromptOptimizer()
        v = opt.register_dspy_profile("p4", "system", "prompt", validation_score=0.0)
        assert v.alpha >= 1.0
        assert v.beta >= 1.0


# ---------------------------------------------------------------------------
# PromptOptimizer — auto_generate_variants
# ---------------------------------------------------------------------------


class TestAutoGenerateVariants:
    def test_empty_base_prompt_returns_empty(self):
        opt = PromptOptimizer()
        result = opt.auto_generate_variants("cat", "")
        assert result == []

    def test_generates_requested_count(self):
        opt = PromptOptimizer()
        variants = opt.auto_generate_variants("cat", "Base prompt", num_variants=2)
        assert len(variants) == 2

    def test_generates_all_three_by_default(self):
        opt = PromptOptimizer()
        variants = opt.auto_generate_variants("cat", "Base prompt", num_variants=3)
        assert len(variants) == 3

    def test_variant_ids_are_auto_prefixed(self):
        opt = PromptOptimizer()
        variants = opt.auto_generate_variants("cat", "Base prompt", num_variants=3)
        ids = {v.variant_id for v in variants}
        assert ids == {"auto_concise", "auto_detailed", "auto_collaborative"}

    def test_idempotent_on_second_call(self):
        opt = PromptOptimizer()
        first = opt.auto_generate_variants("cat", "Base prompt", num_variants=2)
        second = opt.auto_generate_variants("cat", "Base prompt", num_variants=2)
        assert [v.variant_id for v in first] == [v.variant_id for v in second]
        # Both calls return objects for the same stored variants
        assert first[0] is second[0]

    def test_templates_include_style_directive(self):
        opt = PromptOptimizer()
        variants = opt.auto_generate_variants("cat", "Base prompt", num_variants=1)
        assert variants[0].prompt_template.startswith("Base prompt")
        assert "[Style:" in variants[0].prompt_template

    def test_registered_in_correct_category(self):
        opt = PromptOptimizer()
        opt.auto_generate_variants("my_cat", "Base prompt", num_variants=2)
        assert "my_cat" in opt._variants
        assert opt.get_exploration_stats()["variants_by_category"]["my_cat"] == 2


# ---------------------------------------------------------------------------
# PromptOptimizer — get_exploration_stats
# ---------------------------------------------------------------------------


class TestGetExplorationStats:
    def test_reflects_selections(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.select_variant("cat")
        opt.select_variant("cat")
        assert opt.get_exploration_stats()["total_selections"] == 2

    def test_reflects_variant_counts(self):
        opt = PromptOptimizer()
        opt.register_variant("cat", "v1", TMPL)
        opt.register_variant("cat", "v2", TMPL)
        opt.register_variant("dog", "w1", TMPL)
        stats = opt.get_exploration_stats()
        assert stats["categories"] == 2
        assert stats["variants_by_category"]["cat"] == 2
        assert stats["variants_by_category"]["dog"] == 1


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingletonHelpers:
    def setup_method(self):
        reset_prompt_optimizer()

    def teardown_method(self):
        reset_prompt_optimizer()

    def test_get_prompt_optimizer_returns_instance(self):
        opt = get_prompt_optimizer()
        assert isinstance(opt, PromptOptimizer)

    def test_get_prompt_optimizer_returns_same_instance(self):
        a = get_prompt_optimizer()
        b = get_prompt_optimizer()
        assert a is b

    def test_reset_creates_fresh_instance(self):
        a = get_prompt_optimizer()
        a.register_variant("cat", "v1", TMPL)
        reset_prompt_optimizer()
        b = get_prompt_optimizer()
        assert b is not a
        assert b.get_exploration_stats()["categories"] == 0
