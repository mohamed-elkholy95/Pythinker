"""Response generation helpers for the ExecutionAgent summarization pipeline.

Encapsulates content cleaning, quality gates, stream coalescing, delivery
integrity checks, follow-up suggestion generation, and all supporting
utility methods that were previously embedded in ExecutionAgent.

Usage:
    rg = ResponseGenerator(
        llm=llm,
        memory=memory,
        source_tracker=source_tracker,
        metrics=metrics,
    )
    cleaned = rg.clean_report_content(raw)
    title = rg.extract_title(cleaned)
    suggestions = await rg.generate_follow_up_suggestions(title, cleaned)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.event import StreamEvent
from app.domain.services.agents.compliance_gates import GateStatus, get_compliance_gates
from app.domain.services.agents.response_policy import ResponsePolicy, VerbosityMode

if TYPE_CHECKING:
    from app.domain.services.agents.source_tracker import SourceTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models for suggestion parsing
# ---------------------------------------------------------------------------

_SUGGESTION_LIST_ADAPTER = TypeAdapter(list[str])


class _SuggestionPayload(BaseModel):
    suggestions: list[str]


# ---------------------------------------------------------------------------
# Pre-compiled regex patterns (moved from class-level on ExecutionAgent)
# ---------------------------------------------------------------------------

_TOOL_CALL_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)
_FUNCTION_CALL_RE = re.compile(r"<function_call>.*?</function_call>", re.DOTALL)

_PREAMBLE_RE = re.compile(r"\A([^#]*?)(?=^#\s)", re.MULTILINE | re.DOTALL)
_BOILERPLATE_FINAL_RESULT_RE = re.compile(
    r"##\s*Final Result\s*\n+"
    r"(?:The requested work has been completed[^\n]*\n*)+",
)
_BOILERPLATE_ARTIFACT_REFS_RE = re.compile(
    r"##\s*Artifact References?\s*\n+"
    r"(?:-\s*No (?:file )?artifacts? (?:were |was )[^\n]*\n*)+",
)
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_REPORT_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_VERIFICATION_TAG_RE = re.compile(r"\[(?:unverified|verified|not verified)[^\]]*\]?", re.IGNORECASE)

_JSON_CODEBLOCK_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\s*\n?```$", re.DOTALL)

_META_COMMENTARY_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"I(?:'ve| have) (?:created|produced|written|prepared|compiled|generated|delivered|completed)"
    r"|I(?:'ll| will| am going to|'m going to) (?:create|write|prepare|compile|generate|produce|deliver)"
    r"|Let me (?:create|write|prepare|compile|generate|produce)"
    r"|(?:The|A) (?:comprehensive|detailed|complete|full|final) (?:research )?report (?:has been|was|is)"
    r"|(?:Here is|Below is) (?:a |the )?(?:summary|overview) of (?:what|the)"
    r"|The report (?:covers|includes|contains|addresses)"
    r"|Task requires .+?(?:but|however)"
    r"|(?:exceeds|exceeded) (?:the )?(?:available )?(?:token|context) (?:budget|limit|window)"
    r"|(?:additional|more) context processing (?:that )?(?:exceeds|is required|is needed)"
    r"|(?:token|context) (?:budget|limit|window) (?:has been |is )?(?:exceeded|exhausted|insufficient)"
    r"|Research findings have been gathered but"
    r"|findings (?:have been |were )?(?:gathered|collected|compiled) but"
    r"|(?:I am |I'm )?(?:unable|cannot|can't|couldn't) (?:to )?(?:generate|compile|produce|complete|write|create)"
    r" (?:the |a )?(?:full |complete |comprehensive )?(?:report|response|document)"
    r"|report (?:compilation|generation|creation) requires"
    r"|based on the (?:research |parallel )?(?:findings|search findings)"
    r"|citing only the sources provided"
    r")",
    re.IGNORECASE,
)

_EXCUSE_KEYWORDS = frozenset(
    {
        "token budget",
        "token limit",
        "context budget",
        "context limit",
        "context window",
        "exceeds available",
        "insufficient context",
        "unable to generate",
        "unable to compile",
        "cannot generate",
        "cannot compile",
        "additional context processing",
    }
)


class ResponseGenerator:
    """Response-generation helpers extracted from ExecutionAgent.

    Responsibilities:
    - Content cleaning (tool-call XML, boilerplate, preamble, JSON echo)
    - Quality gates (meta-commentary, low-quality, report structure)
    - Stream coalescing for smooth frontend rendering
    - Continuation merging and duplicate collapse
    - Delivery integrity gate (truncation, coverage, completeness)
    - Follow-up suggestion generation
    - Title extraction, metric recording, fallback recovery

    All methods were previously private on ExecutionAgent and are called
    exclusively from ``summarize()``.
    """

    __slots__ = (
        "_coalesce_flush_seconds",
        "_coalesce_max_chars",
        "_llm",
        "_memory",
        "_metrics",
        "_pre_trim_report_cache",
        "_resolve_feature_flags_fn",
        "_source_tracker",
        "_user_request",
    )

    def __init__(
        self,
        *,
        llm: Any,
        memory: Any,
        source_tracker: SourceTracker,
        metrics: MetricsPort | None = None,
        resolve_feature_flags_fn: Any = None,
        coalesce_max_chars: int = 320,
        coalesce_flush_seconds: float = 0.05,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._source_tracker = source_tracker
        self._metrics: MetricsPort = metrics or get_null_metrics()
        self._resolve_feature_flags_fn = resolve_feature_flags_fn
        self._coalesce_max_chars = coalesce_max_chars
        self._coalesce_flush_seconds = coalesce_flush_seconds

        # Mutable state (set per-run by the caller)
        self._pre_trim_report_cache: str | None = None
        self._user_request: str | None = None

    # ── State Setters ──────────────────────────────────────────────────

    def set_pre_trim_report_cache(self, content: str | None) -> None:
        self._pre_trim_report_cache = content

    def set_user_request(self, request: str | None) -> None:
        self._user_request = request

    # ── Stream Helpers ─────────────────────────────────────────────────

    def get_last_stream_metadata(self) -> dict[str, Any]:
        """Safely read stream metadata from the LLM adapter."""
        metadata = getattr(self._llm, "last_stream_metadata", None)
        if isinstance(metadata, dict):
            return metadata
        return {}

    async def iter_coalesced_stream_events(
        self,
        stream_iter: AsyncGenerator[str, None],
        *,
        phase: str = "summarizing",
    ) -> AsyncGenerator[StreamEvent, None]:
        """Coalesce small LLM chunks into smoother StreamEvent payloads."""
        max_chars = max(1, int(self._coalesce_max_chars))
        flush_seconds = max(0.0, float(self._coalesce_flush_seconds))
        loop = asyncio.get_running_loop()

        buffered_chunks: list[str] = []
        buffered_chars = 0
        last_flush_at = loop.time()

        async with aclosing(stream_iter) as stream:
            async for raw_chunk in stream:
                chunk = raw_chunk or ""
                if not chunk:
                    continue

                buffered_chunks.append(chunk)
                buffered_chars += len(chunk)

                now = loop.time()
                should_flush = buffered_chars >= max_chars
                if not should_flush and flush_seconds > 0:
                    should_flush = (now - last_flush_at) >= flush_seconds
                if not should_flush and chunk.endswith("\n"):
                    should_flush = True

                if not should_flush:
                    continue

                coalesced_chunk = "".join(buffered_chunks)
                buffered_chunks.clear()
                buffered_chars = 0
                last_flush_at = now
                yield StreamEvent(content=coalesced_chunk, is_final=False, phase=phase)

            if buffered_chunks:
                yield StreamEvent(content="".join(buffered_chunks), is_final=False, phase=phase)

    # ── Continuation / Merging ─────────────────────────────────────────

    def build_continuation_prompt(
        self,
        accumulated_text: str = "",
        source_list: str = "",
    ) -> str:
        """Prompt used when stream truncation is detected.

        When the accumulated text has an incomplete References section and sources
        are available, appends the authoritative numbered source list so the LLM
        can complete the section deterministically.
        """
        base_prompt = (
            "Your previous response was truncated by token limits. Continue exactly where you stopped, "
            "without repeating prior sections. Complete any unfinished heading, list, or code block."
        )

        if not accumulated_text or not source_list:
            return base_prompt

        # Detect if the References section is incomplete or missing
        has_ref_heading = bool(re.search(r"^##\s+References?\s*$", accumulated_text, re.MULTILINE | re.IGNORECASE))
        has_inline_citations = bool(re.search(r"\[\d+\]", accumulated_text))

        needs_references = False
        if has_ref_heading:
            # References heading exists — check if section is incomplete
            ref_match = re.search(r"^##\s+References?\s*$", accumulated_text, re.MULTILINE | re.IGNORECASE)
            if ref_match:
                ref_section = accumulated_text[ref_match.end() :].strip()
                ref_entry_count = len(re.findall(r"^\s*\[?\d+\]", ref_section, re.MULTILINE))
                source_line_count = source_list.count("\n") + 1
                if ref_entry_count < source_line_count:
                    needs_references = True
        elif has_inline_citations:
            # Inline citations exist but no References heading at all
            needs_references = True

        if needs_references:
            return (
                f"{base_prompt}\n\n"
                "IMPORTANT: The ## References section is incomplete or missing. "
                "You MUST write the complete ## References section using EXACTLY these sources:\n\n"
                f"{source_list}"
            )

        return base_prompt

    def merge_stream_continuation(self, base_text: str, continuation_text: str) -> str:
        """Merge continuation output while avoiding duplicated overlap."""
        base = base_text or ""
        continuation = continuation_text or ""

        if not continuation.strip():
            return base
        if not base.strip():
            return continuation
        if continuation in base:
            return base
        if base in continuation and len(continuation) >= int(len(base) * 0.8):
            return continuation

        base_tail = base[-4000:]
        continuation_head = continuation[:4000]
        max_overlap = min(len(base_tail), len(continuation_head), 1200)
        min_overlap = 80

        for overlap_size in range(max_overlap, min_overlap - 1, -1):
            if base_tail[-overlap_size:] == continuation_head[:overlap_size]:
                merged = base + continuation[overlap_size:]
                return self._repair_markdown_structure(merged)

        if base.endswith("\n") or continuation.startswith("\n"):
            merged = base + continuation
        else:
            merged = base + "\n" + continuation
        return self._repair_markdown_structure(merged)

    @staticmethod
    def _repair_markdown_structure(text: str) -> str:
        """Repair common markdown structural issues after continuation stitching.

        Fixes:
        - Unclosed code fences (odd count of ``` markers)
        - Duplicate headings at the merge seam
        - Orphaned list items without preceding content
        """
        if not text:
            return text

        # 1. Close unclosed code fences
        fence_count = len(re.findall(r"^```", text, re.MULTILINE))
        if fence_count % 2 != 0:
            text = text.rstrip() + "\n```\n"

        # 2. Remove duplicate adjacent headings (same level + same text)
        text = re.sub(
            r"(^#{1,6}\s+.+$)\n+\1",
            r"\1",
            text,
            flags=re.MULTILINE,
        )

        # 3. Clean up triple+ blank lines (stitch artifact)
        return re.sub(r"\n{4,}", "\n\n\n", text)

    # ── Duplicate Collapse ─────────────────────────────────────────────

    def collapse_duplicate_report_payload(self, content: str) -> str:
        """Collapse duplicate full-report payloads caused by continuation retries."""
        normalized = (content or "").strip()
        if len(normalized) < 300:
            return normalized

        heading_matches = list(_REPORT_H1_RE.finditer(normalized))
        if len(heading_matches) < 2:
            return normalized

        first_heading = heading_matches[0]
        first_title = first_heading.group(1).strip().lower()

        duplicate_heading = None
        for heading in heading_matches[1:]:
            if heading.group(1).strip().lower() == first_title:
                duplicate_heading = heading
                break

        if duplicate_heading is None:
            return normalized

        first_index = first_heading.start()
        duplicate_index = duplicate_heading.start()
        if duplicate_index <= first_index:
            return normalized

        first_block = normalized[first_index:duplicate_index].strip()
        second_block = normalized[duplicate_index:].strip()
        if len(second_block) < 200:
            return normalized

        first_score = self._report_quality_score(first_block)
        second_score = self._report_quality_score(second_block)
        chosen_block = second_block if (second_score < first_score) else first_block
        if second_score == first_score and len(second_block) >= len(first_block):
            chosen_block = second_block

        prefix = normalized[:first_index].strip()
        if prefix:
            return f"{prefix}\n\n{chosen_block}".strip()
        return chosen_block

    def _report_quality_score(self, report_block: str) -> int:
        """Score report quality; lower score is better."""
        if not report_block:
            return 10_000

        marker_count = len(_VERIFICATION_TAG_RE.findall(report_block))
        dangling_brackets = abs(report_block.count("[") - report_block.count("]"))
        short_penalty = 1 if len(report_block) < 500 else 0
        return marker_count * 5 + dangling_brackets + short_penalty

    # ── Delivery Integrity Gate ────────────────────────────────────────

    def run_delivery_integrity_gate(
        self,
        content: str,
        response_policy: ResponsePolicy,
        coverage_result: Any,
        stream_metadata: dict[str, Any],
        truncation_exhausted: bool,
    ) -> tuple[bool, list[str]]:
        """Fail-closed delivery gate for truncation/completeness risks."""
        flags = self._resolve_feature_flags_fn() if self._resolve_feature_flags_fn else {}
        if not flags.get("delivery_integrity_gate", False):
            return True, []

        strict_mode = self.is_integrity_strict_mode(content, response_policy)
        issues: list[str] = []
        warnings: list[str] = []

        finish_reason = str(stream_metadata.get("finish_reason") or "")
        is_stream_truncated = bool(stream_metadata.get("truncated")) or finish_reason == "length"
        if truncation_exhausted:
            issues.append("stream_truncation_unresolved")
        elif is_stream_truncated:
            warnings.append("stream_truncation_detected")

        completeness_result = get_compliance_gates().check_content_completeness(content)
        if completeness_result.status == GateStatus.WARNING:
            warnings.append("content_completeness_warning")

        if not getattr(coverage_result, "is_valid", True):
            missing = getattr(coverage_result, "missing_requirements", [])
            if missing:
                non_blocking = {"next step"}
                blocking_missing = [r for r in missing if r.lower() not in non_blocking]
                warning_only = [r for r in missing if r.lower() in non_blocking]

                if warning_only:
                    warnings.append(f"coverage_missing:{', '.join(warning_only)}")

                if blocking_missing:
                    missing_text = ", ".join(blocking_missing)
                    if strict_mode and is_stream_truncated:
                        issues.append(f"coverage_missing:{missing_text}")
                    else:
                        warnings.append(f"coverage_missing:{missing_text}")
            else:
                warnings.append("coverage_relevance_low")

        if warnings:
            logger.warning("Delivery integrity warnings: %s", "; ".join(warnings))

        self._record_delivery_integrity_gate_metrics(
            stream_metadata=stream_metadata,
            strict_mode=strict_mode,
            warnings=warnings,
            issues=issues,
        )

        if issues:
            logger.warning(
                "Delivery integrity gate blocked output (strict_mode=%s): %s",
                strict_mode,
                "; ".join(issues),
            )
            return False, issues

        return True, []

    def is_integrity_strict_mode(self, content: str, response_policy: ResponsePolicy) -> bool:
        """Enable strict integrity checks for report/evidence-heavy outputs."""
        return (
            response_policy.mode == VerbosityMode.DETAILED
            or "artifact references" in response_policy.min_required_sections
            or self.is_report_structure(content)
        )

    def can_auto_repair_delivery_integrity(self, issues: list[str], content: str = "") -> bool:
        """Allow safe remediation for coverage-only misses with deterministic fallbacks.

        For stream_truncation_unresolved: if the gathered content is substantial (>=500 chars)
        we prefer delivering it with a truncation notice over silently discarding the work.
        """
        if not issues:
            return False
        if any(issue == "stream_truncation_unresolved" for issue in issues):
            # Degrade gracefully — deliver partial content with a disclaimer rather than
            # discarding potentially thousands of chars of completed research.
            return len(content.strip()) >= 500

        actionable_issues = [i for i in issues if i != "content_completeness_warning"]
        if not actionable_issues:
            return True

        if not all(issue.startswith("coverage_missing:") for issue in actionable_issues):
            return False

        reparable_requirements = {"final result", "artifact references", "key caveat", "next step"}
        missing = self._extract_missing_coverage_requirements(actionable_issues)
        return bool(missing) and missing.issubset(reparable_requirements)

    def _extract_missing_coverage_requirements(self, issues: list[str]) -> set[str]:
        """Extract normalized missing requirement labels from gate issues."""
        missing: set[str] = set()
        for issue in issues:
            if not issue.startswith("coverage_missing:"):
                continue
            raw_requirements = issue.split(":", 1)[1]
            for item in raw_requirements.split(","):
                normalized = item.strip().lower()
                if normalized:
                    missing.add(normalized)
        return missing

    def append_delivery_integrity_fallback(self, content: str, issues: list[str]) -> str:
        """Append deterministic fallback sections for reparable coverage misses."""
        missing = self._extract_missing_coverage_requirements(issues)
        sections: list[str] = []

        if any(issue == "stream_truncation_unresolved" for issue in issues):
            sections.append(
                "> **Note:** The model's output was cut off before completion. "
                "The content above represents all successfully gathered information. "
                "You may ask a follow-up question to continue from where this left off."
            )

        if "final result" in missing:
            sections.append("## Final Result\nThe requested work has been completed as summarized above.")
        if "artifact references" in missing:
            sections.append("## Artifact References\n- No file artifacts were created or referenced in this response.")
        if "key caveat" in missing:
            sections.append("## Key Caveat\n- Validate the output with targeted checks before relying on it.")
        if "next step" in missing:
            sections.append(
                "## Next Step\n1. Execute the highest-priority remaining action, then verify the outcome with "
                "targeted checks."
            )

        if not sections:
            return content
        return f"{content}\n\n" + "\n\n".join(sections) + "\n"

    # ── Metrics ────────────────────────────────────────────────────────

    def _record_delivery_integrity_gate_metrics(
        self,
        stream_metadata: dict[str, Any],
        strict_mode: bool,
        warnings: list[str],
        issues: list[str],
    ) -> None:
        """Record delivery-integrity gate outcomes with low-cardinality labels."""
        provider = self._normalize_metric_label(
            str(stream_metadata.get("provider") or getattr(self._llm, "provider", "unknown")),
            fallback="unknown",
        )
        strict_label = "true" if strict_mode else "false"
        result = "blocked" if issues else "passed"

        self._metrics.record_counter(
            "delivery_integrity_gate_result_total",
            labels={"provider": provider, "result": result, "strict_mode": strict_label},
        )
        for warning in warnings:
            self._metrics.record_counter(
                "delivery_integrity_gate_warning_total",
                labels={
                    "provider": provider,
                    "reason": self._normalize_integrity_reason(warning),
                    "strict_mode": strict_label,
                },
            )
        for issue in issues:
            self._metrics.record_counter(
                "delivery_integrity_gate_block_reason_total",
                labels={
                    "provider": provider,
                    "reason": self._normalize_integrity_reason(issue),
                    "strict_mode": strict_label,
                },
            )

    def record_stream_truncation_metric(self, stream_metadata: dict[str, Any], outcome: str) -> None:
        """Record stream truncation lifecycle events for tuning retries."""
        provider = self._normalize_metric_label(
            str(stream_metadata.get("provider") or getattr(self._llm, "provider", "unknown")),
            fallback="unknown",
        )
        finish_reason = self._normalize_metric_label(str(stream_metadata.get("finish_reason") or "unknown"))
        self._metrics.record_counter(
            "delivery_integrity_stream_truncation_total",
            labels={"provider": provider, "finish_reason": finish_reason, "outcome": outcome},
        )

    def _normalize_integrity_reason(self, reason: str) -> str:
        """Normalize a gate issue/warning reason for metric labels."""
        base_reason = (reason or "").split(":", 1)[0]
        return self._normalize_metric_label(base_reason, fallback="unknown")

    def _normalize_metric_label(self, value: str, fallback: str = "unknown") -> str:
        """Convert label values to predictable, low-cardinality token format."""
        raw = (value or "").strip().lower()
        if not raw:
            return fallback

        normalized_chars = [char if char.isalnum() else "_" for char in raw]
        normalized = "".join(normalized_chars).strip("_")
        while "__" in normalized:
            normalized = normalized.replace("__", "_")
        return normalized or fallback

    # ── Content Cleaning ───────────────────────────────────────────────

    def clean_report_content(self, content: str) -> str:
        """Strip hallucinated tool-call XML, JSON tool results, and boilerplate."""
        if not content:
            return content

        original_len = len(content)

        cleaned = self.resolve_json_tool_result(content)
        if cleaned != content:
            logger.info(
                "Resolved JSON tool result (%d chars) to actual report content (%d chars)",
                len(content),
                len(cleaned),
            )
            content = cleaned

        cleaned = _TOOL_CALL_RE.sub("", content)
        cleaned = _FUNCTION_CALL_RE.sub("", cleaned)

        cleaned = _BOILERPLATE_FINAL_RESULT_RE.sub("", cleaned)
        cleaned = _BOILERPLATE_ARTIFACT_REFS_RE.sub("", cleaned)

        preamble_match = _PREAMBLE_RE.match(cleaned)
        if preamble_match and preamble_match.group(1).strip():
            preamble = preamble_match.group(1).strip()
            if len(preamble) < 500:
                logger.info("Stripped %d chars of preamble before first heading", len(preamble))
                cleaned = cleaned[preamble_match.end(1) :]

        cleaned = _EXCESS_BLANK_LINES_RE.sub("\n\n", cleaned)
        cleaned = cleaned.strip()

        removed = original_len - len(cleaned)
        if removed > 0:
            logger.info(
                "Cleaned %d chars of hallucinated tool-call XML / boilerplate from report content",
                removed,
            )

        return cleaned

    # ── Quality Detection ──────────────────────────────────────────────

    def is_meta_commentary(self, content: str) -> bool:
        """Detect when the LLM produced meta-commentary instead of actual content."""
        if not content or len(content) > 800:
            return False
        return bool(_META_COMMENTARY_RE.search(content))

    def is_low_quality_summary(self, content: str, research_depth: str = "STANDARD") -> bool:
        """Structural quality gate for summarization output.

        Args:
            content: The summarization output to check.
            research_depth: One of QUICK, STANDARD, DEEP, DEAL. Controls minimum length threshold.
        """
        if not content:
            return True

        # Depth-aware minimum lengths
        depth_min_chars: dict[str, int] = {
            "QUICK": 300,
            "STANDARD": 800,
            "DEEP": 1500,
            "DEAL": 500,
        }
        min_chars = depth_min_chars.get(research_depth.upper(), 800)

        # Long content is unlikely to be low quality
        if len(content) > max(1200, min_chars * 2):
            return False

        has_headings = bool(re.search(r"^#{1,3}\s+\S", content, re.MULTILINE))
        if has_headings:
            return False

        content_lower = content.lower()
        has_excuse = any(kw in content_lower for kw in _EXCUSE_KEYWORDS)
        if has_excuse:
            return True

        return len(content) < min_chars

    def is_research_report_quality(self, content: str) -> tuple[bool, list[str]]:
        """Check research-specific quality indicators.

        Returns:
            Tuple of (passed, issues) where issues lists specific problems found.
        """
        if not content:
            return False, ["empty_content"]

        issues: list[str] = []

        # Check for References section
        has_references = bool(re.search(r"^##\s+References?\s*$", content, re.MULTILINE | re.IGNORECASE))
        if not has_references:
            issues.append("missing_references_section")

        # Check for inline citations (at least 2)
        citation_count = len(set(re.findall(r"\[\d+\]", content)))
        if citation_count < 2:
            issues.append(f"insufficient_citations:{citation_count}")

        # Check for comparison tables (if applicable — informational, not blocking)
        has_table = bool(re.search(r"\|.*\|.*\|", content))
        if not has_table:
            issues.append("no_comparison_table")

        passed = "missing_references_section" not in issues and citation_count >= 2
        return passed, issues

    def is_report_structure(self, content: str) -> bool:
        """Check if content has report-like structure (headings, sections, or citations)."""
        if not content:
            return False

        heading_count = len(re.findall(r"^#{1,4}\s+.+", content, re.MULTILINE))
        if heading_count >= 2:
            return True

        bold_headers = len(re.findall(r"\*\*[^*]+:\*\*", content))
        if bold_headers >= 2:
            return True

        numbered_sections = len(re.findall(r"^\d+\.\s+[A-Z]", content, re.MULTILINE))
        if numbered_sections >= 2:
            return True

        # Also detect citation-heavy content + sufficient length as report-like
        citation_count = len(re.findall(r"\[\d+\]", content))
        return bool(citation_count >= 3 and len(content) > 1000)

    # ── Title Extraction ───────────────────────────────────────────────

    def extract_title(self, content: str) -> str:
        """Extract a title from markdown content."""
        lines = content.strip().split("\n")

        for line in lines[:10]:
            h1_match = re.match(r"^#\s+(.+)$", line.strip())
            if h1_match:
                return h1_match.group(1).strip()

        for line in lines[:10]:
            h2_match = re.match(r"^##\s+(.+)$", line.strip())
            if h2_match:
                return h2_match.group(1).strip()

        for line in lines[:5]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                clean = re.sub(r"\*(.+?)\*", r"\1", clean)
                return clean[:80] + ("..." if len(clean) > 80 else "")

        return "Task Report"

    # ── Fallback Recovery ──────────────────────────────────────────────

    def extract_fallback_summary(self) -> str:
        """Extract a fallback summary from the agent's conversation memory."""
        if self._pre_trim_report_cache and len(self._pre_trim_report_cache) > 200:
            logger.info(
                "Using pre-trim report cache as fallback summary (%d chars)",
                len(self._pre_trim_report_cache),
            )
            return self._pre_trim_report_cache

        if not self._memory:
            return ""

        messages = self._memory.get_messages()
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 50:
                continue
            cleaned = _TOOL_CALL_RE.sub("", content)
            cleaned = _FUNCTION_CALL_RE.sub("", cleaned).strip()
            if len(cleaned) >= 50:
                logger.info(
                    "Extracted fallback summary from conversation memory (%d chars)",
                    len(cleaned),
                )
                return f"# Task Summary\n\n{cleaned}"

        return ""

    def resolve_json_tool_result(self, content: str) -> str:
        """If content is a JSON tool result, recover the actual report content."""
        stripped = content.strip()

        codeblock_match = _JSON_CODEBLOCK_RE.match(stripped)
        if codeblock_match:
            stripped = codeblock_match.group(1).strip()

        if not (stripped.startswith("{") and stripped.endswith("}")):
            return content

        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return content

        if not isinstance(parsed, dict) or "success" not in parsed:
            return content

        is_success = parsed.get("success", False)
        logger.warning(
            "Summarization output is a JSON tool result (success=%s), recovering actual report content",
            is_success,
        )

        report_from_memory = self.extract_report_from_file_write_memory()
        if report_from_memory:
            return report_from_memory

        if self._pre_trim_report_cache:
            logger.info(
                "Using pre-trim report cache as recovery (%d chars)",
                len(self._pre_trim_report_cache),
            )
            return self._pre_trim_report_cache

        if is_success:
            result_text = parsed.get("result", "")
            if isinstance(result_text, str) and len(result_text.strip()) > 30:
                logger.info("Using tool result 'result' field as fallback report content")
                return result_text.strip()

        if not is_success:
            error_msg = parsed.get("message") or parsed.get("result") or parsed.get("error", "")
            if error_msg:
                logger.warning(
                    "JSON tool result has success=False with message: %.200s",
                    error_msg,
                )

        return ""

    def extract_report_from_file_write_memory(self) -> str | None:
        """Search conversation memory for the last file_write tool call with markdown content."""
        if not self._memory:
            return None

        messages = self._memory.get_messages()

        for msg in reversed(messages):
            tool_calls = msg.get("tool_calls")
            if not tool_calls or msg.get("role") != "assistant":
                continue

            for tc in tool_calls:
                func = tc.get("function", {})
                func_name = func.get("name", "")
                if func_name not in ("file_write", "file_create"):
                    continue

                args_str = func.get("arguments", "")
                if not args_str:
                    continue

                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except (json.JSONDecodeError, ValueError):
                    continue

                file_content = args.get("content", "")
                file_path = args.get("path", "")

                if (
                    isinstance(file_content, str)
                    and len(file_content.strip()) > 200
                    and isinstance(file_path, str)
                    and file_path.endswith(".md")
                ):
                    logger.info(
                        "Recovered report content from file_write memory (path=%s, %d chars)",
                        file_path,
                        len(file_content),
                    )
                    return file_content.strip()

        return None

    # ── Confirmation Summary (dead code preserved for future use) ──────

    async def generate_confirmation_summary(self, report_content: str, title: str | None) -> str | None:
        """Generate a brief confirmation message summarizing key findings."""
        from app.domain.services.prompts.execution import CONFIRMATION_SUMMARY_PROMPT

        try:
            excerpt = report_content[:2000]
            prompt = CONFIRMATION_SUMMARY_PROMPT.format(report_content=excerpt)
            response = await self._llm.ask(
                [{"role": "user", "content": prompt}],
                tools=None,
                tool_choice=None,
            )
            confirmation = response.get("content", "")
            if isinstance(confirmation, str) and len(confirmation.strip()) > 30:
                return confirmation.strip()
        except Exception as e:
            logger.debug(f"Confirmation summary generation failed: {e}")
        return None

    # ── Follow-Up Suggestions ──────────────────────────────────────────

    async def generate_follow_up_suggestions(self, title: str, content: str) -> list[str]:
        """Generate follow-up suggestions grounded in session context."""
        try:
            user_request_context = f'User request: "{self._user_request}"\n' if self._user_request else ""
            content_excerpt = content[:500] + ("..." if len(content) > 500 else "")
            recent_session_context = self._build_recent_memory_context_excerpt()
            recent_context_block = (
                f"Recent session context:\n{recent_session_context}\n\n" if recent_session_context else ""
            )

            suggestion_response = await self._llm.ask(
                [
                    {
                        "role": "user",
                        "content": (
                            f"{user_request_context}"
                            f"{recent_context_block}"
                            f'Completion title: "{title}"\n'
                            f"Summary excerpt: {content_excerpt}\n\n"
                            "Generate exactly 3 short follow-up questions (5-15 words each) that are grounded "
                            "in the actual completion results and user's original request. "
                            "Suggestions should help the user explore next steps or dive deeper into specific "
                            "aspects. "
                            'Return ONLY a JSON object in this format: {"suggestions": ["...", "...", "..."]}.'
                        ),
                    }
                ],
                tools=None,
                response_format={"type": "json_object"},
                tool_choice=None,
            )
            raw = suggestion_response.get("content", {"suggestions": []})
            suggestions = self._parse_suggestions_payload(raw)
            normalized = [str(s).strip() for s in suggestions if str(s).strip()]
            if normalized:
                return normalized[:3]
        except Exception as e:
            logger.debug(f"Suggestion generation failed, using fallback suggestions: {e}")

        return self._default_follow_up_suggestions(title=title, content=content)

    def _default_follow_up_suggestions(self, title: str, content: str) -> list[str]:
        """Deterministic fallback suggestions used when LLM suggestion generation fails."""
        combined = f"{title} {content}".lower()
        if "pirate" in combined or "arrr" in combined:
            return [
                "Tell me a pirate story.",
                "What's your favorite pirate saying?",
                "How do pirates find treasure?",
            ]

        topic_hint = self._extract_topic_hint(f"{self._user_request or ''} {title} {content}")
        if topic_hint:
            return [
                f"Can you expand on {topic_hint} with a concrete example?",
                f"What should I prioritize next for {topic_hint}?",
                f"What risks should I watch for with {topic_hint}?",
            ]

        return [
            "Can you summarize this in three key points?",
            "What should I prioritize as next steps?",
            "Can you provide a practical example for this?",
        ]

    def _parse_suggestions_payload(self, payload: Any) -> list[str]:
        """Parse suggestion payload from LLM output using strict validation first."""
        if isinstance(payload, str):
            try:
                return _SuggestionPayload.model_validate_json(payload).suggestions
            except ValidationError:
                return _SUGGESTION_LIST_ADAPTER.validate_json(payload)

        if isinstance(payload, dict):
            return _SuggestionPayload.model_validate(payload).suggestions

        if isinstance(payload, list):
            return _SUGGESTION_LIST_ADAPTER.validate_python(payload)

        raise TypeError("Unsupported suggestion payload type")

    def _build_recent_memory_context_excerpt(self, max_messages: int = 6, max_chars: int = 900) -> str:
        """Build a short user/assistant transcript excerpt from in-memory session messages."""
        if not self._memory:
            return ""

        try:
            messages = self._memory.get_messages()
        except Exception:
            return ""

        if not messages:
            return ""

        lines: list[str] = []
        for entry in reversed(messages):
            if not isinstance(entry, dict):
                continue

            role = str(entry.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue

            raw_content = entry.get("content")
            if isinstance(raw_content, str):
                text = raw_content.strip()
            else:
                text = str(raw_content).strip() if raw_content is not None else ""

            if not text:
                continue

            speaker = "User" if role == "user" else "Assistant"
            lines.append(f"{speaker}: {text[:220]}")
            if len(lines) >= max_messages:
                break

        if not lines:
            return ""

        transcript = "\n".join(reversed(lines))
        return transcript[:max_chars]

    def _extract_topic_hint(self, text: str) -> str | None:
        """Extract a compact topic hint from free text for fallback suggestion templates.

        Extraction priority:
        1. Quoted phrases ("noise-canceling headphones")
        2. Capitalized multi-word entities (FastAPI, Claude Code)
        3. Naive tokenization fallback (longest non-stopword tokens)
        """
        if not text:
            return None

        # Priority 1: quoted phrases
        quoted = re.findall(r'"([^"]{3,40})"', text)
        if quoted:
            return quoted[0]

        # Priority 2: capitalized multi-word entities (2-4 words starting with uppercase)
        entities = re.findall(r"\b([A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*){1,3})\b", text)
        if entities:
            return entities[0]

        # Priority 3: naive tokenization
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = [token for token in cleaned.split() if len(token) >= 4]
        if not tokens:
            return None

        stopwords = {
            "that",
            "this",
            "with",
            "from",
            "have",
            "what",
            "when",
            "where",
            "which",
            "would",
            "could",
            "should",
            "your",
            "about",
            "into",
            "there",
            "them",
            "then",
            "only",
            "more",
            "next",
            "compare",
            "research",
            "find",
            "best",
            "like",
            "also",
            "some",
            "very",
        }
        filtered = [token for token in tokens if token not in stopwords]
        candidates = filtered or tokens
        return " ".join(candidates[:3]) if candidates else None
