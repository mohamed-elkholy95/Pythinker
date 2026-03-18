"""Report generation service with structured output validation."""

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.domain.exceptions.base import ConfigurationException, LLMException
from app.domain.external.llm import LLM
from app.domain.models.report import (
    AnalysisReport,
    CitationEntry,
    ComparisonReport,
    Report,
    ReportMetadata,
    ResearchReport,
    StructuredReportOutput,
)
from app.domain.models.source_attribution import AttributionSummary

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates structured reports with validation and retry."""

    MAX_RETRIES = 3

    def __init__(self, llm: LLM):
        self.llm = llm

    async def generate(
        self,
        research_data: dict[str, Any],
        report_type: str,
        citations: list[CitationEntry],
        attribution_summary: AttributionSummary,
    ) -> StructuredReportOutput:
        """Generate a validated structured report.

        Args:
            research_data: Compiled research data
            report_type: Type of report to generate
            citations: Available citations
            attribution_summary: Source attribution summary

        Returns:
            Validated StructuredReportOutput
        """
        start_time = datetime.now(UTC)

        # Get the appropriate model class
        model_class = self._get_model_class(report_type)

        # Build messages with schema
        messages = self._build_messages(research_data, report_type, citations)

        # Attempt generation with retries
        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                # Use structured output for type-safe generation
                policy_method = getattr(self.llm, "ask_structured_with_policy", None)
                if callable(policy_method):
                    report = await policy_method(
                        messages=messages,
                        response_model=model_class,
                        tier="A",
                    )
                else:
                    report = await self.llm.ask_structured(
                        messages=messages,
                        response_model=model_class,
                    )

                # Build metadata
                metadata = ReportMetadata(
                    total_sources_consulted=attribution_summary.total_claims,
                    sources_used=attribution_summary.verified_claims,
                    sources_filtered=attribution_summary.unavailable_claims,
                    average_source_quality=attribution_summary.average_confidence,
                    generation_time_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                    token_usage=0,  # Token tracking handled elsewhere
                )

                # Calculate quality score
                quality_score = self._calculate_quality_score(report, citations)

                return StructuredReportOutput(
                    report=report,
                    metadata=metadata,
                    citation_bibliography=citations,
                    quality_score=quality_score,
                    warnings=self._generate_warnings(report, attribution_summary),
                )

            except ValidationError as e:
                last_error = e
                logger.warning(f"Report validation failed (attempt {attempt + 1}): {e}")
                # Add error context to messages for retry
                messages = self._add_retry_context(messages, str(e))
            except Exception as e:
                last_error = e
                logger.warning(f"Report generation failed (attempt {attempt + 1}): {e}")

        raise LLMException(f"Failed to generate valid report after {self.MAX_RETRIES} attempts: {last_error}")

    def _get_model_class(
        self, report_type: str
    ) -> type[ResearchReport] | type[ComparisonReport] | type[AnalysisReport]:
        """Get the appropriate model class for report type."""
        type_map: dict[str, type[ResearchReport] | type[ComparisonReport] | type[AnalysisReport]] = {
            "research": ResearchReport,
            "comparison": ComparisonReport,
            "analysis": AnalysisReport,
        }

        model_class = type_map.get(report_type)
        if not model_class:
            raise ConfigurationException(f"Unknown report type: {report_type}")

        return model_class

    def _calculate_quality_score(self, report: Report, citations: list[CitationEntry]) -> float:
        """Calculate overall report quality score."""
        scores = []

        # Citation coverage
        if hasattr(report, "key_findings"):
            cited_findings = sum(1 for f in report.key_findings if f.citation_ids)
            scores.append(cited_findings / len(report.key_findings) if report.key_findings else 0)

        if hasattr(report, "findings"):
            cited_findings = sum(1 for f in report.findings if f.citation_ids)
            scores.append(cited_findings / len(report.findings) if report.findings else 0)

        # Section completeness
        if hasattr(report, "sections"):
            scores.append(min(len(report.sections) / 3, 1.0))  # Target 3+ sections

        # Source reliability
        if citations:
            avg_reliability = sum(c.reliability_score for c in citations) / len(citations)
            scores.append(avg_reliability)

        return sum(scores) / len(scores) if scores else 0.5

    def _generate_warnings(self, report: Report, attribution: AttributionSummary) -> list[str]:
        """Generate warnings about report quality."""
        warnings = []

        if attribution.has_paywall_sources:
            warnings.append("Some sources were behind paywalls - information may be incomplete")

        if attribution.inferred_claims > attribution.verified_claims:
            warnings.append("Report contains more inferred than verified claims")

        if attribution.average_confidence < 0.6:
            warnings.append("Overall source confidence is low - verify key claims independently")

        return warnings

    def _build_messages(
        self, data: dict[str, Any], report_type: str, citations: list[CitationEntry]
    ) -> list[dict[str, str]]:
        """Build generation messages with schema instructions."""
        # Format citations for context
        citation_context = "\n".join(f"[{c.id}] {c.title} - {c.url}" for c in citations)

        # Format research data
        research_context = self._format_research_data(data)

        system_prompt = f"""You are an expert research analyst generating structured reports.
Generate a {report_type} report based on the provided research data.

IMPORTANT:
1. Every factual claim MUST reference one of the provided citation IDs
2. Do NOT make up citations - only use the ones provided
3. Be specific and detailed in findings
4. Include confidence scores reflecting source reliability
5. Note any limitations or caveats

Available Citations:
{citation_context or "No citations available - note this limitation"}
"""

        user_prompt = f"""Generate a comprehensive {report_type} report based on this research:

{research_context}

Requirements:
- Title must clearly describe the report topic
- Executive summary should be 2-3 paragraphs minimum
- Each key finding must have supporting evidence and citations
- Sections should cover distinct aspects of the research
- Note any limitations or areas requiring further research"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _format_research_data(self, data: dict[str, Any]) -> str:
        """Format research data for the prompt."""
        parts = []

        if "query" in data:
            parts.append(f"Research Query: {data['query']}")

        if "sources" in data:
            parts.append("\nSources Analyzed:")
            for i, source in enumerate(data["sources"][:10], 1):
                url = source.get("url", "Unknown URL")
                title = source.get("title", "Untitled")
                content = source.get("content", "")[:500]
                parts.append(f"\n{i}. {title}\n   URL: {url}\n   Content: {content}...")

        if data.get("benchmarks"):
            parts.append("\nExtracted Benchmarks:")
            parts.extend(f"- {b.name}: {b.value} (Source: {b.source_url})" for b in data["benchmarks"][:10])

        if data.get("comparisons"):
            parts.append("\nComparisons:")
            parts.extend(f"- {c.benchmark_name}: {len(c.entries)} entries compared" for c in data["comparisons"][:5])

        return "\n".join(parts)

    def _add_retry_context(self, messages: list[dict[str, str]], error: str) -> list[dict[str, str]]:
        """Add retry context with validation feedback."""
        messages = messages.copy()
        messages.append(
            {
                "role": "assistant",
                "content": "[Previous attempt failed validation]",
            }
        )
        messages.append(
            {
                "role": "user",
                "content": f"""The previous response failed validation with this error:
{error}

Please fix the issues and try again. Ensure:
1. All required fields are present
2. All strings meet minimum length requirements
3. All citation IDs reference provided citations
4. Confidence scores are between 0.0 and 1.0""",
            }
        )
        return messages
