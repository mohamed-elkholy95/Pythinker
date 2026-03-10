"""Source citation tracking for execution agent reports.

Collects, deduplicates, and indexes source citations from ToolEvent
results during step execution. Builds numbered bibliographies for
citation-aware summarization.

Usage:
    tracker = SourceTracker(max_sources=200)
    tracker.track_tool_event(event)           # called per tool event
    sources = tracker.get_collected_sources()  # list[SourceCitation]
    bib = tracker.build_numbered_source_list() # "[1] Title - URL\n..."
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.domain.models.source_citation import SourceCitation
from app.domain.models.tool_name import ToolName

if TYPE_CHECKING:
    from app.domain.models.event import ToolEvent

logger = logging.getLogger(__name__)


class SourceTracker:
    """Collects and deduplicates source citations from tool events.

    Attributes are intentionally public (prefixed with underscore for convention
    consistency with ExecutionAgent) to allow the coordinator to read citation
    state for prompt-building and report events.
    """

    __slots__ = (
        "_citation_counter",
        "_collected_sources",
        "_max_collected_sources",
        "_seen_urls",
        "_url_to_citation",
    )

    def __init__(self, *, max_sources: int = 200) -> None:
        self._max_collected_sources = max_sources
        self._collected_sources: list[SourceCitation] = []
        self._seen_urls: set[str] = set()
        self._citation_counter: int = 0
        self._url_to_citation: dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────

    def track_tool_event(self, event: ToolEvent) -> None:
        """Extract and track source citations from a completed tool event.

        Dispatches to search or browser extractors based on the tool name.

        Args:
            event: ToolEvent that completed execution.
        """
        if not event.function_result or not event.function_result.success:
            return

        access_time = event.started_at or datetime.now(UTC)

        if event.function_name in {ToolName.INFO_SEARCH_WEB, ToolName.WIDE_RESEARCH}:
            self._extract_search_sources(event, access_time)
        elif event.function_name in {
            ToolName.BROWSER_NAVIGATE,
            ToolName.BROWSER_GET_CONTENT,
            ToolName.BROWSER_VIEW,
        }:
            self._extract_browser_source(event, access_time)

    def get_collected_sources(self) -> list[SourceCitation]:
        """Return a shallow copy of all collected source citations."""
        return self._collected_sources.copy()

    def build_numbered_source_list(self) -> str:
        """Build a numbered source list for citation-aware summarization.

        Returns:
            Formatted string like:
            [1] Title - URL
            [2] Title - URL
        """
        lines: list[str] = []
        bibliography_sources = self._get_bibliography_sources()
        self._url_to_citation = {}

        for i, source in enumerate(bibliography_sources, start=1):
            # Sanitize multiline titles to prevent citation parser confusion
            title = re.sub(r"\s+", " ", source.title or source.url).strip()
            lines.append(f"[{i}] {title} - {source.url}")
            self._url_to_citation[source.url] = i
        return "\n".join(lines)

    def add_source(self, citation: SourceCitation) -> None:
        """Add a pre-built SourceCitation (e.g., from evidence pipeline).

        Deduplicates by URL. Upgrades search→browser if browser grounding.

        Args:
            citation: A fully constructed SourceCitation to register.
        """
        for i, existing in enumerate(self._collected_sources):
            if existing.url == citation.url:
                # Browser grounding always upgrades a search-typed entry
                if citation.source_type == "browser" and existing.source_type == "search":
                    self._collected_sources[i] = citation
                return
        if len(self._collected_sources) < self._max_collected_sources:
            self._collected_sources.append(citation)

    def restore_sources(self, sources: list[SourceCitation]) -> None:
        """Restore persisted sources from a prior session.

        Used during session reactivation to hydrate the tracker with
        sources from previous report events so hallucination verification
        retains its grounding context.
        """
        self.clear()
        for source in sources:
            if source.url and source.url not in self._seen_urls:
                self._seen_urls.add(source.url)
                self._collected_sources.append(source)
                self._citation_counter += 1
                self._url_to_citation[source.url] = self._citation_counter

    def clear(self) -> None:
        """Reset all tracking state."""
        self._collected_sources.clear()
        self._seen_urls.clear()
        self._citation_counter = 0
        self._url_to_citation.clear()

    @property
    def source_count(self) -> int:
        """Number of tracked sources."""
        return len(self._collected_sources)

    @property
    def citation_counter(self) -> int:
        """Current citation index."""
        return self._citation_counter

    @property
    def url_to_citation(self) -> dict[str, int]:
        """URL → citation-number mapping (read-only reference)."""
        return self._url_to_citation

    # ── Internal Extraction Methods ───────────────────────────────────

    def _extract_search_sources(self, event: ToolEvent, access_time: datetime) -> None:
        """Extract sources from search tool results."""
        results: list = []
        if event.tool_content and hasattr(event.tool_content, "results"):
            results = event.tool_content.results or []
        elif event.function_result and hasattr(event.function_result, "data"):
            data = event.function_result.data
            if isinstance(data, dict) and "results" in data:
                results = data["results"]
            elif isinstance(data, list):
                results = data

        for result in results:
            if hasattr(result, "link"):
                url = result.link
                title = result.title
                snippet = getattr(result, "snippet", None)
            elif isinstance(result, dict):
                url = result.get("link") or result.get("url", "")
                title = result.get("title", "")
                snippet = result.get("snippet")
            else:
                continue

            if not url:
                continue

            existing_index = self._find_source_index(url)
            if existing_index is not None:
                # Never downgrade an already grounded source back to a search snippet.
                continue

            if len(self._collected_sources) >= self._max_collected_sources:
                continue

            self._seen_urls.add(url)
            self._collected_sources.append(
                SourceCitation(
                    url=url,
                    title=title or url,
                    snippet=snippet[:2000] if snippet else None,
                    access_time=access_time,
                    source_type="search",
                )
            )
            self._citation_counter += 1
            self._url_to_citation[url] = self._citation_counter
            logger.debug(
                "Tracked search source [%d]: %s",
                self._citation_counter,
                (title[:50] if title else url[:50]),
            )

    def _extract_browser_source(self, event: ToolEvent, access_time: datetime) -> None:
        """Extract source from browser navigation events."""
        url = event.function_args.get("url", "")
        if not url:
            return

        title = url
        snippet: str | None = None
        if event.tool_content and hasattr(event.tool_content, "content"):
            content = event.tool_content.content
            if content:
                title = self._extract_title_from_content(content) or url
                snippet = self._extract_snippet_from_content(content)

        existing_index = self._find_source_index(url)
        if existing_index is not None:
            existing_source = self._collected_sources[existing_index]
            has_grounded_title = bool(title and title != url)
            has_grounded_snippet = bool(snippet and snippet.strip())
            if not has_grounded_title and not has_grounded_snippet:
                logger.debug("Skipped browser upgrade for %s because no grounded content was extracted", url)
                return

            self._collected_sources[existing_index] = SourceCitation(
                url=url,
                title=title if has_grounded_title else existing_source.title,
                snippet=snippet if has_grounded_snippet else existing_source.snippet,
                access_time=access_time,
                source_type="browser",
            )
            logger.debug("Upgraded tracked source to browser grounding: %s", title[:50])
            return

        if len(self._collected_sources) >= self._max_collected_sources:
            return

        self._seen_urls.add(url)
        self._collected_sources.append(
            SourceCitation(
                url=url,
                title=title,
                snippet=snippet,
                access_time=access_time,
                source_type="browser",
            )
        )
        logger.debug("Tracked browser source: %s", title[:50])

    @staticmethod
    def _extract_title_from_content(content: str) -> str | None:
        """Extract page title from HTML or text content."""
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", content, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()[:200]

        h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", content, re.IGNORECASE)
        if h1_match:
            return h1_match.group(1).strip()[:200]

        md_h1_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
        if md_h1_match:
            return md_h1_match.group(1).strip()[:200]

        return None

    @staticmethod
    def _extract_snippet_from_content(content: str) -> str | None:
        """Extract a compact text snippet from browser-fetched content."""
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        return text[:8000]

    def _get_bibliography_sources(self) -> list[SourceCitation]:
        """Prefer grounded sources when any browser/file evidence exists."""
        grounded_sources = [s for s in self._collected_sources if s.source_type in {"browser", "file"}]
        if grounded_sources:
            return grounded_sources
        return self._collected_sources

    def _find_source_index(self, url: str) -> int | None:
        """Return the index of a tracked source for a URL, if present."""
        for index, source in enumerate(self._collected_sources):
            if source.url == url:
                return index
        return None
