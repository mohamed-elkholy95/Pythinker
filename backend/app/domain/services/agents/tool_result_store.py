"""External storage for large tool results to reduce conversation context bloat.

Tool results from browser pages, shell output, and file reads regularly exceed 4K chars.
Rather than keeping full content in conversation memory (where it counts against the LLM's
context window), ToolResultStore offloads large results to an in-memory LRU cache and
keeps only a compact preview + reference marker in the conversation.

The agent can retrieve full content via the reference ID when needed (e.g. for
follow-up analysis), and graduated compaction (Component 2) can reference stored
content instead of destroying it.

Phase 1C enhancements (Claude Code pattern):
- Per-message aggregate budget (MAX_TOOL_RESULTS_PER_MESSAGE_CHARS) prevents N parallel
  tools from collectively overwhelming context in a single turn.
- Disk-backed spillover: evicted entries are written to /tmp before being discarded,
  and retrieve() falls back to disk on LRU miss.

Session-scoped lifecycle: created in PlanActFlow, garbage-collected on session end.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Claude Code uses 200K per-message aggregate cap (toolLimits.ts)
DEFAULT_PER_MESSAGE_BUDGET_CHARS = 200_000


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
        per_message_budget_chars: Max aggregate chars for tool results in a single turn.
        session_id: Session ID for disk spillover path isolation.
    """

    def __init__(
        self,
        offload_threshold: int = 4000,
        preview_chars: int = 500,
        max_entries: int = 200,
        per_message_budget_chars: int = DEFAULT_PER_MESSAGE_BUDGET_CHARS,
        session_id: str | None = None,
    ) -> None:
        self._offload_threshold = offload_threshold
        self._preview_chars = preview_chars
        self._max_entries = max_entries
        self._per_message_budget_chars = per_message_budget_chars
        self._store: OrderedDict[str, StoredResult] = OrderedDict()
        self._total_stored: int = 0
        self._total_evicted: int = 0
        self._total_bytes_saved: int = 0
        self._total_spilled_to_disk: int = 0

        # Disk spillover directory (session-isolated, ephemeral)
        self._session_id = session_id or uuid.uuid4().hex[:12]
        self._disk_dir = Path(f"/tmp/pythinker/tool_results/{self._session_id}")

    # ── Public API ────────────────────────────────────────────────────

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
            "Stored tool result %s (%s, %d chars -> %d char preview)",
            result_id,
            function_name,
            len(content),
            len(preview),
        )
        return result_id, preview

    def retrieve(self, result_id: str) -> str | None:
        """Retrieve full content by reference ID.

        Returns None if the entry has been evicted from both LRU and disk.
        Accessing an entry refreshes its LRU position.
        """
        # Try in-memory LRU first
        entry = self._store.get(result_id)
        if entry is not None:
            self._store.move_to_end(result_id)
            return entry.full_content

        # Fall back to disk spillover
        return self._retrieve_from_disk(result_id)

    def enforce_message_budget(
        self,
        results: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Enforce per-message aggregate budget on parallel tool results.

        When multiple tools return results in a single turn, their combined size
        can blow up context. This method offloads the largest results first until
        the aggregate is within budget.

        Args:
            results: List of (function_name, content) tuples from parallel tool calls.

        Returns:
            List of (function_name, content_or_preview) tuples within budget.
        """
        total_chars = sum(len(content) for _, content in results)
        if total_chars <= self._per_message_budget_chars:
            return results

        def _fit_preview(content: str, result_id: str, max_chars: int) -> str:
            """Build a preview that fits a specific character budget."""
            if max_chars <= 0:
                return ""

            ref_marker = f" [ref:{result_id}]"
            if max_chars <= len(ref_marker):
                return ref_marker[:max_chars]

            body_budget = max_chars - len(ref_marker)
            if len(content) <= body_budget:
                return content + ref_marker

            if body_budget <= 3:
                return content[:body_budget] + ref_marker

            body = content[: body_budget - 3]
            return f"{body}...{ref_marker}"

        indexed = [(i, fn, content) for i, (fn, content) in enumerate(results)]
        indexed.sort(key=lambda x: len(x[2]), reverse=True)

        output_by_index: dict[int, tuple[str, str]] = {idx: (fn_name, content) for idx, fn_name, content in indexed}
        result_ids_by_index: dict[int, str] = {}
        offloaded_indices: set[int] = set()
        running_total = total_chars

        for idx, fn_name, content in indexed:
            if running_total <= self._per_message_budget_chars:
                break

            result_id, preview = self.store(content, fn_name)
            output_by_index[idx] = (fn_name, preview)
            result_ids_by_index[idx] = result_id
            offloaded_indices.add(idx)
            running_total -= len(content) - len(preview)
            logger.debug(
                "Message budget: offloaded %s (%d chars -> preview), remaining=%d",
                fn_name,
                len(content),
                running_total,
            )

        if running_total > self._per_message_budget_chars:
            logger.warning(
                "Message budget still exceeded after offloading %d result(s); returning best-effort previews",
                len(offloaded_indices),
            )
            remaining_budget = self._per_message_budget_chars
            budgeted_results: list[tuple[str, str]] = []

            for idx in range(len(results)):
                fn_name, content = output_by_index[idx]
                if len(content) <= remaining_budget:
                    budgeted_results.append((fn_name, content))
                    remaining_budget -= len(content)
                    continue

                result_id = result_ids_by_index.get(idx)
                if result_id is None:
                    preview = content[:remaining_budget]
                else:
                    preview = _fit_preview(content, result_id, remaining_budget)

                budgeted_results.append((fn_name, preview))
                remaining_budget -= len(preview)

            return budgeted_results

        return [output_by_index[i] for i in range(len(results))]

    def get_stats(self) -> dict:
        """Return store statistics for observability."""
        return {
            "current_entries": len(self._store),
            "max_entries": self._max_entries,
            "total_stored": self._total_stored,
            "total_evicted": self._total_evicted,
            "total_bytes_saved": self._total_bytes_saved,
            "total_spilled_to_disk": self._total_spilled_to_disk,
            "per_message_budget_chars": self._per_message_budget_chars,
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
        """Evict oldest entries if over capacity, spilling to disk first."""
        while len(self._store) > self._max_entries:
            evicted_id, entry = self._store.popitem(last=False)
            self._spill_to_disk(entry)
            self._total_evicted += 1
            logger.debug("Evicted tool result %s from LRU (spilled to disk)", evicted_id)

    def _spill_to_disk(self, entry: StoredResult) -> None:
        """Write an evicted entry to disk for later retrieval."""
        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
            path = self._disk_dir / f"{entry.result_id}.json"
            payload = {
                "result_id": entry.result_id,
                "function_name": entry.function_name,
                "full_content": entry.full_content,
                "original_size": entry.original_size,
                "stored_at": entry.stored_at,
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            self._total_spilled_to_disk += 1
            logger.debug("Spilled %s to disk (%d chars)", entry.result_id, entry.original_size)
        except Exception:
            logger.warning("Failed to spill %s to disk", entry.result_id, exc_info=True)

    def _retrieve_from_disk(self, result_id: str) -> str | None:
        """Try to retrieve a previously evicted entry from disk."""
        path = self._disk_dir / f"{result_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            content = payload.get("full_content")
            if content:
                logger.debug("Retrieved %s from disk (%d chars)", result_id, len(content))
            return content
        except Exception:
            logger.warning("Failed to retrieve %s from disk", result_id, exc_info=True)
            return None

    def cleanup_disk(self) -> None:
        """Remove disk spillover directory. Call on session teardown."""
        try:
            if self._disk_dir.exists():
                import shutil

                shutil.rmtree(self._disk_dir, ignore_errors=True)
                logger.debug("Cleaned up disk spillover at %s", self._disk_dir)
        except Exception:
            logger.warning("Failed to clean up disk spillover", exc_info=True)

    @property
    def disk_dir(self) -> Path:
        """Path to the disk spillover directory (for testing/inspection)."""
        return self._disk_dir
