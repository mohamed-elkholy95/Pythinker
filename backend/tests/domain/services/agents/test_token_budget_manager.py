"""Tests for token_budget_manager: PhaseAllocation, TokenBudget, BudgetAction, BudgetPhase."""

from __future__ import annotations

import pytest

from app.domain.services.agents.token_budget_manager import (
    BudgetAction,
    BudgetPhase,
    PhaseAllocation,
    TokenBudget,
    TokenBudgetManager,
)

# ── BudgetPhase enum ───────────────────────────────────────────────────────


class TestBudgetPhase:
    def test_all_members_exist(self) -> None:
        names = {m.value for m in BudgetPhase}
        assert names == {"system_prompt", "planning", "execution", "memory_context", "summarization"}

    def test_string_comparison(self) -> None:
        assert BudgetPhase.PLANNING == "planning"
        assert BudgetPhase.EXECUTION == "execution"


# ── BudgetAction enum ──────────────────────────────────────────────────────


class TestBudgetAction:
    def test_all_members_exist(self) -> None:
        names = {m.value for m in BudgetAction}
        assert names == {"normal", "reduce_verbosity", "force_conclude", "force_hard_stop_nudge", "hard_stop_tools"}


# ── PhaseAllocation ─────────────────────────────────────────────────────────


class TestPhaseAllocation:
    def test_remaining_with_unused_budget(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.PLANNING, fraction=0.15, allocated_tokens=10000, used_tokens=3000)
        assert alloc.remaining == 7000

    def test_remaining_exceeds_allocated(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.PLANNING, fraction=0.15, allocated_tokens=5000, used_tokens=7000)
        assert alloc.remaining == 0

    def test_remaining_exactly_zero(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.PLANNING, fraction=0.15, allocated_tokens=5000, used_tokens=5000)
        assert alloc.remaining == 0

    def test_usage_ratio_normal(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.EXECUTION, fraction=0.45, allocated_tokens=10000, used_tokens=5000)
        assert alloc.usage_ratio == pytest.approx(0.5)

    def test_usage_ratio_zero_allocated(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.EXECUTION, fraction=0.0, allocated_tokens=0, used_tokens=0)
        assert alloc.usage_ratio == 0.0

    def test_is_exceeded_false(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.EXECUTION, fraction=0.45, allocated_tokens=10000, used_tokens=5000)
        assert alloc.is_exceeded is False

    def test_is_exceeded_true(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.EXECUTION, fraction=0.45, allocated_tokens=5000, used_tokens=5001)
        assert alloc.is_exceeded is True

    def test_is_exceeded_equal(self) -> None:
        alloc = PhaseAllocation(phase=BudgetPhase.EXECUTION, fraction=0.45, allocated_tokens=5000, used_tokens=5000)
        assert alloc.is_exceeded is False


# ── TokenBudget ─────────────────────────────────────────────────────────────


class TestTokenBudget:
    def _make_budget(self) -> TokenBudget:
        budget = TokenBudget(max_tokens=128000, safety_margin=2048)
        budget.phases[BudgetPhase.SYSTEM_PROMPT] = PhaseAllocation(
            phase=BudgetPhase.SYSTEM_PROMPT, fraction=0.15, allocated_tokens=18893
        )
        budget.phases[BudgetPhase.PLANNING] = PhaseAllocation(
            phase=BudgetPhase.PLANNING, fraction=0.15, allocated_tokens=18893
        )
        budget.phases[BudgetPhase.EXECUTION] = PhaseAllocation(
            phase=BudgetPhase.EXECUTION, fraction=0.45, allocated_tokens=56678
        )
        budget.phases[BudgetPhase.MEMORY_CONTEXT] = PhaseAllocation(
            phase=BudgetPhase.MEMORY_CONTEXT, fraction=0.10, allocated_tokens=12595
        )
        budget.phases[BudgetPhase.SUMMARIZATION] = PhaseAllocation(
            phase=BudgetPhase.SUMMARIZATION, fraction=0.15, allocated_tokens=18893
        )
        return budget

    def test_effective_limit(self) -> None:
        budget = TokenBudget(max_tokens=128000, safety_margin=2048)
        assert budget.effective_limit == 125952

    def test_total_allocated(self) -> None:
        budget = self._make_budget()
        assert budget.total_allocated == 18893 + 18893 + 56678 + 12595 + 18893

    def test_total_used_initial(self) -> None:
        budget = self._make_budget()
        assert budget.total_used == 0

    def test_total_remaining_initial(self) -> None:
        budget = self._make_budget()
        assert budget.total_remaining == budget.effective_limit

    def test_overall_usage_ratio_zero_initially(self) -> None:
        budget = self._make_budget()
        assert budget.overall_usage_ratio == 0.0

    def test_record_usage(self) -> None:
        budget = self._make_budget()
        budget.record_usage(BudgetPhase.PLANNING, 5000)
        assert budget.phases[BudgetPhase.PLANNING].used_tokens == 5000
        assert budget.total_used == 5000

    def test_record_usage_multiple_phases(self) -> None:
        budget = self._make_budget()
        budget.record_usage(BudgetPhase.PLANNING, 3000)
        budget.record_usage(BudgetPhase.EXECUTION, 10000)
        assert budget.total_used == 13000

    def test_record_usage_unknown_phase_no_op(self) -> None:
        budget = TokenBudget(max_tokens=128000)
        # No phases configured — should not raise
        budget.record_usage(BudgetPhase.PLANNING, 1000)

    def test_get_phase_remaining(self) -> None:
        budget = self._make_budget()
        budget.record_usage(BudgetPhase.EXECUTION, 10000)
        assert budget.get_phase_remaining(BudgetPhase.EXECUTION) == 56678 - 10000

    def test_get_phase_remaining_unknown_phase(self) -> None:
        budget = TokenBudget(max_tokens=128000)
        assert budget.get_phase_remaining(BudgetPhase.PLANNING) == 0

    def test_overall_usage_ratio_after_usage(self) -> None:
        budget = self._make_budget()
        budget.record_usage(BudgetPhase.EXECUTION, budget.effective_limit // 2)
        assert budget.overall_usage_ratio == pytest.approx(0.5, abs=0.01)

    def test_overall_usage_ratio_zero_effective_limit(self) -> None:
        budget = TokenBudget(max_tokens=100, safety_margin=100)
        assert budget.effective_limit == 0
        assert budget.overall_usage_ratio == 0.0


# ── TokenBudgetManager (data models only, mock token_manager) ───────────────


class _FakeTokenManager:
    """Minimal mock for TokenManager interface."""

    def __init__(self, max_tokens: int = 128000) -> None:
        self._max_tokens = max_tokens

    def count_messages_tokens(self, messages: list) -> int:
        return sum(len(m.get("content", "")) for m in messages)


class TestTokenBudgetManagerCreateBudget:
    def test_create_budget_default_allocations(self) -> None:
        tm = _FakeTokenManager(128000)
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)

        assert len(budget.phases) == 5
        assert BudgetPhase.EXECUTION in budget.phases
        # Execution should get 45% of effective limit
        effective = 128000 - 2048
        expected_exec = int(effective * 0.45)
        assert budget.phases[BudgetPhase.EXECUTION].allocated_tokens == expected_exec

    def test_create_budget_research_profile(self) -> None:
        tm = _FakeTokenManager(128000)
        mgr = TokenBudgetManager(tm, research_mode="deep_research")
        budget = mgr.create_budget(128000)

        # Deep research: planning=20%, execution=45%, summarization=20%
        effective = 128000 - 2048
        assert budget.phases[BudgetPhase.PLANNING].allocated_tokens == int(effective * 0.20)
        assert budget.phases[BudgetPhase.EXECUTION].allocated_tokens == int(effective * 0.45)
        assert budget.phases[BudgetPhase.SUMMARIZATION].allocated_tokens == int(effective * 0.20)

    def test_create_budget_min_phase_tokens(self) -> None:
        tm = _FakeTokenManager(5000)
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(5000)

        # All phases should have at least MIN_PHASE_TOKENS
        for alloc in budget.phases.values():
            assert alloc.allocated_tokens >= TokenBudgetManager.MIN_PHASE_TOKENS

    def test_create_budget_uses_token_manager_limit_when_none(self) -> None:
        tm = _FakeTokenManager(64000)
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget()
        assert budget.max_tokens == 64000

    def test_planning_cap_enforced(self) -> None:
        """If planning fraction exceeds MAX_PLANNING_FRACTION, it's capped."""
        tm = _FakeTokenManager(128000)
        high_planning = {
            BudgetPhase.SYSTEM_PROMPT: 0.10,
            BudgetPhase.PLANNING: 0.50,  # Way above 0.30 cap
            BudgetPhase.EXECUTION: 0.20,
            BudgetPhase.MEMORY_CONTEXT: 0.10,
            BudgetPhase.SUMMARIZATION: 0.10,
        }
        mgr = TokenBudgetManager(tm, allocations=high_planning)
        budget = mgr.create_budget(128000)

        assert budget.phases[BudgetPhase.PLANNING].fraction <= TokenBudgetManager.MAX_PLANNING_FRACTION


class TestTokenBudgetManagerEnforceBudgetPolicy:
    def test_normal_at_low_usage(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.50) == BudgetAction.NORMAL

    def test_reduce_verbosity_at_90(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.90) == BudgetAction.REDUCE_VERBOSITY

    def test_force_conclude_at_95(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.95) == BudgetAction.FORCE_CONCLUDE

    def test_force_hard_stop_nudge_at_98(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.98) == BudgetAction.FORCE_HARD_STOP_NUDGE

    def test_hard_stop_tools_at_99(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.99) == BudgetAction.HARD_STOP_TOOLS

    def test_hard_stop_at_100(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(1.0) == BudgetAction.HARD_STOP_TOOLS

    def test_boundary_just_below_90(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        assert mgr.enforce_budget_policy(0.899) == BudgetAction.NORMAL


class TestTokenBudgetManagerRebalance:
    def test_rebalance_transfers_unused_tokens(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)

        planning_alloc = budget.phases[BudgetPhase.PLANNING]
        exec_alloc = budget.phases[BudgetPhase.EXECUTION]
        original_exec = exec_alloc.allocated_tokens

        # Use only half the planning budget
        budget.record_usage(BudgetPhase.PLANNING, planning_alloc.allocated_tokens // 2)
        unused = planning_alloc.remaining

        mgr.rebalance(budget, BudgetPhase.PLANNING, BudgetPhase.EXECUTION)

        assert exec_alloc.allocated_tokens == original_exec + unused

    def test_rebalance_zero_unused(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)

        exec_alloc = budget.phases[BudgetPhase.EXECUTION]
        original_exec = exec_alloc.allocated_tokens

        # Use all planning budget
        planning_alloc = budget.phases[BudgetPhase.PLANNING]
        budget.record_usage(BudgetPhase.PLANNING, planning_alloc.allocated_tokens)

        mgr.rebalance(budget, BudgetPhase.PLANNING, BudgetPhase.EXECUTION)

        assert exec_alloc.allocated_tokens == original_exec

    def test_rebalance_missing_phase_no_error(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = TokenBudget(max_tokens=128000)
        # No phases configured - should not raise
        mgr.rebalance(budget, BudgetPhase.PLANNING, BudgetPhase.EXECUTION)


class TestTokenBudgetManagerCheckBeforeCall:
    def test_check_passes_within_budget(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)

        messages = [{"role": "user", "content": "Hello"}]
        ok, reason = mgr.check_before_call(budget, BudgetPhase.PLANNING, messages)
        assert ok is True
        assert reason == "OK"

    def test_check_fails_when_exceeds_phase(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)

        # Exhaust the planning phase
        planning = budget.phases[BudgetPhase.PLANNING]
        budget.record_usage(BudgetPhase.PLANNING, planning.allocated_tokens)

        messages = [{"role": "user", "content": "x" * 100}]
        ok, reason = mgr.check_before_call(budget, BudgetPhase.PLANNING, messages)
        assert ok is False
        assert "budget exceeded" in reason.lower()

    def test_check_passes_unbudgeted_phase(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = TokenBudget(max_tokens=128000)

        messages = [{"role": "user", "content": "Hello"}]
        ok, reason = mgr.check_before_call(budget, BudgetPhase.PLANNING, messages)
        assert ok is True
        assert reason == "Phase not budgeted"


class TestTokenBudgetManagerBudgetSummary:
    def test_get_budget_summary_structure(self) -> None:
        tm = _FakeTokenManager()
        mgr = TokenBudgetManager(tm)
        budget = mgr.create_budget(128000)
        budget.record_usage(BudgetPhase.EXECUTION, 5000)

        summary = mgr.get_budget_summary(budget)

        assert summary["max_tokens"] == 128000
        assert summary["effective_limit"] == 125952
        assert summary["total_used"] == 5000
        assert "phases" in summary
        assert "execution" in summary["phases"]
        assert summary["phases"]["execution"]["used"] == 5000
