"""Tests for ProviderHealthTracker (Phase 3).

Covers: score calculation, sliding window eviction, best_provider selection.
"""

from __future__ import annotations

import pytest

from app.domain.services.llm.provider_health import (
    ProviderHealthTracker,
    reset_provider_health_tracker,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_provider_health_tracker()
    yield
    reset_provider_health_tracker()


# ─────────────────────────── score() ─────────────────────────────────────────


def test_score_unknown_provider_returns_optimistic_1():
    tracker = ProviderHealthTracker()
    assert tracker.score("never-seen") == 1.0


def test_score_all_success_returns_near_1():
    tracker = ProviderHealthTracker(max_good_latency_ms=5_000)
    for _ in range(10):
        tracker.record("openai", latency_ms=100.0, success=True)
    score = tracker.score("openai")
    assert score > 0.9


def test_score_all_failure_returns_0():
    tracker = ProviderHealthTracker()
    for _ in range(10):
        tracker.record("openai", latency_ms=100.0, success=False)
    assert tracker.score("openai") == 0.0


def test_score_mixed_results():
    tracker = ProviderHealthTracker(latency_percentile_weight=0.0)
    for i in range(10):
        tracker.record("openai", latency_ms=100.0, success=(i < 7))
    score = tracker.score("openai")
    assert 0.65 < score < 0.75  # ~70% success, 0% latency weight


def test_score_high_latency_reduces_score():
    tracker = ProviderHealthTracker(latency_percentile_weight=0.5, max_good_latency_ms=500.0)
    for _ in range(10):
        tracker.record("openai", latency_ms=5_000.0, success=True)  # high latency
    score_high_latency = tracker.score("openai")

    tracker2 = ProviderHealthTracker(latency_percentile_weight=0.5, max_good_latency_ms=500.0)
    for _ in range(10):
        tracker2.record("openai", latency_ms=100.0, success=True)  # low latency
    score_low_latency = tracker2.score("openai")

    assert score_low_latency > score_high_latency


def test_score_clamped_between_0_and_1():
    tracker = ProviderHealthTracker()
    for _ in range(5):
        tracker.record("p", latency_ms=1.0, success=True)
    score = tracker.score("p")
    assert 0.0 <= score <= 1.0


# ─────────────────────────── sliding window ──────────────────────────────────


def test_sliding_window_evicts_old_samples():
    tracker = ProviderHealthTracker(window_size=5)
    # Add 5 failures
    for _ in range(5):
        tracker.record("p", latency_ms=100.0, success=False)
    assert tracker.score("p") == 0.0

    # Add 5 successes — window of 5 now only contains successes
    for _ in range(5):
        tracker.record("p", latency_ms=100.0, success=True)
    assert tracker.score("p") > 0.8


# ─────────────────────────── best_provider() ─────────────────────────────────


def test_best_provider_returns_highest_score():
    tracker = ProviderHealthTracker()
    # Anthropic has all successes
    for _ in range(5):
        tracker.record("anthropic", latency_ms=200.0, success=True)
    # OpenAI has all failures
    for _ in range(5):
        tracker.record("openai", latency_ms=200.0, success=False)

    best = tracker.best_provider(["anthropic", "openai"])
    assert best == "anthropic"


def test_best_provider_falls_back_to_first_when_all_unknown():
    tracker = ProviderHealthTracker()
    best = tracker.best_provider(["anthropic", "openai", "ollama"])
    # All unknown → all score 1.0 → tie → first in list preferred
    assert best == "anthropic"


def test_best_provider_single_candidate():
    tracker = ProviderHealthTracker()
    assert tracker.best_provider(["ollama"]) == "ollama"


def test_best_provider_raises_on_empty_candidates():
    tracker = ProviderHealthTracker()
    with pytest.raises(ValueError, match="must not be empty"):
        tracker.best_provider([])


# ─────────────────────────── status_report() ─────────────────────────────────


def test_status_report_includes_tracked_providers():
    tracker = ProviderHealthTracker()
    tracker.record("p1", latency_ms=100.0, success=True)
    tracker.record("p2", latency_ms=200.0, success=False)
    report = tracker.status_report()
    assert "p1" in report
    assert "p2" in report
    assert report["p1"] > report["p2"]
