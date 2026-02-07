"""Enhanced research flow integrating all four improvements."""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.models.benchmark import BenchmarkExtractionResult
from app.domain.models.citation_discipline import CitationConfig, CitationValidationResult
from app.domain.models.event import ThoughtEvent, ThoughtStatus
from app.domain.models.report import CitationEntry, StructuredReportOutput
from app.domain.models.source_attribution import AttributionSummary
from app.domain.models.source_quality import FilteredSourceResult, SourceFilterConfig
from app.domain.services.benchmark_extractor import BenchmarkExtractor
from app.domain.services.citation_validator import CitationValidator
from app.domain.services.report_generator import ReportGenerator
from app.domain.services.source_filter import SourceFilterService

logger = logging.getLogger(__name__)


class EnhancedResearchFlow:
    """Research flow with structured reporting, source filtering,
    benchmark extraction, and citation discipline."""

    def __init__(
        self,
        llm: LLM,
        search_engine: SearchEngine,
        source_filter_config: SourceFilterConfig | None = None,
        citation_config: CitationConfig | None = None,
    ):
        self.llm = llm
        self.search_engine = search_engine

        # Initialize services
        self.source_filter = SourceFilterService(source_filter_config)
        self.benchmark_extractor = BenchmarkExtractor(llm)
        self.citation_validator = CitationValidator(llm, citation_config)
        self.report_generator = ReportGenerator(llm)

    async def research(
        self,
        query: str,
        report_type: str = "research",
        max_sources: int = 10,
        emit_events: bool = True,
    ) -> AsyncGenerator[ThoughtEvent | StructuredReportOutput, None]:
        """Execute enhanced research flow.

        Args:
            query: Research query
            report_type: Type of report to generate (research, comparison, analysis)
            max_sources: Maximum sources to use
            emit_events: Whether to emit progress events

        Yields:
            Progress events and final StructuredReportOutput
        """
        start_time = datetime.utcnow()

        # Step 1: Search and gather sources
        if emit_events:
            yield self._create_event("Searching for sources...", "search_started")

        logger.info(f"Searching for: {query}")
        raw_sources = await self._search(query)

        if emit_events:
            yield self._create_event(f"Found {len(raw_sources)} potential sources", "search_completed")

        # Step 2: Filter sources by quality
        if emit_events:
            yield self._create_event("Filtering sources by quality...", "filter_started")

        logger.info(f"Filtering {len(raw_sources)} sources")
        filter_result = self.source_filter.filter_sources(raw_sources, query)

        sources = filter_result.accepted_sources[:max_sources]
        logger.info(f"Using {len(sources)} sources after filtering")

        if emit_events:
            yield self._create_event(
                f"Selected {len(sources)} high-quality sources (filtered {len(filter_result.rejected_sources)})",
                "filter_completed",
            )

        if not sources:
            raise ValueError("No sources passed quality filtering. Try broadening your query.")

        # Step 3: Extract benchmarks
        if emit_events:
            yield self._create_event("Extracting benchmarks and metrics...", "benchmark_started")

        logger.info("Extracting benchmarks")
        source_data = [
            {"url": s.url, "content": self._get_content(s.url, raw_sources), "title": self._get_title(s.url, raw_sources)}
            for s in sources
        ]
        benchmark_result = await self.benchmark_extractor.extract(source_data)

        if emit_events:
            yield self._create_event(
                f"Extracted {benchmark_result.benchmarks_found} benchmarks from {benchmark_result.sources_analyzed} sources",
                "benchmark_completed",
            )

        # Step 4: Build citations
        citations = self._build_citations(sources, raw_sources)
        source_scores = {s.url: s for s in sources}

        # Step 5: Generate report
        if emit_events:
            yield self._create_event("Generating structured report...", "report_started")

        logger.info("Generating structured report")
        research_data = {
            "query": query,
            "sources": source_data,
            "benchmarks": benchmark_result.benchmarks,
            "comparisons": benchmark_result.comparisons,
        }

        attribution = AttributionSummary(
            total_claims=len(sources),
            verified_claims=len([s for s in sources if s.reliability_score > 0.7]),
            average_confidence=sum(s.composite_score for s in sources) / len(sources) if sources else 0,
        )

        report_output = await self.report_generator.generate(
            research_data=research_data,
            report_type=report_type,
            citations=list(citations.values()),
            attribution_summary=attribution,
        )

        # Step 6: Validate citations in report
        if emit_events:
            yield self._create_event("Validating citations...", "validation_started")

        logger.info("Validating citations")
        report_content = self._extract_report_content(report_output.report)
        citation_validation = await self.citation_validator.validate(
            content=report_content,
            available_citations={c.id: {"url": c.url, "title": c.title, "excerpt": c.excerpt} for c in report_output.citation_bibliography},
            source_scores=source_scores,
        )

        # Add citation warnings
        if not citation_validation.is_valid:
            report_output.warnings.extend(
                [
                    f"Citation coverage: {citation_validation.citation_coverage:.1%}",
                    f"Uncited factual claims: {citation_validation.uncited_factual_claims}",
                ]
            )

        # Calculate generation time
        generation_time = (datetime.utcnow() - start_time).total_seconds()
        report_output.metadata.generation_time_seconds = generation_time

        if emit_events:
            yield self._create_event(
                f"Report generated in {generation_time:.1f}s with {len(citations)} citations",
                "report_completed",
            )

        # Final output
        yield report_output

    async def research_single(
        self,
        query: str,
        report_type: str = "research",
        max_sources: int = 10,
    ) -> StructuredReportOutput:
        """Execute research and return only the final report.

        Args:
            query: Research query
            report_type: Type of report to generate
            max_sources: Maximum sources to use

        Returns:
            StructuredReportOutput
        """
        result: StructuredReportOutput | None = None

        async for item in self.research(query, report_type, max_sources, emit_events=False):
            if isinstance(item, StructuredReportOutput):
                result = item

        if result is None:
            raise ValueError("Research flow completed without producing a report")

        return result

    def get_filter_result(self, sources: list[dict], query: str) -> FilteredSourceResult:
        """Get source filtering result without full research.

        Useful for previewing which sources would be used.
        """
        return self.source_filter.filter_sources(sources, query)

    async def extract_benchmarks(self, sources: list[dict]) -> BenchmarkExtractionResult:
        """Extract benchmarks from sources without full research.

        Useful for benchmark-focused queries.
        """
        return await self.benchmark_extractor.extract(sources)

    async def validate_citations(
        self,
        content: str,
        citations: dict[str, dict[str, Any]],
    ) -> CitationValidationResult:
        """Validate citations in content without full research.

        Useful for post-hoc validation.
        """
        return await self.citation_validator.validate(content, citations)

    async def _search(self, query: str) -> list[dict[str, Any]]:
        """Execute search and return raw results."""
        result = await self.search_engine.search(query)

        if not result.success or not result.data:
            logger.warning(f"Search failed or returned no results for: {query}")
            return []

        return [
            {
                "url": r.link,
                "title": r.title,
                "content": r.snippet or "",
                "snippet": r.snippet,
            }
            for r in result.data.results
        ]

    def _get_content(self, url: str, sources: list[dict]) -> str:
        """Get content for a URL from raw sources."""
        for s in sources:
            if s.get("url") == url:
                return s.get("content", "")
        return ""

    def _get_title(self, url: str, sources: list[dict]) -> str:
        """Get title for a URL from raw sources."""
        for s in sources:
            if s.get("url") == url:
                return s.get("title", "")
        return ""

    def _build_citations(
        self,
        filtered_sources: list,
        raw_sources: list[dict],
    ) -> dict[str, CitationEntry]:
        """Build citation entries from filtered sources."""
        citations: dict[str, CitationEntry] = {}

        for i, source in enumerate(filtered_sources):
            cid = f"[{i + 1}]"
            raw = next((s for s in raw_sources if s.get("url") == source.url), {})

            citations[cid] = CitationEntry(
                id=cid,
                url=source.url,
                title=raw.get("title", "Unknown"),
                accessed_at=datetime.utcnow(),
                source_type="web",
                reliability_score=source.reliability_score,
                excerpt=raw.get("snippet"),
            )

        return citations

    def _extract_report_content(self, report: Any) -> str:
        """Extract text content from report for validation."""
        parts: list[str] = []

        if hasattr(report, "executive_summary"):
            parts.append(report.executive_summary)

        if hasattr(report, "sections"):
            for section in report.sections:
                parts.append(section.content)

        if hasattr(report, "key_findings"):
            for finding in report.key_findings:
                parts.append(finding.finding)

        if hasattr(report, "findings"):
            for finding in report.findings:
                parts.append(finding.finding)

        if hasattr(report, "recommendation") and report.recommendation:
            parts.append(report.recommendation)

        return "\n\n".join(parts)

    def _create_event(self, message: str, step: str) -> ThoughtEvent:
        """Create a progress event."""
        return ThoughtEvent(
            status=ThoughtStatus.THINKING,
            thought_type=step,
            content=message,
        )
