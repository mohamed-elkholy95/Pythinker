"""Pre-planning web search: inject real-time search results into planning prompts.

The key insight is that the planner already spends 1-5 seconds on thinking,
ToT exploration, and memory retrieval. We fire the search at the START and
await at the END — the search completes during existing work, adding zero
perceived latency.

Timeline inside _create_plan_inner:
    0ms     Fire search task (background)
    10ms    Requirements extraction
    50ms    Thinking stream (1-3s, visible to user)
    3000ms  ToT exploration (0-5s)
    3200ms  Memory retrieval (200ms)
    3400ms  Await search task ← already done!
            Build prompt with search results
            Call LLM to generate plan
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detector — heuristic-based, < 1 ms, no LLM call
# ---------------------------------------------------------------------------

# Temporal keywords that suggest the user wants current information
_TEMPORAL_KEYWORDS: set[str] = {
    "latest",
    "current",
    "recent",
    "newest",
    "new",
    "today",
    "now",
    "2025",
    "2026",
    "this year",
    "this month",
}

# Comparison patterns
_COMPARISON_KEYWORDS: set[str] = {
    "compare",
    "comparison",
    "vs",
    "versus",
    "difference between",
    "differences between",
    "better than",
    "worse than",
    "pros and cons",
}

# Product/research patterns that benefit from current data
_RESEARCH_KEYWORDS: set[str] = {
    "price",
    "pricing",
    "cost",
    "benchmark",
    "benchmarks",
    "specs",
    "specifications",
    "features",
    "release",
    "version",
    "update",
    "changelog",
    "roadmap",
    "availability",
    "performance",
}

# Negative filters — skip search for these task types
_SKIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(write|code|refactor|fix bug|debug|implement|create file|build)\b", re.IGNORECASE),
    re.compile(r"^(hi|hello|hey|thanks|thank you|good morning|good evening)\b", re.IGNORECASE),
    re.compile(r"\b(what is a |explain |define |how does .+ work|concept of)\b", re.IGNORECASE),
]


@dataclass(frozen=True, slots=True)
class PrePlanningSearchResult:
    """Result of a pre-planning search execution."""

    triggered: bool
    search_context: str = ""
    total_results: int = 0
    duration_ms: float = 0.0
    queries: list[str] = field(default_factory=list)


class PrePlanningSearchDetector:
    """Heuristic detector that decides whether a user message needs pre-planning search.

    Runs in < 1 ms with no LLM call — pure keyword/pattern matching.
    """

    @staticmethod
    def should_search(message: str) -> tuple[bool, list[str]]:
        """Check if the message would benefit from real-time web search before planning.

        Args:
            message: The user's raw message.

        Returns:
            Tuple of (should_search, list of trigger reasons).
        """
        msg_lower = message.lower()

        # Negative filters first — skip for code tasks, greetings, concept explanations
        for pattern in _SKIP_PATTERNS:
            if pattern.search(message):
                return False, []

        reasons: list[str] = []

        # Check temporal keywords
        for kw in _TEMPORAL_KEYWORDS:
            if kw in msg_lower:
                reasons.append(f"temporal:{kw}")
                break  # one reason per category is enough

        # Check comparison patterns
        for kw in _COMPARISON_KEYWORDS:
            if kw in msg_lower:
                reasons.append(f"comparison:{kw}")
                break

        # Check research/product patterns
        for kw in _RESEARCH_KEYWORDS:
            if kw in msg_lower:
                reasons.append(f"research:{kw}")
                break

        should = len(reasons) >= 1
        return should, reasons


class PrePlanningSearchExecutor:
    """Executes 1-3 fast web searches concurrently before planning.

    Designed to run in the background while the planner does thinking/ToT/memory work.
    """

    # Maximum total characters for the formatted search context
    MAX_CONTEXT_CHARS = 1500
    # Per-query timeout
    QUERY_TIMEOUT_S = 5.0

    def __init__(self, search_engine: SearchEngine) -> None:
        self._search_engine = search_engine

    @staticmethod
    def generate_search_queries(message: str, reasons: list[str]) -> list[str]:
        """Generate 1-3 targeted search queries from the user message.

        Extracts comparison entities (split on "vs"/"and") and builds
        targeted queries. Never returns more than 3 queries.

        Args:
            message: The user's raw message.
            reasons: Trigger reasons from the detector.

        Returns:
            List of 1-3 search query strings.
        """
        queries: list[str] = []

        # Extract entities from comparison patterns like "A vs B vs C" or "A and B"
        # Strip common prefixes like "compare", "what is the difference between"
        cleaned = re.sub(
            r"^(compare|what (?:is|are) the (?:difference|differences) between)\s+",
            "",
            message.strip(),
            flags=re.IGNORECASE,
        )

        # Split on "vs", "versus", " and " (but not "and" inside words)
        entities = re.split(r"\s+(?:vs\.?|versus|and)\s+", cleaned, flags=re.IGNORECASE)
        entities = [e.strip().rstrip("?.!,") for e in entities if e.strip()]

        if len(entities) >= 2:
            # Comparison query: each entity gets its own "latest" query
            queries.extend(f"{entity} latest 2026" for entity in entities[:3])
        elif entities:
            # Single entity — broad search
            queries.append(f"{entities[0]} latest 2026")

        # If no entities extracted, fall back to the raw message
        if not queries:
            # Trim to a reasonable query length
            trimmed = message[:120].strip()
            queries.append(f"{trimmed} latest 2026")

        return queries[:3]

    async def execute(self, message: str, reasons: list[str]) -> PrePlanningSearchResult:
        """Run pre-planning searches concurrently.

        Args:
            message: The user's raw message.
            reasons: Trigger reasons from the detector.

        Returns:
            PrePlanningSearchResult with formatted context.
        """
        queries = self.generate_search_queries(message, reasons)
        if not queries:
            return PrePlanningSearchResult(triggered=False)

        start = time.monotonic()

        # Fire all searches concurrently with a global timeout
        async def _safe_search(query: str) -> list[tuple[str, str, str]]:
            """Run a single search, returning list of (title, url, snippet)."""
            try:
                result = await asyncio.wait_for(
                    self._search_engine.search(query, date_range="past_month"),
                    timeout=self.QUERY_TIMEOUT_S,
                )
                if result.success and result.data:
                    return [(r.title, r.link, r.snippet) for r in result.data.results[:5]]
            except TimeoutError:
                logger.warning(f"Pre-planning search timed out for query: {query}")
            except Exception:
                logger.warning(f"Pre-planning search failed for query: {query}", exc_info=True)
            return []

        all_results = await asyncio.gather(*[_safe_search(q) for q in queries])

        # Flatten and deduplicate by URL
        seen_urls: set[str] = set()
        unique_items: list[tuple[str, str, str]] = []
        for batch in all_results:
            for title, url, snippet in batch:
                if url not in seen_urls:
                    seen_urls.add(url)
                    unique_items.append((title, url, snippet))

        duration_ms = (time.monotonic() - start) * 1000

        if not unique_items:
            return PrePlanningSearchResult(
                triggered=True,
                search_context="",
                total_results=0,
                duration_ms=duration_ms,
                queries=queries,
            )

        context = self._format_context(unique_items)

        return PrePlanningSearchResult(
            triggered=True,
            search_context=context,
            total_results=len(unique_items),
            duration_ms=duration_ms,
            queries=queries,
        )

    @staticmethod
    def _format_context(items: list[tuple[str, str, str]]) -> str:
        """Condense search results into a compact context string.

        Args:
            items: List of (title, url, snippet) tuples.

        Returns:
            Formatted string capped at MAX_CONTEXT_CHARS.
        """
        lines: list[str] = []
        total_len = 0

        for title, _url, snippet in items:
            # Title + snippet only (URL omitted — planner doesn't need it)
            line = f"- {title}: {snippet}" if snippet else f"- {title}"
            if total_len + len(line) > PrePlanningSearchExecutor.MAX_CONTEXT_CHARS:
                break
            lines.append(line)
            total_len += len(line) + 1  # +1 for newline

        return "\n".join(lines)
