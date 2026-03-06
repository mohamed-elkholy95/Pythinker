"""Tests for deep_research budget allocation rebalance."""

from __future__ import annotations

from app.domain.services.agents.token_budget_manager import (
    BudgetPhase,
    TokenBudgetManager,
)


class TestDeepResearchAllocations:
    def test_deep_research_planning_is_15_percent(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["deep_research"]
        assert allocs[BudgetPhase.PLANNING] == 0.15

    def test_deep_research_memory_context_is_5_percent(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["deep_research"]
        assert allocs[BudgetPhase.MEMORY_CONTEXT] == 0.05

    def test_deep_research_allocations_sum_to_1(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["deep_research"]
        total = sum(allocs.values())
        assert abs(total - 1.0) < 0.001, f"Sum is {total}"

    def test_wide_research_allocations_sum_to_1(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["wide_research"]
        total = sum(allocs.values())
        assert abs(total - 1.0) < 0.001

    def test_fast_search_allocations_sum_to_1(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["fast_search"]
        total = sum(allocs.values())
        assert abs(total - 1.0) < 0.001

    def test_execution_unchanged_at_50_percent(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["deep_research"]
        assert allocs[BudgetPhase.EXECUTION] == 0.50

    def test_summarization_unchanged_at_20_percent(self):
        allocs = TokenBudgetManager.RESEARCH_ALLOCATIONS["deep_research"]
        assert allocs[BudgetPhase.SUMMARIZATION] == 0.20
