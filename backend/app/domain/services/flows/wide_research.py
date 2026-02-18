"""Wide Research Flow for parallel multi-source research.

Inspired by Pythinker AI's "Map" capability for dividing tasks into
homogeneous subtasks that execute concurrently and aggregate results.

Features:
- Parallel search across multiple sources (search types)
- Query expansion for comprehensive coverage
- Source cross-validation
- Result aggregation with deduplication
- Synthesis with source citations
- Real-time SSE progress updates
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.models.event import BaseEvent, ToolEvent
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.search import QueryExpander, SearchType

logger = logging.getLogger(__name__)


class AggregationStrategy(str, Enum):
    """Strategy for aggregating results from multiple sources."""

    MERGE = "merge"  # Simple merge with deduplication
    SYNTHESIZE = "synthesize"  # Synthesize into coherent summary
    COMPARE = "compare"  # Side-by-side comparison
    VALIDATE = "validate"  # Cross-validate facts across sources


@dataclass
class WideResearchConfig:
    """Configuration for wide research execution."""

    topic: str
    queries: list[str]
    search_types: list[SearchType] = field(default_factory=lambda: [SearchType.INFO])
    expand_queries: bool = True
    max_variants: int = 3
    max_concurrent: int = 5
    timeout_per_query: int = 30
    aggregation_strategy: AggregationStrategy = AggregationStrategy.SYNTHESIZE
    deep_dive_top_n: int = 3  # Number of top results to deep-dive with browser for visual feedback
    date_range: str | None = None


@dataclass
class ResearchSource:
    """A source discovered during research."""

    url: str
    title: str
    snippet: str
    query: str
    search_type: SearchType
    relevance_score: float = 0.0
    deep_dive_content: str | None = None
    validated: bool = False


@dataclass
class WideResearchResult:
    """Result of wide research execution."""

    research_id: str
    topic: str
    total_queries: int
    completed_queries: int
    sources: list[ResearchSource]
    aggregated_content: str
    citations: list[dict[str, str]]
    synthesis: str | None = None
    cross_validated_facts: list[str] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    errors: list[str] = field(default_factory=list)


class WideResearchFlow:
    """Executes parallel research across multiple sources with aggregation.

    Inspired by Pythinker AI's "Map" capability - dividing research tasks into
    homogeneous subtasks that execute concurrently.

    Usage:
        flow = WideResearchFlow(search_engine, browser)
        result = await flow.execute(config)
    """

    def __init__(
        self,
        search_engine: SearchEngine,
        browser: Browser | None = None,
        session_id: str | None = None,
    ):
        """Initialize the wide research flow.

        Args:
            search_engine: Search engine for executing queries
            browser: Optional browser for deep-dive content extraction
            session_id: Parent session ID for tracking
        """
        self.search_engine = search_engine
        self.browser = browser
        self.session_id = session_id

        # Internal state
        self._research_id: str | None = None
        self._sources: list[ResearchSource] = []
        self._seen_urls: set[str] = set()
        self._event_queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
        self._cancelled = False

    @property
    def research_id(self) -> str | None:
        """Get the current research ID."""
        return self._research_id

    async def execute(
        self,
        config: WideResearchConfig,
    ) -> WideResearchResult:
        """Execute wide research with parallel queries.

        Args:
            config: Research configuration

        Returns:
            Aggregated research result
        """
        self._research_id = str(uuid.uuid4())[:12]
        started_at = datetime.now(UTC)

        logger.info(f"Starting wide research {self._research_id} on topic: {config.topic}")

        # Phase 1: Generate all query variants
        all_queries = self._generate_query_matrix(config)
        total_queries = len(all_queries)

        logger.info(f"Generated {total_queries} queries across {len(config.search_types)} search types")

        # Phase 2: Execute parallel searches
        completed_queries = 0
        errors = []

        try:
            await self._execute_parallel_searches(
                all_queries,
                config.max_concurrent,
                config.timeout_per_query,
                config.date_range,
            )
            completed_queries = total_queries - len(errors)
        except Exception as e:
            logger.error(f"Wide research search phase failed: {e}")
            errors.append(str(e))

        # Phase 3: Optional deep-dive on top results
        if config.deep_dive_top_n > 0 and self.browser:
            await self._deep_dive_top_sources(config.deep_dive_top_n)

        # Phase 4: Aggregate and synthesize
        aggregated_content = self._aggregate_sources(config.aggregation_strategy)
        citations = self._generate_citations()

        # Phase 5: Cross-validation (if strategy is VALIDATE)
        cross_validated = None
        if config.aggregation_strategy == AggregationStrategy.VALIDATE:
            cross_validated = self._cross_validate_facts()

        # Phase 6: Generate synthesis
        synthesis = None
        if config.aggregation_strategy == AggregationStrategy.SYNTHESIZE:
            synthesis = self._generate_synthesis(config.topic)

        completed_at = datetime.now(UTC)

        result = WideResearchResult(
            research_id=self._research_id,
            topic=config.topic,
            total_queries=total_queries,
            completed_queries=completed_queries,
            sources=self._sources,
            aggregated_content=aggregated_content,
            citations=citations,
            synthesis=synthesis,
            cross_validated_facts=cross_validated,
            started_at=started_at,
            completed_at=completed_at,
            errors=errors,
        )

        logger.info(
            f"Wide research {self._research_id} completed: "
            f"{len(self._sources)} unique sources from {completed_queries}/{total_queries} queries"
        )

        return result

    async def execute_streaming(
        self,
        config: WideResearchConfig,
    ) -> AsyncGenerator[BaseEvent | WideResearchResult, None]:
        """Execute wide research with streaming progress events.

        Args:
            config: Research configuration

        Yields:
            Progress events and final result
        """
        self._research_id = str(uuid.uuid4())[:12]
        started_at = datetime.now(UTC)

        # Emit start event
        yield ToolEvent(
            tool_name="wide_research",
            tool_input={"topic": config.topic, "research_id": self._research_id},
            tool_output="Started wide research",
            success=True,
        )

        # Generate query matrix
        all_queries = self._generate_query_matrix(config)
        total_queries = len(all_queries)

        # Execute with progress events
        completed_queries = 0
        errors = []
        semaphore = asyncio.Semaphore(config.max_concurrent)

        async def search_with_event(query: str, search_type: SearchType) -> tuple[bool, str | None]:
            nonlocal completed_queries
            async with semaphore:
                try:
                    result = await asyncio.wait_for(
                        self.search_engine.search(query, config.date_range),
                        timeout=config.timeout_per_query,
                    )
                    if result.success and result.data:
                        self._process_search_results(result.data, query, search_type)
                    completed_queries += 1
                    return True, None
                except Exception as e:
                    completed_queries += 1
                    return False, str(e)

        # Launch all searches
        tasks = [asyncio.create_task(search_with_event(q, st)) for q, st in all_queries]

        # Yield progress events as tasks complete
        for coro in asyncio.as_completed(tasks):
            _success, error = await coro
            if error:
                errors.append(error)

            # Yield progress event
            yield ToolEvent(
                tool_name="wide_research",
                tool_input={"research_id": self._research_id},
                tool_output=f"Progress: {completed_queries}/{total_queries} queries, {len(self._sources)} sources found",
                success=True,
            )

        # Aggregate and synthesize
        aggregated_content = self._aggregate_sources(config.aggregation_strategy)
        citations = self._generate_citations()
        synthesis = (
            self._generate_synthesis(config.topic)
            if config.aggregation_strategy == AggregationStrategy.SYNTHESIZE
            else None
        )

        # Yield final result
        result = WideResearchResult(
            research_id=self._research_id,
            topic=config.topic,
            total_queries=total_queries,
            completed_queries=completed_queries,
            sources=self._sources,
            aggregated_content=aggregated_content,
            citations=citations,
            synthesis=synthesis,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            errors=errors,
        )

        yield result

    def _generate_query_matrix(self, config: WideResearchConfig) -> list[tuple[str, SearchType]]:
        """Generate all query-type combinations.

        Args:
            config: Research configuration

        Returns:
            List of (query, search_type) tuples
        """
        all_queries = []

        for query in config.queries:
            for search_type in config.search_types:
                if config.expand_queries:
                    # Expand each query into variants
                    variants = QueryExpander.expand(query, search_type, config.max_variants)
                    all_queries.extend((variant, search_type) for variant in variants)
                else:
                    all_queries.append((query, search_type))

        return all_queries

    async def _execute_parallel_searches(
        self,
        queries: list[tuple[str, SearchType]],
        max_concurrent: int,
        timeout: int,  # noqa: ASYNC109
        date_range: str | None,
    ) -> None:
        """Execute all searches in parallel.

        Args:
            queries: List of (query, search_type) tuples
            max_concurrent: Maximum concurrent searches
            timeout: Timeout per query
            date_range: Optional date range filter
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def search_one(query: str, search_type: SearchType) -> None:
            async with semaphore:
                if self._cancelled:
                    return

                try:
                    result = await asyncio.wait_for(
                        self.search_engine.search(query, date_range),
                        timeout=timeout,
                    )

                    if result.success and result.data:
                        self._process_search_results(result.data, query, search_type)

                except TimeoutError:
                    logger.warning(f"Query timed out: {query[:50]}...")
                except Exception as e:
                    logger.warning(f"Query failed: {query[:50]}... - {e}")

        # Launch all searches
        tasks = [asyncio.create_task(search_one(q, st)) for q, st in queries]

        await asyncio.gather(*tasks, return_exceptions=True)

    def _process_search_results(
        self,
        results: SearchResults,
        query: str,
        search_type: SearchType,
    ) -> None:
        """Process and deduplicate search results.

        Args:
            results: Search results to process
            query: Original query
            search_type: Type of search
        """
        for item in results.results:
            if item.link not in self._seen_urls:
                self._seen_urls.add(item.link)
                source = ResearchSource(
                    url=item.link,
                    title=item.title,
                    snippet=item.snippet,
                    query=query,
                    search_type=search_type,
                    relevance_score=self._calculate_relevance(item, query),
                )
                self._sources.append(source)

    def _calculate_relevance(self, item: SearchResultItem, query: str) -> float:
        """Calculate relevance score for a search result.

        Args:
            item: Search result item
            query: Original query

        Returns:
            Relevance score (0-1)
        """
        score = 0.0
        query_words = set(query.lower().split())

        # Title match
        title_words = set(item.title.lower().split())
        title_overlap = len(query_words & title_words) / max(len(query_words), 1)
        score += title_overlap * 0.4

        # Snippet match
        snippet_words = set(item.snippet.lower().split())
        snippet_overlap = len(query_words & snippet_words) / max(len(query_words), 1)
        score += snippet_overlap * 0.3

        # URL quality indicators
        if any(domain in item.link.lower() for domain in [".gov", ".edu", ".org", "wikipedia", "docs."]):
            score += 0.2

        # Length bonus (longer snippets often more informative)
        if len(item.snippet) > 200:
            score += 0.1

        return min(score, 1.0)

    async def _deep_dive_top_sources(self, top_n: int) -> None:
        """Deep-dive into top sources using browser.

        Args:
            top_n: Number of top sources to deep-dive
        """
        if not self.browser:
            return

        # Sort by relevance and take top N
        sorted_sources = sorted(self._sources, key=lambda s: s.relevance_score, reverse=True)[:top_n]

        for source in sorted_sources:
            try:
                result = await self.browser.navigate(source.url)
                if result.success and result.data:
                    content = result.data.get("content", "")
                    if content:
                        source.deep_dive_content = content[:10000]  # Limit content
                        logger.debug(f"Deep-dived into: {source.url}")
            except Exception as e:
                logger.warning(f"Deep-dive failed for {source.url}: {e}")

    def _aggregate_sources(self, strategy: AggregationStrategy) -> str:
        """Aggregate sources based on strategy.

        Args:
            strategy: Aggregation strategy to use

        Returns:
            Aggregated content string
        """
        if not self._sources:
            return "No sources found."

        if strategy == AggregationStrategy.MERGE:
            # Simple merge of snippets
            lines = []
            for i, source in enumerate(self._sources[:20], 1):
                lines.append(f"{i}. [{source.title}]({source.url})")
                lines.append(f"   {source.snippet}")
                lines.append("")
            return "\n".join(lines)

        if strategy == AggregationStrategy.COMPARE:
            # Group by search type for comparison
            by_type: dict[SearchType, list[ResearchSource]] = {}
            for source in self._sources:
                if source.search_type not in by_type:
                    by_type[source.search_type] = []
                by_type[source.search_type].append(source)

            lines = []
            for stype, sources in by_type.items():
                lines.append(f"## {stype.value.upper()} Results")
                lines.append("")
                for source in sources[:5]:
                    lines.append(f"- [{source.title}]({source.url})")
                lines.append("")
            return "\n".join(lines)

        if strategy == AggregationStrategy.SYNTHESIZE:
            # Prepare for synthesis
            sorted_sources = sorted(self._sources, key=lambda s: s.relevance_score, reverse=True)[:15]

            lines = [
                "## Key Findings",
                "",
                f"Analyzed {len(self._sources)} sources across multiple search types.",
                "",
                "### Top Sources:",
                "",
            ]

            for source in sorted_sources[:10]:
                lines.append(f"- **{source.title}** ({source.search_type.value})")
                if source.snippet:
                    lines.append(f"  > {source.snippet[:200]}...")
                lines.append("")

            return "\n".join(lines)

        # VALIDATE
        # Group sources by topic for cross-validation
        return self._aggregate_for_validation()

    def _aggregate_for_validation(self) -> str:
        """Aggregate sources for cross-validation.

        Returns:
            Validation-focused aggregation
        """
        lines = [
            "## Cross-Validation Analysis",
            "",
            f"Comparing {len(self._sources)} sources for fact verification.",
            "",
        ]

        # Group by similar topics (simplified)
        sorted_sources = sorted(self._sources, key=lambda s: s.relevance_score, reverse=True)[:20]

        for source in sorted_sources:
            lines.append(f"### {source.title}")
            lines.append(f"Source: {source.url}")
            lines.append(f"Search Type: {source.search_type.value}")
            lines.append("")
            if source.snippet:
                lines.append(f"> {source.snippet}")
            lines.append("")

        return "\n".join(lines)

    def _generate_citations(self) -> list[dict[str, str]]:
        """Generate citation list for all sources.

        Returns:
            List of citation dictionaries
        """
        citations = []
        for i, source in enumerate(self._sources, 1):
            citations.append(
                {
                    "index": str(i),
                    "title": source.title,
                    "url": source.url,
                    "type": source.search_type.value,
                }
            )
        return citations[:50]  # Limit to 50 citations

    def _cross_validate_facts(self) -> list[str]:
        """Cross-validate facts across sources.

        Returns:
            List of validated facts
        """
        # Simplified cross-validation: find common terms across sources
        facts = []

        if len(self._sources) < 2:
            return facts

        # Count term frequency across sources
        term_sources: dict[str, set[str]] = {}

        for source in self._sources[:20]:
            words = set(source.snippet.lower().split())
            # Filter to meaningful terms
            meaningful = {w for w in words if len(w) > 5 and w.isalpha()}
            for term in meaningful:
                if term not in term_sources:
                    term_sources[term] = set()
                term_sources[term].add(source.url)

        # Find terms appearing in multiple sources
        for term, sources in term_sources.items():
            if len(sources) >= 3:  # Appears in 3+ sources
                facts.append(f"'{term}' mentioned across {len(sources)} sources")

        return facts[:20]  # Limit to 20 facts

    def _generate_synthesis(self, topic: str) -> str:
        """Generate a synthesis of all research findings.

        Args:
            topic: Research topic

        Returns:
            Synthesized summary
        """
        if not self._sources:
            return "Insufficient data for synthesis."

        sorted_sources = sorted(self._sources, key=lambda s: s.relevance_score, reverse=True)

        lines = [
            f"# Research Synthesis: {topic}",
            "",
            f"Based on analysis of {len(self._sources)} sources.",
            "",
            "## Key Themes",
            "",
        ]

        # Extract themes from top sources
        top_sources = sorted_sources[:10]
        for i, source in enumerate(top_sources, 1):
            lines.append(f"{i}. **{source.title}**")
            if source.snippet:
                # First sentence of snippet as key point
                first_sentence = source.snippet.split(".")[0] + "."
                lines.append(f"   - {first_sentence}")
            lines.append("")

        lines.extend(
            [
                "## Methodology",
                "",
                f"- Searched across {len({s.search_type for s in self._sources})} search types",
                f"- Processed {len({s.query for s in self._sources})} unique queries",
                f"- Found {len(self._sources)} unique sources",
                "",
                "## Sources",
                "",
            ]
        )

        for i, source in enumerate(sorted_sources[:10], 1):
            lines.append(f"{i}. [{source.title}]({source.url})")

        return "\n".join(lines)

    def cancel(self) -> None:
        """Cancel the research."""
        self._cancelled = True
        logger.info(f"Wide research {self._research_id} cancelled")

    def to_tool_result(self, result: WideResearchResult) -> ToolResult:
        """Convert WideResearchResult to ToolResult.

        Args:
            result: Wide research result

        Returns:
            ToolResult for tool framework compatibility
        """
        return ToolResult(
            success=len(result.errors) == 0,
            message=(
                f"Wide research completed: {len(result.sources)} sources from "
                f"{result.completed_queries}/{result.total_queries} queries"
            ),
            data={
                "research_id": result.research_id,
                "topic": result.topic,
                "sources_count": len(result.sources),
                "synthesis": result.synthesis,
                "aggregated_content": result.aggregated_content,
                "citations": result.citations,
                "errors": result.errors,
            },
        )


async def create_wide_research_tool_handler(
    search_engine: SearchEngine,
    browser: Browser | None = None,
    session_id: str | None = None,
) -> tuple["WideResearchFlow", Any]:
    """Factory function to create wide research flow and its tool definition.

    Args:
        search_engine: Search engine instance
        browser: Optional browser instance
        session_id: Parent session ID

    Returns:
        Tuple of (flow instance, tool definition)
    """
    flow = WideResearchFlow(search_engine, browser, session_id)

    tool_def = {
        "name": "wide_research",
        "description": """Execute comprehensive parallel research across multiple sources.

INSPIRED BY PYTHINKER AI'S "MAP" CAPABILITY:
Divides research into homogeneous subtasks executed concurrently,
then aggregates and synthesizes results.

FEATURES:
- Parallel search across multiple search types (info, news, academic, etc.)
- Query expansion for comprehensive coverage
- Result deduplication and relevance scoring
- Cross-source validation
- Automatic synthesis with source citations

USE WHEN:
- Researching a topic thoroughly from multiple angles
- Comparing information across different source types
- Validating claims with multiple sources
- Generating comprehensive research reports""",
        "parameters": {
            "topic": {
                "type": "string",
                "description": "Research topic or question",
            },
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific search queries",
            },
            "search_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["info", "news", "academic", "api", "data", "tool"],
                },
                "description": "Types of sources to search",
            },
            "aggregation_strategy": {
                "type": "string",
                "enum": ["merge", "synthesize", "compare", "validate"],
                "description": "How to aggregate results",
            },
        },
        "required": ["topic", "queries"],
    }

    return flow, tool_def
