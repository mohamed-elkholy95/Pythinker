"""Tests for RetryBudget (Phase 2).

Covers: per-task cap, global rate limit, record_retry, get_usage, reset_task.
"""

from __future__ import annotations

import time

import pytest

from app.domain.services.llm.retry_budget import RetryBudget, RetryBudgetUsage, reset_retry_budget


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_retry_budget()
    yield
    reset_retry_budget()


# ─────────────────────────── Per-task cap ────────────────────────────────────


def test_can_retry_returns_true_within_budget():
    budget = RetryBudget(max_retries_per_task=5, max_retries_per_minute=100)
    assert budget.can_retry("task-1") is True


def test_can_retry_returns_false_after_per_task_cap():
    budget = RetryBudget(max_retries_per_task=3, max_retries_per_minute=100)
    for _ in range(3):
        budget.record_retry("task-1", "openai", "TimeoutError")
    assert budget.can_retry("task-1") is False


def test_per_task_cap_is_independent_per_task():
    budget = RetryBudget(max_retries_per_task=2, max_retries_per_minute=100)
    for _ in range(2):
        budget.record_retry("task-A", "openai", "err")
    # task-A is exhausted, task-B should still be allowed
    assert budget.can_retry("task-A") is False
    assert budget.can_retry("task-B") is True


# ─────────────────────────── Usage tracking ──────────────────────────────────


def test_record_retry_increments_total():
    budget = RetryBudget(max_retries_per_task=10, max_retries_per_minute=100)
    budget.record_retry("t1", "anthropic", "ConnectionError")
    budget.record_retry("t1", "anthropic", "TimeoutError")
    usage = budget.get_usage("t1")
    assert usage.total_retries == 2


def test_record_retry_tracks_by_provider():
    budget = RetryBudget(max_retries_per_task=10, max_retries_per_minute=100)
    budget.record_retry("t1", "openai", "err")
    budget.record_retry("t1", "openai", "err")
    budget.record_retry("t1", "anthropic", "err")
    usage = budget.get_usage("t1")
    assert usage.retries_by_provider["openai"] == 2
    assert usage.retries_by_provider["anthropic"] == 1


def test_record_retry_tracks_by_error_type():
    budget = RetryBudget(max_retries_per_task=10, max_retries_per_minute=100)
    budget.record_retry("t1", "openai", "TimeoutError")
    budget.record_retry("t1", "openai", "TimeoutError")
    budget.record_retry("t1", "openai", "ConnectionError")
    usage = budget.get_usage("t1")
    assert usage.retries_by_error["TimeoutError"] == 2
    assert usage.retries_by_error["ConnectionError"] == 1


def test_get_usage_unknown_task_returns_empty():
    budget = RetryBudget(max_retries_per_task=5, max_retries_per_minute=100)
    usage = budget.get_usage("never-seen")
    assert usage.total_retries == 0
    assert usage.budget_exhausted is False


def test_budget_exhausted_flag_set_when_cap_reached():
    budget = RetryBudget(max_retries_per_task=2, max_retries_per_minute=100)
    for _ in range(2):
        budget.record_retry("t1", "openai", "err")
    # Trigger cap check
    budget.can_retry("t1")
    usage = budget.get_usage("t1")
    assert usage.budget_exhausted is True


# ─────────────────────────── Global rate limit ───────────────────────────────


def test_global_rate_limit_blocks_after_threshold():
    budget = RetryBudget(max_retries_per_task=1000, max_retries_per_minute=5)
    for i in range(5):
        budget.record_retry(f"task-{i}", "openai", "err")
    # 5 retries consumed in the last 60s — next should be blocked
    assert budget.can_retry("task-new") is False


# ─────────────────────────── reset_task ──────────────────────────────────────


def test_reset_task_clears_usage():
    budget = RetryBudget(max_retries_per_task=2, max_retries_per_minute=100)
    for _ in range(2):
        budget.record_retry("t1", "openai", "err")
    budget.reset_task("t1")
    assert budget.can_retry("t1") is True
    assert budget.get_usage("t1").total_retries == 0


# ─────────────────────────── RetryBudgetUsage ────────────────────────────────


def test_retry_budget_usage_is_independent_copy():
    budget = RetryBudget(max_retries_per_task=10, max_retries_per_minute=100)
    budget.record_retry("t1", "openai", "err")
    usage1 = budget.get_usage("t1")
    budget.record_retry("t1", "openai", "err")
    usage2 = budget.get_usage("t1")
    # usage1 captured before second record should be unchanged
    assert usage1.total_retries == 1
    assert usage2.total_retries == 2
