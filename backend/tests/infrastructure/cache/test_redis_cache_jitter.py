"""Tests for Redis cache TTL jitter (Phase 2A)."""

from app.infrastructure.external.cache.redis_cache import RedisCache


class TestTTLJitter:
    """Tests for RedisCache._jittered_ttl()."""

    def test_jitter_stays_within_bounds(self):
        """Jittered TTL should be within ±jitter_percent of original."""
        cache = RedisCache.__new__(RedisCache)
        cache._ttl_jitter_percent = 0.1

        original_ttl = 1000
        for _ in range(100):
            jittered = cache._jittered_ttl(original_ttl)
            assert 900 <= jittered <= 1100, f"Jittered TTL {jittered} out of bounds"

    def test_jitter_disabled_when_zero_percent(self):
        """Zero jitter percent returns exact TTL."""
        cache = RedisCache.__new__(RedisCache)
        cache._ttl_jitter_percent = 0.0

        assert cache._jittered_ttl(1000) == 1000

    def test_jitter_minimum_one_second(self):
        """Jittered TTL never goes below 1 second."""
        cache = RedisCache.__new__(RedisCache)
        cache._ttl_jitter_percent = 0.5  # ±50%

        for _ in range(100):
            jittered = cache._jittered_ttl(1)
            assert jittered >= 1

    def test_jitter_with_small_ttl(self):
        """Small TTL with jitter range of 0 returns exact TTL."""
        cache = RedisCache.__new__(RedisCache)
        cache._ttl_jitter_percent = 0.1

        # TTL=5, jitter_range = int(5 * 0.1) = 0
        assert cache._jittered_ttl(5) == 5

    def test_jitter_produces_variation(self):
        """Jitter should produce different values across calls."""
        cache = RedisCache.__new__(RedisCache)
        cache._ttl_jitter_percent = 0.1

        values = {cache._jittered_ttl(10000) for _ in range(50)}
        # With 10% jitter on 10000, should get multiple distinct values
        assert len(values) > 1, "Jitter should produce variation"
