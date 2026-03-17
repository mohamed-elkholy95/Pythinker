"""Tests for ProviderHealthRanker sliding-window health scoring."""

import time

import pytest

from app.infrastructure.external.search.provider_health_ranker import (
    WINDOW_SECONDS,
    ProviderHealthRanker,
    get_provider_health_ranker,
)


@pytest.fixture
def ranker() -> ProviderHealthRanker:
    return ProviderHealthRanker()


def test_fresh_provider_score_is_1(ranker):
    """Provider with no events has max health score."""
    assert ranker.health_score("serper") == 1.0


def test_all_successes_score_is_1(ranker):
    for _ in range(10):
        ranker.record_success("serper")
    assert ranker.health_score("serper") == 1.0


def test_all_429s_reduce_score(ranker):
    """Provider with only 429 responses should have heavily reduced score."""
    for _ in range(10):
        ranker.record_429("tavily")
    score = ranker.health_score("tavily")
    assert score < 0.5


def test_mixed_success_and_429_partial_score(ranker):
    """50% success + 50% 429 should yield intermediate score."""
    for _ in range(5):
        ranker.record_success("brave")
    for _ in range(5):
        ranker.record_429("brave")
    score = ranker.health_score("brave")
    assert 0.0 < score < 1.0


def test_rank_puts_healthier_provider_first(ranker):
    """rank() returns healthier providers before degraded ones."""
    # Make serper look degraded (all 429s)
    for _ in range(10):
        ranker.record_429("serper")
    # Make tavily look healthy (all successes)
    for _ in range(10):
        ranker.record_success("tavily")

    ordered = ranker.rank(["serper", "tavily"])
    assert ordered[0] == "tavily"
    assert ordered[1] == "serper"


def test_rank_preserves_order_when_equal(ranker):
    """Providers with equal (no data) scores keep original order."""
    chain = ["serper", "brave", "tavily", "exa"]
    ordered = ranker.rank(chain)
    assert ordered == chain  # All score 1.0 — stable sort preserves order


def test_events_outside_window_are_pruned(ranker):
    """Events older than WINDOW_SECONDS are not counted."""
    stats = ranker._get_stats("exa")
    # Inject an old event manually
    old_time = time.monotonic() - WINDOW_SECONDS - 1
    stats.events.append((old_time, "429"))
    # Prune + score — old event should be gone
    score = ranker.health_score("exa")
    assert score == 1.0  # Old event pruned, no recent events


def test_get_provider_health_ranker_returns_singleton():
    """get_provider_health_ranker returns the same instance each time."""
    r1 = get_provider_health_ranker()
    r2 = get_provider_health_ranker()
    assert r1 is r2
