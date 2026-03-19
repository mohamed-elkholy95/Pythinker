"""In-process store for RESEARCH_TRACE memory tier.

Keeps transient search breadcrumbs alive for a configurable TTL, then
expires them automatically.  Durable entries (DISTILLED_OUTCOME) bypass
TTL and survive until the session is explicitly cleared.
"""

from collections import defaultdict
from collections.abc import Set
from datetime import UTC, datetime, timedelta

from app.domain.models.research_trace import TraceEntry, TraceTier, TraceType


class ResearchTraceStore:
    """Lightweight in-memory store for research trace entries.

    Thread-safety note: this store uses plain asyncio semantics and is
    not safe for concurrent access from multiple OS threads.  Use it
    from a single event-loop only.
    """

    __slots__ = ("_traces", "_ttl")

    def __init__(self, ttl_seconds: int = 7200) -> None:
        self._ttl: int = ttl_seconds
        self._traces: dict[str, list[TraceEntry]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def add(self, entry: TraceEntry) -> None:
        """Append a trace entry for its session."""
        self._traces[entry.session_id].append(entry)

    async def clear_session(self, session_id: str) -> None:
        """Remove all trace entries for a session."""
        self._traces.pop(session_id, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_session_traces(
        self,
        session_id: str,
        trace_types: Set[TraceType] | None = None,
    ) -> list[TraceEntry]:
        """Return entries for *session_id*, honouring TTL and optional type filter.

        Transient entries older than *_ttl* seconds are excluded.
        Durable entries are always included.
        ``trace_types``, when provided, further restricts which types are returned.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl)
        results: list[TraceEntry] = []
        for entry in self._traces.get(session_id, []):
            if entry.tier is TraceTier.TRANSIENT and entry.created_at < cutoff:
                continue
            if trace_types is not None and entry.trace_type not in trace_types:
                continue
            results.append(entry)
        return results

    async def get_distilled_outcomes(self, session_id: str) -> list[TraceEntry]:
        """Convenience wrapper returning only DISTILLED_OUTCOME entries."""
        return await self.get_session_traces(session_id, trace_types={TraceType.DISTILLED_OUTCOME})

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def prune_expired(self) -> int:
        """Remove all expired transient entries across all sessions.

        Returns the total number of entries removed.
        Empty session buckets are cleaned up after pruning.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self._ttl)
        removed = 0
        empty_sessions: list[str] = []

        for session_id, entries in self._traces.items():
            before = len(entries)
            kept = [e for e in entries if not (e.tier is TraceTier.TRANSIENT and e.created_at < cutoff)]
            self._traces[session_id] = kept
            removed += before - len(kept)
            if not kept:
                empty_sessions.append(session_id)

        for session_id in empty_sessions:
            self._traces.pop(session_id, None)

        return removed
