"""Persistent scratchpad for agent working notes that survive all compaction.

The scratchpad is an append-only notepad where the agent records key findings
(URLs visited, decisions made, errors encountered, intermediate results).
Its content is injected TRANSIENTLY before each LLM call — it is never
persisted into conversation memory, so it survives all forms of compaction
(smart_compact, graduated_compact, structured_compact).

FIFO eviction at configurable max_chars prevents unbounded growth.

Session-scoped lifecycle: created in PlanActFlow alongside ToolResultStore.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_SCRATCHPAD_HEADER = "[SCRATCHPAD — Your persistent working notes (survives compaction):]"


@dataclass(frozen=True)
class ScratchpadEntry:
    """Single note in the scratchpad."""

    note: str
    timestamp: float = field(default_factory=time.time)
    tag: str = ""


class Scratchpad:
    """Append-only notepad with FIFO eviction.

    Args:
        max_chars: Maximum total characters across all entries before eviction.
        max_entries: Maximum number of entries before FIFO eviction.
    """

    def __init__(self, max_chars: int = 4000, max_entries: int = 50) -> None:
        self._max_chars = max_chars
        self._max_entries = max_entries
        self._entries: deque[ScratchpadEntry] = deque()
        self._total_chars: int = 0

    def append(self, note: str, tag: str = "") -> None:
        """Add a note to the scratchpad.

        Args:
            note: The note text to record.
            tag: Optional category tag (e.g. "url", "error", "decision").
        """
        entry = ScratchpadEntry(note=note, tag=tag)
        self._entries.append(entry)
        self._total_chars += len(note)
        self._evict_if_needed()
        logger.debug("Scratchpad: appended note (%d chars, tag=%r)", len(note), tag)

    def get_content(self) -> str:
        """Render scratchpad content for injection into LLM context.

        Returns:
            Formatted string with header and numbered entries, or empty string if no entries.
        """
        if not self._entries:
            return ""

        lines = [_SCRATCHPAD_HEADER]
        for i, entry in enumerate(self._entries, 1):
            tag_prefix = f"[{entry.tag}] " if entry.tag else ""
            lines.append(f"{i}. {tag_prefix}{entry.note}")

        return "\n".join(lines)

    def clear(self) -> int:
        """Clear all entries.

        Returns:
            Number of entries cleared.
        """
        count = len(self._entries)
        self._entries.clear()
        self._total_chars = 0
        return count

    @property
    def is_empty(self) -> bool:
        """Check if the scratchpad has no entries."""
        return len(self._entries) == 0

    @property
    def entry_count(self) -> int:
        """Number of entries currently in the scratchpad."""
        return len(self._entries)

    def _evict_if_needed(self) -> None:
        """FIFO eviction when over max_chars or max_entries."""
        # Evict by entry count
        while len(self._entries) > self._max_entries:
            evicted = self._entries.popleft()
            self._total_chars -= len(evicted.note)

        # Evict by total char budget
        while self._total_chars > self._max_chars and self._entries:
            evicted = self._entries.popleft()
            self._total_chars -= len(evicted.note)
