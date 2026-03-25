"""Unit tests for ScreenshotDedupService."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(threshold: int = 5) -> MagicMock:
    settings = MagicMock()
    settings.screenshot_dedup_threshold = threshold
    return settings


def _make_service(threshold: int = 5):
    """Construct a ScreenshotDedupService with mocked settings."""
    with patch("app.application.services.screenshot_dedup_service.get_settings") as mock_get:
        mock_get.return_value = _make_settings(threshold)
        from app.application.services.screenshot_dedup_service import ScreenshotDedupService

        return ScreenshotDedupService()


def _make_screenshot(storage_key: str, is_duplicate: bool = False) -> MagicMock:
    ss = MagicMock(spec=SessionScreenshot)
    ss.storage_key = storage_key
    ss.is_duplicate = is_duplicate
    return ss


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def svc():
    return _make_service(threshold=5)


# ---------------------------------------------------------------------------
# is_duplicate — always-save triggers
# ---------------------------------------------------------------------------


def test_is_duplicate_session_start_always_returns_false(svc) -> None:
    result = svc.is_duplicate(
        session_id="s1",
        current_hash="aaaa0000ffff1111",
        trigger=ScreenshotTrigger.SESSION_START,
    )
    assert result is False


def test_is_duplicate_session_end_always_returns_false(svc) -> None:
    # Prime the cache with the same hash so it would normally be a duplicate
    svc.is_duplicate("s1", "abcdef0123456789", ScreenshotTrigger.SESSION_START)

    result = svc.is_duplicate(
        session_id="s1",
        current_hash="abcdef0123456789",
        trigger=ScreenshotTrigger.SESSION_END,
    )
    assert result is False


def test_is_duplicate_tool_before_always_returns_false(svc) -> None:
    svc.is_duplicate("s1", "abcdef0123456789", ScreenshotTrigger.SESSION_START)

    result = svc.is_duplicate(
        session_id="s1",
        current_hash="abcdef0123456789",
        trigger=ScreenshotTrigger.TOOL_BEFORE,
    )
    assert result is False


def test_is_duplicate_tool_after_always_returns_false(svc) -> None:
    svc.is_duplicate("s1", "abcdef0123456789", ScreenshotTrigger.SESSION_START)

    result = svc.is_duplicate(
        session_id="s1",
        current_hash="abcdef0123456789",
        trigger=ScreenshotTrigger.TOOL_AFTER,
    )
    assert result is False


def test_always_save_triggers_still_update_cache(svc) -> None:
    """SESSION_START should populate the cache so subsequent PERIODIC comparison works."""
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.SESSION_START)

    # Identical hash as PERIODIC — should be caught as a duplicate
    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=0)
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    assert result is True


# ---------------------------------------------------------------------------
# is_duplicate — empty hash
# ---------------------------------------------------------------------------


def test_is_duplicate_returns_false_for_empty_hash(svc) -> None:
    result = svc.is_duplicate(
        session_id="s1",
        current_hash="",
        trigger=ScreenshotTrigger.PERIODIC,
    )
    assert result is False


def test_is_duplicate_empty_hash_does_not_update_cache(svc) -> None:
    svc.is_duplicate("s1", "", ScreenshotTrigger.PERIODIC)
    assert "s1" not in svc._last_hash_cache


# ---------------------------------------------------------------------------
# is_duplicate — first screenshot per session
# ---------------------------------------------------------------------------


def test_is_duplicate_first_screenshot_per_session_returns_false(svc) -> None:
    result = svc.is_duplicate(
        session_id="brand-new-session",
        current_hash="deadbeef01234567",
        trigger=ScreenshotTrigger.PERIODIC,
    )
    assert result is False


def test_is_duplicate_first_screenshot_populates_cache(svc) -> None:
    svc.is_duplicate("session-x", "deadbeef01234567", ScreenshotTrigger.PERIODIC)
    assert "session-x" in svc._last_hash_cache


def test_is_duplicate_different_sessions_are_independent(svc) -> None:
    # Prime session A
    svc.is_duplicate("session-a", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    # session B has never been seen — should be False even with same hash
    result = svc.is_duplicate("session-b", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)
    assert result is False


# ---------------------------------------------------------------------------
# is_duplicate — duplicate detection via imagehash
# ---------------------------------------------------------------------------


def test_is_duplicate_returns_true_when_distance_below_threshold(svc) -> None:
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=3)  # 3 <= 5 (threshold)
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff2222", ScreenshotTrigger.PERIODIC)

    assert result is True


def test_is_duplicate_returns_true_when_distance_equals_threshold(svc) -> None:
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=5)  # exactly at threshold
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff2222", ScreenshotTrigger.PERIODIC)

    assert result is True


def test_is_duplicate_returns_false_when_distance_above_threshold(svc) -> None:
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=6)  # 6 > 5
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff2222", ScreenshotTrigger.PERIODIC)

    assert result is False


def test_is_duplicate_returns_false_on_imagehash_exception(svc) -> None:
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash", side_effect=ValueError("bad hash")):
        result = svc.is_duplicate("s1", "badhash", ScreenshotTrigger.PERIODIC)

    assert result is False


def test_is_duplicate_updates_cache_after_each_call(svc) -> None:
    svc.is_duplicate("s1", "hash-one", ScreenshotTrigger.PERIODIC)
    svc.is_duplicate("s1", "hash-two", ScreenshotTrigger.PERIODIC)

    assert svc._last_hash_cache["s1"].hash_value == "hash-two"


# ---------------------------------------------------------------------------
# is_duplicate — threshold variants
# ---------------------------------------------------------------------------


def test_is_duplicate_threshold_zero_only_exact_match_is_duplicate() -> None:
    """With threshold=0, only distance==0 (identical hash) triggers duplicate."""
    svc = _make_service(threshold=0)
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=0)
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    assert result is True


def test_is_duplicate_threshold_zero_distance_one_is_not_duplicate() -> None:
    svc = _make_service(threshold=0)
    svc.is_duplicate("s1", "aaaa0000ffff1111", ScreenshotTrigger.PERIODIC)

    with patch("imagehash.hex_to_hash") as mock_hex:
        h = MagicMock()
        h.__sub__ = MagicMock(return_value=1)
        mock_hex.return_value = h

        result = svc.is_duplicate("s1", "aaaa0000ffff2222", ScreenshotTrigger.PERIODIC)

    assert result is False


# ---------------------------------------------------------------------------
# _evict_stale
# ---------------------------------------------------------------------------


def test_evict_stale_does_nothing_when_under_max_size(svc) -> None:
    for i in range(10):
        svc._last_hash_cache[f"session-{i}"] = MagicMock(last_seen=time.monotonic())

    svc._evict_stale()

    assert len(svc._last_hash_cache) == 10


def test_evict_stale_removes_old_entries_when_over_max_size(svc) -> None:
    from app.application.services.screenshot_dedup_service import _CACHE_TTL_SECONDS, _MAX_CACHE_SIZE

    # Fill to just over limit
    stale_time = time.monotonic() - (_CACHE_TTL_SECONDS + 100)
    fresh_time = time.monotonic()

    # Add _MAX_CACHE_SIZE + 1 entries: some stale, some fresh
    for i in range(_MAX_CACHE_SIZE + 1):
        entry = MagicMock()
        entry.last_seen = stale_time if i < 10 else fresh_time
        svc._last_hash_cache[f"session-{i}"] = entry

    svc._evict_stale()

    # All 10 stale entries should be removed
    assert len(svc._last_hash_cache) == _MAX_CACHE_SIZE + 1 - 10


def test_evict_stale_does_not_remove_fresh_entries(svc) -> None:
    from app.application.services.screenshot_dedup_service import _MAX_CACHE_SIZE

    # Overfill with all fresh entries
    fresh_time = time.monotonic()
    for i in range(_MAX_CACHE_SIZE + 5):
        entry = MagicMock()
        entry.last_seen = fresh_time
        svc._last_hash_cache[f"session-{i}"] = entry

    svc._evict_stale()

    # Nothing should be removed (all fresh)
    assert len(svc._last_hash_cache) == _MAX_CACHE_SIZE + 5


# ---------------------------------------------------------------------------
# find_original_key
# ---------------------------------------------------------------------------


def test_find_original_key_returns_last_non_duplicate_storage_key(svc) -> None:
    screenshots = [
        _make_screenshot("key/0001.jpg", is_duplicate=False),
        _make_screenshot("key/0002.jpg", is_duplicate=False),
        _make_screenshot("key/0003.jpg", is_duplicate=True),
    ]

    result = svc.find_original_key("s1", screenshots)

    assert result == "key/0002.jpg"


def test_find_original_key_returns_none_when_all_are_duplicates(svc) -> None:
    screenshots = [
        _make_screenshot("key/0001.jpg", is_duplicate=True),
        _make_screenshot("key/0002.jpg", is_duplicate=True),
    ]

    result = svc.find_original_key("s1", screenshots)

    assert result is None


def test_find_original_key_returns_none_for_empty_list(svc) -> None:
    result = svc.find_original_key("s1", [])
    assert result is None


def test_find_original_key_returns_only_non_duplicate(svc) -> None:
    screenshots = [
        _make_screenshot("key/0001.jpg", is_duplicate=False),
    ]

    result = svc.find_original_key("s1", screenshots)

    assert result == "key/0001.jpg"


def test_find_original_key_scans_in_reverse_order(svc) -> None:
    """Most recent non-duplicate should be preferred (reversed scan)."""
    screenshots = [
        _make_screenshot("key/0001.jpg", is_duplicate=False),
        _make_screenshot("key/0002.jpg", is_duplicate=False),
    ]

    result = svc.find_original_key("s1", screenshots)

    assert result == "key/0002.jpg"


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


def test_clear_session_removes_session_from_cache(svc) -> None:
    svc.is_duplicate("s1", "deadbeef01234567", ScreenshotTrigger.PERIODIC)
    assert "s1" in svc._last_hash_cache

    svc.clear_session("s1")

    assert "s1" not in svc._last_hash_cache


def test_clear_session_is_idempotent_when_session_not_in_cache(svc) -> None:
    # Should not raise even if session was never added
    svc.clear_session("ghost-session")


def test_clear_session_does_not_remove_other_sessions(svc) -> None:
    svc.is_duplicate("s1", "hash-a", ScreenshotTrigger.PERIODIC)
    svc.is_duplicate("s2", "hash-b", ScreenshotTrigger.PERIODIC)

    svc.clear_session("s1")

    assert "s1" not in svc._last_hash_cache
    assert "s2" in svc._last_hash_cache


# ---------------------------------------------------------------------------
# compute_hash
# ---------------------------------------------------------------------------


def test_compute_hash_returns_empty_string_on_import_error(svc) -> None:
    with patch.dict("sys.modules", {"imagehash": None, "PIL": None, "PIL.Image": None}):
        result = svc.compute_hash(b"not-an-image")

    assert result == ""


def test_compute_hash_returns_empty_string_on_invalid_image_bytes(svc) -> None:
    with patch("PIL.Image.open", side_effect=Exception("invalid image")):
        result = svc.compute_hash(b"\x00\x01\x02")

    assert result == ""


def test_compute_hash_returns_string_result_from_imagehash(svc) -> None:
    mock_hash = MagicMock()
    mock_hash.__str__ = MagicMock(return_value="abcdef0123456789")
    mock_image = MagicMock()

    with (
        patch("PIL.Image.open", return_value=mock_image),
        patch("imagehash.average_hash", return_value=mock_hash),
    ):
        result = svc.compute_hash(b"fake-png-bytes")

    assert result == "abcdef0123456789"
