"""Tests for query canonicalization and in-process hot cache."""

import time

import pytest

from app.domain.services.tools.search import (
    _HOT_CACHE_MAXSIZE,
    _HOT_CACHE_TTL,
    _hot_cache,
    _hot_cache_get,
    _hot_cache_set,
    canonicalize_query,
)


# ---------------------------------------------------------------------------
# canonicalize_query
# ---------------------------------------------------------------------------


def test_canonicalize_strips_leading_trailing_whitespace():
    assert canonicalize_query("  hello world  ") == "hello world"


def test_canonicalize_lowercases():
    assert canonicalize_query("Python FastAPI") == "python fastapi"


def test_canonicalize_collapses_internal_whitespace():
    assert canonicalize_query("hello   world") == "hello world"


def test_canonicalize_near_duplicate_same_key():
    assert canonicalize_query("  Python  FastAPI  ") == canonicalize_query("python fastapi")


def test_canonicalize_empty_string():
    assert canonicalize_query("") == ""


def test_canonicalize_single_word():
    assert canonicalize_query("  FastAPI  ") == "fastapi"


# ---------------------------------------------------------------------------
# In-process hot cache
# ---------------------------------------------------------------------------


def setup_function():
    """Clear the hot cache before each test."""
    _hot_cache.clear()


def test_hot_cache_miss_returns_none():
    result = _hot_cache_get("nonexistent")
    assert result is None


def test_hot_cache_set_and_get():
    sentinel = object()
    _hot_cache_set("test_key", sentinel)
    assert _hot_cache_get("test_key") is sentinel


def test_hot_cache_expired_returns_none():
    _hot_cache_set("expiring", "value", ttl=0.05)  # 50ms TTL
    time.sleep(0.1)  # Wait for expiry
    assert _hot_cache_get("expiring") is None


def test_hot_cache_evicts_oldest_at_capacity():
    """When at maxsize, oldest entry is evicted to make room."""
    # Fill cache to capacity
    for i in range(_HOT_CACHE_MAXSIZE):
        _hot_cache_set(f"key_{i}", f"value_{i}")

    assert len(_hot_cache) == _HOT_CACHE_MAXSIZE

    # Add one more — should evict key_0 (oldest)
    _hot_cache_set("new_key", "new_value")
    assert len(_hot_cache) == _HOT_CACHE_MAXSIZE
    assert _hot_cache_get("key_0") is None  # evicted
    assert _hot_cache_get("new_key") == "new_value"


def test_hot_cache_ttl_constant():
    """Default TTL must be 30s."""
    assert _HOT_CACHE_TTL == 30.0


def test_hot_cache_maxsize_constant():
    """Default maxsize must be 50."""
    assert _HOT_CACHE_MAXSIZE == 50
