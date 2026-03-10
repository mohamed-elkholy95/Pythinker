"""External storage for large tool results to reduce conversation context bloat.

Tool results from browser pages, shell output, and file reads regularly exceed 4K chars.
Rather than keeping full content in conversation memory (where it counts against the LLM's
context window), ToolResultStore offloads large results to an in-memory LRU cache and
keeps only a compact preview + reference marker in the conversation.

The agent can retrieve full content via the reference ID when needed (e.g. for
follow-up analysis), and graduated compaction (Component 2) can reference stored
content instead of destroying it.

Session-scoped lifecycle: created in PlanActFlow, garbage-collected on session end.
"""

import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredResult:
    """Immutable record of an offloaded tool result."""

    result_id: str
    function_name: str
    full_content: str
    original_size: int
    preview: str
    stored_at: float = field(default_factory=time.time)


class ToolResultStore:
    """LRU cache for large tool results offloaded from conversation memory.

    Args:
        offload_threshold: Minimum content length (chars) to trigger offloading.
        preview_chars: Maximum characters to keep in the conversation preview.
        max_entries: Maximum stored results before LRU eviction kicks in.
    """

    def __init__(
        self,
        offload_threshold: int = 4000,
        preview_chars: int = 500,
        max_entries: int = 200,
    ) -> None:
        self._offload_threshold = offload_threshold
        self._preview_chars = preview_chars
        self._max_entries = max_entries
        self._store: OrderedDict[str, StoredResult] = OrderedDict()
        self._total_stored: int = 0
        self._total_evicted: int = 0
        self._total_bytes_saved: int = 0

    # ── Public API ────────────────────────────────────────────────────

    @property
    def offload_threshold(self) -> int:
        """Compatibility accessor for callers that still read the threshold directly."""
        return self._offload_threshold

    def should_offload(self, content: str) -> bool:
        """Check whether content exceeds the offload threshold."""
        return len(content) > self._offload_threshold

    def store(
        self,
        content: str,
        function_name: str,
        result_id: str | None = None,
    ) -> tuple[str, str]:
        """Store content externally and return (result_id, preview).

        Args:
            content: Full tool result content to store.
            function_name: Name of the tool that produced this result.
            result_id: Optional explicit ID; auto-generated if None.

        Returns:
            Tuple of (result_id, preview_text) for embedding in conversation memory.
        """
        if result_id is None:
            result_id = f"trs-{uuid.uuid4().hex[:12]}"

        preview = self._build_preview(content, result_id)

        entry = StoredResult(
            result_id=result_id,
            function_name=function_name,
            full_content=content,
            original_size=len(content),
            preview=preview,
        )

        # LRU: move to end if key exists, else insert
        if result_id in self._store:
            self._store.move_to_end(result_id)
            self._store[result_id] = entry
        else:
            self._store[result_id] = entry
            self._total_stored += 1
            self._total_bytes_saved += len(content) - len(preview)
            self._evict_if_needed()

        logger.debug(
            "Stored tool result %s (%s, %d chars → %d char preview)",
            result_id,
            function_name,
            len(content),
            len(preview),
        )
        return result_id, preview

    def retrieve(self, result_id: str) -> str | None:
        """Retrieve full content by reference ID.

        Returns None if the entry has been evicted from the LRU cache.
        Accessing an entry refreshes its LRU position.
        """
        entry = self._store.get(result_id)
        if entry is None:
            return None
        # Refresh LRU position
        self._store.move_to_end(result_id)
        return entry.full_content

    def get_stats(self) -> dict:
        """Return store statistics for observability."""
        return {
            "current_entries": len(self._store),
            "max_entries": self._max_entries,
            "total_stored": self._total_stored,
            "total_evicted": self._total_evicted,
            "total_bytes_saved": self._total_bytes_saved,
        }

    # ── Internals ─────────────────────────────────────────────────────

    def _build_preview(self, content: str, result_id: str) -> str:
        """Build a truncated preview that ends at a complete line boundary."""
        ref_marker = f" [ref:{result_id}]"
        budget = self._preview_chars - len(ref_marker)
        if budget <= 0:
            return ref_marker.strip()

        if len(content) <= budget:
            return content + ref_marker

        # Truncate at last newline within budget for clean line breaks
        truncated = content[:budget]
        last_newline = truncated.rfind("\n")
        if last_newline > budget // 2:
            truncated = truncated[: last_newline + 1]

        chars_omitted = len(content) - len(truncated)
        return f"{truncated}... ({chars_omitted} chars omitted){ref_marker}"

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if over capacity."""
        while len(self._store) > self._max_entries:
            evicted_id, _entry = self._store.popitem(last=False)
            self._total_evicted += 1
            logger.debug("Evicted tool result %s from store (LRU)", evicted_id)
