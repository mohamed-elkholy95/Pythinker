"""Tests for ReasoningCache and CachedReasoning."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.models.thought import Decision, ThoughtChain
from app.domain.services.agents.caching.reasoning_cache import (
    CachedReasoning,
    ReasoningCache,
    ReasoningMatch,
    get_reasoning_cache,
    reset_reasoning_cache,
)


def _make_chain(problem: str = "test problem") -> ThoughtChain:
    return ThoughtChain(problem=problem)


def _make_decision(action: str = "do something") -> Decision:
    return Decision(action=action, rationale="because", confidence=0.8)


# ---------------------------------------------------------------------------
# CachedReasoning dataclass
# ---------------------------------------------------------------------------


class TestCachedReasoning:
    def test_defaults(self):
        cr = CachedReasoning(
            cache_key="k",
            problem_hash="h",
            problem_summary="summary",
            thought_chain=_make_chain(),
            decision=_make_decision(),
        )
        assert cr.success_count == 0
        assert cr.failure_count == 0
        assert cr.last_used is None
        assert isinstance(cr.created_at, datetime)
        assert isinstance(cr.expires_at, datetime)
        assert cr.metadata == {}

    def test_success_rate_no_uses(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
        )
        assert cr.success_rate == 0.5

    def test_success_rate_all_success(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            success_count=5, failure_count=0,
        )
        assert cr.success_rate == 1.0

    def test_success_rate_mixed(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            success_count=3, failure_count=7,
        )
        assert cr.success_rate == pytest.approx(0.3)

    def test_is_expired_future(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert cr.is_expired() is False

    def test_is_expired_past(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert cr.is_expired() is True

    def test_is_reliable_enough_uses_and_rate(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            success_count=4, failure_count=1,
        )
        assert cr.is_reliable(min_uses=3, min_success_rate=0.6) is True

    def test_is_reliable_too_few_uses(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            success_count=2, failure_count=0,
        )
        assert cr.is_reliable(min_uses=3) is False

    def test_is_reliable_low_rate(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
            success_count=1, failure_count=5,
        )
        assert cr.is_reliable(min_uses=3, min_success_rate=0.6) is False

    def test_record_use_success(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
        )
        cr.record_use(True)
        assert cr.success_count == 1
        assert cr.failure_count == 0
        assert cr.last_used is not None

    def test_record_use_failure(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
        )
        cr.record_use(False)
        assert cr.success_count == 0
        assert cr.failure_count == 1


# ---------------------------------------------------------------------------
# ReasoningMatch dataclass
# ---------------------------------------------------------------------------


class TestReasoningMatch:
    def test_creation(self):
        cr = CachedReasoning(
            cache_key="k", problem_hash="h", problem_summary="s",
            thought_chain=_make_chain(), decision=_make_decision(),
        )
        m = ReasoningMatch(
            cached_reasoning=cr, similarity_score=0.9,
            confidence=0.8, should_use=True, reason="Exact match",
        )
        assert m.similarity_score == 0.9
        assert m.should_use is True


# ---------------------------------------------------------------------------
# ReasoningCache
# ---------------------------------------------------------------------------


class TestReasoningCache:
    def test_init_defaults(self):
        cache = ReasoningCache()
        assert cache._max_entries == 500
        assert cache._total_hits == 0
        assert cache._total_misses == 0

    def test_init_custom_max(self):
        cache = ReasoningCache(max_entries=10)
        assert cache._max_entries == 10

    def test_store_returns_cached_reasoning(self):
        cache = ReasoningCache()
        cr = cache.store("my problem", _make_chain(), _make_decision())
        assert isinstance(cr, CachedReasoning)
        assert cr.problem_summary == "my problem"

    def test_store_truncates_summary_to_200(self):
        cache = ReasoningCache()
        long = "x" * 500
        cr = cache.store(long, _make_chain(), _make_decision())
        assert len(cr.problem_summary) == 200

    def test_store_custom_ttl(self):
        cache = ReasoningCache()
        cr = cache.store("p", _make_chain(), _make_decision(), ttl_hours=1)
        diff = (cr.expires_at - cr.created_at).total_seconds()
        assert 3500 < diff < 3700

    def test_store_evicts_when_full(self):
        cache = ReasoningCache(max_entries=2)
        cache.store("p1", _make_chain(), _make_decision())
        cache.store("p2", _make_chain(), _make_decision())
        cache.store("p3", _make_chain(), _make_decision())
        assert len(cache._cache) == 2

    def test_find_similar_exact_match(self):
        cache = ReasoningCache()
        cache.store("find exact problem", _make_chain(), _make_decision())
        match = cache.find_similar("find exact problem")
        assert match is not None
        assert match.similarity_score == 1.0
        assert match.reason == "Exact match found"

    def test_find_similar_no_match(self):
        cache = ReasoningCache()
        cache.store("apples and oranges", _make_chain(), _make_decision())
        match = cache.find_similar("completely unrelated xyz 123")
        assert match is None

    def test_find_similar_fuzzy_match(self):
        cache = ReasoningCache()
        cache.store("how to deploy python web application", _make_chain(), _make_decision())
        match = cache.find_similar("how to deploy python web service")
        assert match is not None
        assert match.similarity_score >= 0.6

    def test_find_similar_skips_expired(self):
        cache = ReasoningCache()
        cr = cache.store("problem A", _make_chain(), _make_decision())
        cr.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        match = cache.find_similar("problem A")
        assert match is None

    def test_find_similar_hits_counter(self):
        cache = ReasoningCache()
        cache.store("test hit", _make_chain(), _make_decision())
        cache.find_similar("test hit")
        assert cache._total_hits == 1

    def test_find_similar_miss_counter(self):
        cache = ReasoningCache()
        cache.find_similar("nothing stored")
        assert cache._total_misses == 1

    def test_record_outcome_success(self):
        cache = ReasoningCache()
        cr = cache.store("prob", _make_chain(), _make_decision())
        cache.record_outcome(cr.cache_key, True)
        assert cache._cache[cr.cache_key].success_count == 1

    def test_record_outcome_failure(self):
        cache = ReasoningCache()
        cr = cache.store("prob", _make_chain(), _make_decision())
        cache.record_outcome(cr.cache_key, False)
        assert cache._cache[cr.cache_key].failure_count == 1

    def test_record_outcome_missing_key(self):
        cache = ReasoningCache()
        cache.record_outcome("nonexistent", True)  # should not raise

    def test_get_pattern_for_type_found(self):
        cache = ReasoningCache()
        cr = cache.store("deploy python app", _make_chain(), _make_decision())
        cr.success_count = 5
        cr.failure_count = 0
        result = cache.get_pattern_for_type("deploy")
        assert result is not None
        assert result.cache_key == cr.cache_key

    def test_get_pattern_for_type_low_rate(self):
        cache = ReasoningCache()
        cr = cache.store("deploy python app", _make_chain(), _make_decision())
        cr.success_count = 1
        cr.failure_count = 9
        result = cache.get_pattern_for_type("deploy", min_success_rate=0.7)
        assert result is None

    def test_get_pattern_for_type_expired_skipped(self):
        cache = ReasoningCache()
        cr = cache.store("deploy python app", _make_chain(), _make_decision())
        cr.success_count = 5
        cr.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        result = cache.get_pattern_for_type("deploy")
        assert result is None

    def test_cleanup_expired(self):
        cache = ReasoningCache()
        cr1 = cache.store("p1", _make_chain(), _make_decision())
        cr2 = cache.store("p2", _make_chain(), _make_decision())
        cr1.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        removed = cache.cleanup_expired()
        assert removed == 1
        assert len(cache._cache) == 1

    def test_cleanup_low_performing(self):
        cache = ReasoningCache()
        cr = cache.store("low perf", _make_chain(), _make_decision())
        cr.success_count = 1
        cr.failure_count = 10
        removed = cache.cleanup_low_performing(min_uses=5, min_success_rate=0.3)
        assert removed == 1
        assert len(cache._cache) == 0

    def test_cleanup_low_performing_keeps_good(self):
        cache = ReasoningCache()
        cr = cache.store("good", _make_chain(), _make_decision())
        cr.success_count = 8
        cr.failure_count = 2
        removed = cache.cleanup_low_performing(min_uses=5, min_success_rate=0.3)
        assert removed == 0
        assert len(cache._cache) == 1

    def test_cleanup_low_performing_skips_few_uses(self):
        cache = ReasoningCache()
        cr = cache.store("new", _make_chain(), _make_decision())
        cr.success_count = 0
        cr.failure_count = 2
        removed = cache.cleanup_low_performing(min_uses=5, min_success_rate=0.3)
        assert removed == 0

    def test_get_statistics(self):
        cache = ReasoningCache()
        cache.store("p1", _make_chain(), _make_decision())
        cache.find_similar("p1")  # hit
        cache.find_similar("nonexistent")  # miss
        stats = cache.get_statistics()
        assert stats["total_entries"] == 1
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["hit_rate"] == pytest.approx(0.5)

    def test_generate_key_deterministic(self):
        cache = ReasoningCache()
        k1 = cache._generate_key("hello world")
        k2 = cache._generate_key("hello world")
        assert k1 == k2

    def test_generate_key_case_insensitive(self):
        cache = ReasoningCache()
        k1 = cache._generate_key("Hello World")
        k2 = cache._generate_key("hello world")
        assert k1 == k2

    def test_calculate_similarity_identical(self):
        cache = ReasoningCache()
        assert cache._calculate_similarity("a b c", "a b c") == 1.0

    def test_calculate_similarity_disjoint(self):
        cache = ReasoningCache()
        assert cache._calculate_similarity("a b c", "x y z") == 0.0

    def test_calculate_similarity_partial(self):
        cache = ReasoningCache()
        score = cache._calculate_similarity("a b c d", "a b e f")
        assert 0.0 < score < 1.0

    def test_calculate_similarity_empty(self):
        cache = ReasoningCache()
        assert cache._calculate_similarity("", "a b") == 0.0

    def test_evict_least_used(self):
        cache = ReasoningCache(max_entries=2)
        cr1 = cache.store("first problem", _make_chain(), _make_decision())
        cr1.success_count = 0
        cr1.failure_count = 0
        cr2 = cache.store("second problem", _make_chain(), _make_decision())
        cr2.success_count = 10
        # Storing a third should evict the least-used (cr1)
        cache.store("third problem", _make_chain(), _make_decision())
        assert len(cache._cache) == 2
        assert cr2.cache_key in cache._cache

    def test_average_success_rate_empty(self):
        cache = ReasoningCache()
        assert cache._average_success_rate() == 0.0

    def test_average_success_rate_populated(self):
        cache = ReasoningCache()
        cr1 = cache.store("p1", _make_chain(), _make_decision())
        cr1.success_count = 8
        cr1.failure_count = 2
        cr2 = cache.store("p2", _make_chain(), _make_decision())
        cr2.success_count = 6
        cr2.failure_count = 4
        avg = cache._average_success_rate()
        assert avg == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def setup_method(self):
        reset_reasoning_cache()

    def teardown_method(self):
        reset_reasoning_cache()

    def test_get_reasoning_cache_returns_same_instance(self):
        c1 = get_reasoning_cache()
        c2 = get_reasoning_cache()
        assert c1 is c2

    def test_reset_reasoning_cache_creates_new(self):
        c1 = get_reasoning_cache()
        reset_reasoning_cache()
        c2 = get_reasoning_cache()
        assert c1 is not c2
