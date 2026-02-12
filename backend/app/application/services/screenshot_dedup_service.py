"""Screenshot deduplication service using perceptual hashing."""

import logging
import time
from io import BytesIO

from app.core.config import get_settings
from app.domain.models.screenshot import ScreenshotTrigger, SessionScreenshot

logger = logging.getLogger(__name__)

# Non-deduplicatable triggers (always save these)
_ALWAYS_SAVE_TRIGGERS = frozenset(
    {
        ScreenshotTrigger.SESSION_START,
        ScreenshotTrigger.SESSION_END,
        ScreenshotTrigger.TOOL_BEFORE,
        ScreenshotTrigger.TOOL_AFTER,
    }
)

# Maximum entries in the hash cache before stale entries are evicted
_MAX_CACHE_SIZE = 500
# Entries older than this are considered stale (2 hours)
_CACHE_TTL_SECONDS = 7200


class _CacheEntry:
    """Hash + timestamp for TTL-based eviction."""

    __slots__ = ("hash_value", "last_seen")

    def __init__(self, hash_value: str) -> None:
        self.hash_value = hash_value
        self.last_seen = time.monotonic()


class ScreenshotDedupService:
    """Detect duplicate screenshots using perceptual hashing (average hash).

    Only deduplicates PERIODIC screenshots. Tool-triggered and session
    lifecycle screenshots are always saved for timeline accuracy.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        # In-memory cache of last hash per session for fast comparison
        self._last_hash_cache: dict[str, _CacheEntry] = {}

    def _evict_stale(self) -> None:
        """Remove entries older than TTL when cache exceeds max size."""
        if len(self._last_hash_cache) <= _MAX_CACHE_SIZE:
            return
        now = time.monotonic()
        stale_keys = [k for k, v in self._last_hash_cache.items() if now - v.last_seen > _CACHE_TTL_SECONDS]
        for k in stale_keys:
            del self._last_hash_cache[k]

    def compute_hash(self, image_bytes: bytes) -> str:
        """Compute average perceptual hash (64-bit, 16 hex chars).

        Returns empty string on failure (caller should treat as non-duplicate).
        """
        try:
            import imagehash
            from PIL import Image

            img = Image.open(BytesIO(image_bytes))
            return str(imagehash.average_hash(img, hash_size=8))
        except Exception as e:
            logger.debug("Perceptual hash computation failed: %s", e)
            return ""

    def is_duplicate(
        self,
        session_id: str,
        current_hash: str,
        trigger: ScreenshotTrigger,
    ) -> bool:
        """Check if screenshot is a duplicate of the previous one.

        Returns True if the screenshot should be deduplicated (skipped in S3).
        Always returns False for non-PERIODIC triggers.
        """
        if not current_hash:
            return False

        # Never deduplicate explicit triggers
        if trigger in _ALWAYS_SAVE_TRIGGERS:
            self._last_hash_cache[session_id] = _CacheEntry(current_hash)
            return False

        previous_entry = self._last_hash_cache.get(session_id)
        self._last_hash_cache[session_id] = _CacheEntry(current_hash)
        self._evict_stale()

        if previous_entry is None:
            return False

        try:
            import imagehash

            distance = imagehash.hex_to_hash(current_hash) - imagehash.hex_to_hash(previous_entry.hash_value)
            threshold = self._settings.screenshot_dedup_threshold

            if distance <= threshold:
                logger.debug(
                    "Duplicate screenshot for session %s (distance=%d, threshold=%d)",
                    session_id,
                    distance,
                    threshold,
                )
                return True
            return False
        except Exception as e:
            logger.debug("Duplicate detection failed: %s", e)
            return False

    def find_original_key(self, session_id: str, recent_screenshots: list[SessionScreenshot]) -> str | None:
        """Find the storage_key of the most recent non-duplicate screenshot.

        Used to set original_storage_key on duplicate screenshots.
        """
        for screenshot in reversed(recent_screenshots):
            if not screenshot.is_duplicate:
                return screenshot.storage_key
        return None

    def clear_session(self, session_id: str) -> None:
        """Clean up in-memory cache for a completed session."""
        self._last_hash_cache.pop(session_id, None)
