"""Output verification and hallucination detection for ExecutionAgent.

Encapsulates all verification pipelines extracted from ExecutionAgent:
- LLM-based grounding verification (primary — claim-level fact checking)
- Chain-of-Verification (CoVe) — deprecated fallback
- Critic revision loop (dormant, not actively called)
- Heuristic gating (_needs_cove_verification)

Usage:
    verifier = OutputVerifier(
        llm=llm,
        critic=critic,
        cove=cove,
        context_manager=context_manager,
        source_tracker=source_tracker,
        resolve_feature_flags_fn=resolve_fn,
    )
    content = await verifier.apply_hallucination_verification(content, query)
    needs_it = verifier.needs_verification(content, query)

This is a pure domain service with zero infrastructure imports.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.external.llm import LLM
    from app.domain.external.observability import MetricsPort
    from app.domain.models.file import FileInfo
    from app.domain.services.agents.chain_of_verification import ChainOfVerification, CoVeResult
    from app.domain.services.agents.context_manager import ContextManager
    from app.domain.services.agents.critic import CriticAgent
    from app.domain.services.agents.source_tracker import SourceTracker

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HallucinationVerificationResult:
    """Structured result for hallucination verification and delivery gating."""

    content: str
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hallucination_ratio: float | None = None
    span_count: int = 0
    skipped: bool = False


class OutputVerifier:
    """Owns all verification / hallucination-detection logic.

    Responsibilities:
    - Apply LLM-based grounding verification (claim-level fact checking)
    - Apply CoVe (Chain-of-Verification) as deprecated fallback
    - Apply critic revision loop (dormant)
    - Heuristic gating for when verification is needed
    - Build grounding context from collected sources

    The verifier does NOT import any infrastructure; external deps
    (LLM, critic, CoVe, source tracker) are injected via constructor.
    """

    __slots__ = (
        "_context_manager",
        "_cove",
        "_cove_enabled",
        "_critic",
        "_hallucination_verification_enabled",
        "_llm",
        "_metrics",
        "_research_depth",
        "_resolve_feature_flags_fn",
        "_source_tracker",
        "_user_request",
    )

    def __init__(
        self,
        *,
        llm: LLM,
        critic: CriticAgent,
        cove: ChainOfVerification,
        context_manager: ContextManager,
        source_tracker: SourceTracker,
        metrics: MetricsPort | None = None,
        resolve_feature_flags_fn: Any = None,
        cove_enabled: bool = False,
        hallucination_verification_enabled: bool = True,
    ) -> None:
        from app.domain.external.observability import get_null_metrics

        self._llm: LLM = llm
        self._critic: CriticAgent = critic
        self._cove: ChainOfVerification = cove
        self._context_manager: ContextManager = context_manager
        self._source_tracker: SourceTracker = source_tracker
        self._metrics: MetricsPort = metrics or get_null_metrics()
        self._resolve_feature_flags_fn = resolve_feature_flags_fn
        self._cove_enabled: bool = cove_enabled
        self._hallucination_verification_enabled: bool = hallucination_verification_enabled
        self._research_depth: str | None = None

        # Mutable state (set per-run by the caller)
        self._user_request: str | None = None

    # ── State Setters ──────────────────────────────────────────────────

    def set_user_request(self, request: str | None) -> None:
        self._user_request = request

    # ── Feature Flags ──────────────────────────────────────────────────

    def _resolve_feature_flags(self) -> dict[str, bool]:
        if self._resolve_feature_flags_fn:
            try:
                return self._resolve_feature_flags_fn()
            except Exception:
                return {}
        return {}

    # ── Source Context ─────────────────────────────────────────────────

    def build_source_context(self) -> list[str]:
        """Build grounding context from collected sources for hallucination verification.

        Returns each source snippet as a separate list element for the
        grounding verifier. Context trimming is handled by the caller.

        Returns:
            List of source context strings.
        """
        collected = self._source_tracker._collected_sources

        chunks: list[str] = []
        for source in collected:
            snippet = source.snippet or ""
            # Prepend title and URL so the grounding verifier can ground entity
            # names, project names, and URLs that appear in the synthesized report.
            prefix_parts: list[str] = []
            if source.title and source.title != source.url:
                prefix_parts.append(source.title)
            if source.url:
                prefix_parts.append(source.url)
            prefix = " — ".join(prefix_parts)
            if snippet.strip():
                chunk = f"{prefix}: {snippet}" if prefix else snippet
            elif prefix:
                chunk = prefix
            else:
                continue
            chunks.append(chunk)

        # Supplement with key facts from execution context — these contain
        # extracted details from browser visits and tool results that aren't
        # captured in source tracker snippets.
        if hasattr(self._context_manager, "_context") and self._context_manager._context.key_facts:
            chunks.extend(fact for fact in self._context_manager._context.key_facts if fact and len(fact) > 20)

        return chunks

    # ── Content Exemption ──────────────────────────────────────────────

    _NUMERIC_TABLE_RE = re.compile(
        r"[\$€£]\s*\d|[\d.]+\s*%|\d+\.\d+\s*points|score.per.dollar",
        re.IGNORECASE,
    )

    # Patterns that produce systematic false positives in verification:
    # - Bare URLs (not in source context verbatim)
    # - Mermaid diagram syntax (graph TD, flowchart, etc.)
    # - Reference/bibliography sections ([N] Title - URL)
    _MERMAID_BLOCK_RE = re.compile(
        r"```(?:mermaid|graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|gantt|pie|erDiagram)"
        r".*?```",
        re.DOTALL,
    )
    _REFERENCE_SECTION_RE = re.compile(
        r"(?:^|\n)#{1,4}\s*(?:References|Sources|Bibliography|Works Cited|Citations)\s*\n"
        r"((?:\s*(?:\[?\d+\]?\.?\s*)?(?:https?://\S+|[^\n]+https?://\S+)\s*\n?)+)",
        re.IGNORECASE | re.MULTILINE,
    )
    _BARE_URL_LINE_RE = re.compile(
        r"^\s*(?:\[?\d+\]?\.?\s+)?(?:[^\n]*?\s)?https?://\S+\s*$",
        re.MULTILINE,
    )

    @staticmethod
    def _strip_unverifiable_content(text: str) -> str:
        """Remove content patterns that produce systematic false positives.

        These patterns are not factual claims and should be excluded from
        hallucination verification:
        - Mermaid diagram blocks (graph syntax, not factual claims)
        - Reference/bibliography sections (URL lists)
        - Lines that are primarily bare URLs with citation numbers
        """
        if not text:
            return text

        stripped = text
        mermaid_count = 0
        ref_count = 0
        url_line_count = 0

        # Strip Mermaid blocks
        mermaid_matches = OutputVerifier._MERMAID_BLOCK_RE.findall(stripped)
        mermaid_count = len(mermaid_matches)
        stripped = OutputVerifier._MERMAID_BLOCK_RE.sub("", stripped)

        # Strip reference/bibliography sections
        ref_matches = OutputVerifier._REFERENCE_SECTION_RE.findall(stripped)
        ref_count = len(ref_matches)
        stripped = OutputVerifier._REFERENCE_SECTION_RE.sub("", stripped)

        # Strip bare URL citation lines (e.g. "[6] Title - https://...")
        url_lines = OutputVerifier._BARE_URL_LINE_RE.findall(stripped)
        url_line_count = len(url_lines)
        stripped = OutputVerifier._BARE_URL_LINE_RE.sub("", stripped)

        if mermaid_count or ref_count or url_line_count:
            logger.info(
                "Exempted %d Mermaid block(s), %d reference section(s), "
                "and %d URL citation line(s) from hallucination check",
                mermaid_count,
                ref_count,
                url_line_count,
            )

        return stripped

    @staticmethod
    def _strip_cited_tables(text: str) -> str:
        """Remove markdown table blocks that contain citation markers [N].

        Tables with inline citations are sourced data — the verifier cannot
        cross-reference structured tabular content against source text,
        producing false positives on the most valuable report sections.

        Strategy: Two-pass approach.
        Pass 1: Identify contiguous table blocks (runs of lines starting/ending with |).
        Pass 2: If ANY data row in the block contains [N], remove the entire block.
        """
        if not text:
            return text

        lines = text.split("\n")
        # Group lines into table blocks and non-table segments
        segments: list[tuple[str, list[str]]] = []  # ("table"|"text", lines)
        current_type = "text"
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            is_table_row = stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1

            if is_table_row and current_type == "table":
                current_lines.append(line)
            elif is_table_row and current_type == "text":
                if current_lines:
                    segments.append((current_type, current_lines))
                current_type = "table"
                current_lines = [line]
            elif not is_table_row and current_type == "table":
                segments.append((current_type, current_lines))
                current_type = "text"
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            segments.append((current_type, current_lines))

        # Rebuild text, skipping table blocks that contain citations or
        # dense numeric/currency data (verifier cannot reliably check computed values).
        result_lines: list[str] = []
        cited_row_count = 0
        numeric_table_count = 0
        for seg_type, seg_lines in segments:
            if seg_type == "table":
                has_citation = any(re.search(r"\[\d+\]", line) for line in seg_lines)
                if has_citation:
                    cited_row_count += sum(1 for ln in seg_lines if re.search(r"\[\d+\]", ln))
                    continue  # Skip entire table block
                # Also exempt tables dense with numeric/currency values —
                # Verifier cannot reliably check arithmetic derivations.
                data_rows = [ln for ln in seg_lines if not re.match(r"^\s*\|[-:| ]+\|\s*$", ln)]
                numeric_rows = sum(1 for ln in data_rows if OutputVerifier._NUMERIC_TABLE_RE.search(ln))
                if data_rows and numeric_rows / len(data_rows) > 0.5:
                    numeric_table_count += len(data_rows)
                    continue  # Skip numeric-heavy table block
            result_lines.extend(seg_lines)

        if cited_row_count > 0 or numeric_table_count > 0:
            logger.info(
                "Exempted %d cited table row(s) and %d numeric table row(s) from hallucination check",
                cited_row_count,
                numeric_table_count,
            )

        return "\n".join(result_lines)

    # ── Needs Verification (Heuristic Gate) ────────────────────────────

    def needs_verification(self, content: str, query: str) -> bool:
        """Determine if content needs hallucination verification.

        Delegates to _needs_cove_verification which contains the heuristic
        for detecting research/factual/comparative content.
        """
        return self._needs_cove_verification(content, query)

    def _needs_cove_verification(self, content: str, query: str) -> bool:
        """Determine if content needs Chain-of-Verification.

        We apply CoVe selectively to:
        - Research/factual tasks (not creative writing)
        - Content with specific metrics, benchmarks, or statistics
        - Comparative analyses (high risk of data asymmetry)
        - Content over a minimum length threshold

        Args:
            content: Content to potentially verify
            query: Original query for context

        Returns:
            True if content should be verified
        """
        # Length threshold — lowered to catch hallucinations in shorter responses
        if len(content) < 200:
            return False

        query_lower = query.lower() if query else ""
        content_lower = content.lower()

        # Research/factual task indicators
        research_indicators = [
            "research",
            "analyze",
            "compare",
            "benchmark",
            "statistics",
            "study",
            "report",
            "data",
            "metrics",
            "performance",
            "evaluate",
            "assessment",
            "findings",
            "results",
        ]

        # Comparative task indicators (high hallucination risk)
        comparison_indicators = [
            "compare",
            "comparison",
            "versus",
            " vs ",
            " vs.",
            "difference",
            "better than",
            "worse than",
            "ranking",
            "ranked",
            "top ",
        ]

        # Metric/number patterns in content
        has_percentages = bool(re.search(r"\d+(\.\d+)?%", content))
        has_benchmarks = any(
            bench in content_lower for bench in ["mmlu", "humaneval", "gsm8k", "hellaswag", "arc", "winogrande"]
        )
        has_dates = bool(re.search(r"\b20\d{2}\b", content))

        # Decision logic
        is_research_task = any(ind in query_lower for ind in research_indicators)
        is_comparison = any(ind in query_lower or ind in content_lower for ind in comparison_indicators)
        has_factual_claims = has_percentages or has_benchmarks or has_dates

        # Apply CoVe if:
        # 1. It's a research task with factual claims, OR
        # 2. It's a comparison (high data asymmetry risk), OR
        # 3. It has benchmarks (often hallucinated)
        should_verify = (is_research_task and has_factual_claims) or is_comparison or has_benchmarks

        if should_verify:
            logger.debug(
                f"CoVe needed: research={is_research_task}, comparison={is_comparison}, "
                f"factual={has_factual_claims}, benchmarks={has_benchmarks}"
            )

        return should_verify

    # ── Hallucination Verification (Primary Entry Point) ───────────────

    async def apply_hallucination_verification(self, content: str, query: str) -> str:
        """Apply hallucination verification using LLM-based grounding (or CoVe fallback).

        Uses the LLM grounding verifier to extract factual claims from the
        response and classify each against source context. Returns content
        with disclaimer appended if hallucination score exceeds thresholds.

        Falls back to CoVe if grounding verification is disabled or unavailable.

        Args:
            content: The content to verify.
            query: Original user query for context.

        Returns:
            Verified content (with disclaimer if hallucinations detected).
        """
        result = await self.verify_hallucination(content, query)
        return result.content

    async def verify_hallucination(self, content: str, query: str) -> HallucinationVerificationResult:
        """Run hallucination verification and return structured severity information."""
        from app.domain.services.agents.context_manager import InsightType

        flags = self._resolve_feature_flags()

        # Try LLM grounding verification (primary: claim-level fact checking)
        if self._hallucination_verification_enabled and flags.get("hallucination_verification", True):
            try:
                from app.domain.services.agents.llm_grounding_verifier import get_llm_grounding_verifier

                verifier = get_llm_grounding_verifier()

                # Build grounding context from collected sources
                source_context = self.build_source_context()

                # Use expanded context for DEEP research (design 4B)
                from app.core.config import get_settings

                settings = get_settings()
                default_size = getattr(settings, "hallucination_grounding_context_size", 4096)
                if getattr(self, "_research_depth", None) == "DEEP":
                    context_size = getattr(settings, "hallucination_grounding_context_deep", 8192)
                else:
                    context_size = default_size
                # Trim chunks so total chars do not exceed context_size
                trimmed_context: list[str] = []
                _total = 0
                for _chunk in source_context:
                    if _total + len(_chunk) > context_size:
                        _remaining = context_size - _total
                        if _remaining > 50:
                            trimmed_context.append(_chunk[:_remaining])
                        break
                    trimmed_context.append(_chunk)
                    _total += len(_chunk)
                source_context = trimmed_context or source_context

                # Exempt content patterns that produce systematic false positives:
                # cited tables, Mermaid diagrams, reference sections, URL citation lines
                content_for_verification = self._strip_cited_tables(content)
                content_for_verification = self._strip_unverifiable_content(content_for_verification)

                grounding_result = await verifier.verify(
                    response_text=content_for_verification,
                    source_context=source_context,
                )

                if not grounding_result.skipped and grounding_result.flagged_claims:
                    logger.warning(
                        "LLM grounding: %d unsupported claim(s), score: %.1f%%",
                        len(grounding_result.flagged_claims),
                        grounding_result.hallucination_score * 100,
                    )

                    # Log individual flagged claims for post-hoc analysis
                    for claim in grounding_result.flagged_claims:
                        logger.info(
                            "Flagged claim | verdict=%s | text_preview=%.200s",
                            claim.verdict,
                            claim.claim_text,
                        )

                    self._context_manager.add_insight(
                        insight_type=InsightType.ERROR_LEARNING,
                        content=(
                            f"LLM grounding found {len(grounding_result.flagged_claims)} unsupported claim(s) "
                            f"({grounding_result.hallucination_score:.1%} of claims)"
                        ),
                        confidence=0.9,
                        tags=["hallucination", "llm_grounding", "verification"],
                    )

                    # Record Prometheus metric
                    self._metrics.increment(
                        "pythinker_hallucination_detections_total",
                        labels={
                            "method": "llm_grounding",
                            "span_count": str(len(grounding_result.flagged_claims)),
                        },
                    )

                    # Tiered response based on hallucination severity:
                    # - >block_threshold: blocking issue + disclaimer
                    # - warn_threshold-block_threshold: reliability notice (non-blocking)
                    # - <warn_threshold: pass through (noise-level, not actionable)
                    _block_threshold = settings.hallucination_block_threshold
                    _warn_threshold = settings.hallucination_warn_threshold
                    if grounding_result.hallucination_score > _block_threshold:
                        disclaimer = (
                            "\n\n> **Note:** Some information in this response "
                            "could not be fully verified against available sources."
                        )
                        return HallucinationVerificationResult(
                            content=content + disclaimer,
                            blocking_issues=["hallucination_ratio_critical"],
                            warnings=["hallucination_detected"],
                            hallucination_ratio=grounding_result.hallucination_score,
                            span_count=len(grounding_result.flagged_claims),
                        )
                    if grounding_result.hallucination_score > _warn_threshold:
                        ratio_pct = grounding_result.hallucination_score * 100
                        disclaimer = (
                            f"\n\n> ⚠️ **Reliability Notice ({ratio_pct:.1f}% unverified):** "
                            f"{len(grounding_result.flagged_claims)} claim(s) in this report could not be "
                            "fully verified against available sources. Treat specific facts, version numbers, "
                            "and statistics with caution."
                        )
                        logger.info(
                            "LLM grounding: appending disclaimer for moderate score %.1f%%",
                            ratio_pct,
                        )
                        return HallucinationVerificationResult(
                            content=content + disclaimer,
                            warnings=["hallucination_ratio_moderate"],
                            hallucination_ratio=grounding_result.hallucination_score,
                            span_count=len(grounding_result.flagged_claims),
                        )
                    return HallucinationVerificationResult(
                        content=content,
                        warnings=["hallucination_ratio_low"],
                        hallucination_ratio=grounding_result.hallucination_score,
                        span_count=len(grounding_result.flagged_claims),
                    )

                if not grounding_result.skipped:
                    logger.info(
                        "LLM grounding: all claims supported (score=%.2f)",
                        grounding_result.hallucination_score,
                    )
                else:
                    warning = (
                        "hallucination_verification_skipped_no_grounding_context"
                        if not source_context
                        else "hallucination_verification_skipped"
                    )
                    return HallucinationVerificationResult(
                        content=content,
                        warnings=[warning],
                        skipped=True,
                    )

                return HallucinationVerificationResult(content=content)

            except Exception as e:
                logger.warning("LLM grounding verification failed, falling back to CoVe: %s", e)

        # Fallback: CoVe (deprecated, disabled by default)
        if self._cove_enabled and flags.get("chain_of_verification", False):
            verified, _ = await self.apply_cove_verification(content, query)
            return HallucinationVerificationResult(content=verified)

        return HallucinationVerificationResult(content=content)

    # ── Chain-of-Verification (Deprecated Fallback) ────────────────────

    async def apply_cove_verification(self, content: str, query: str) -> tuple[str, CoVeResult | None]:
        """Apply Chain-of-Verification to reduce hallucinations in factual content.

        CoVe works by:
        1. Generating verification questions for key claims
        2. Answering those questions independently (without seeing original)
        3. Revising the response based on verification results

        This is particularly effective for:
        - Research tasks with specific metrics/benchmarks
        - Comparative analyses (where data asymmetry often occurs)
        - Factual summaries with dates, numbers, or statistics

        Args:
            content: The content to verify
            query: Original user query for context

        Returns:
            Tuple of (verified_content, CoVeResult or None if skipped)
        """
        from app.domain.services.agents.context_manager import InsightType

        if not self._cove_enabled:
            return content, None

        # Check feature flags
        flags = self._resolve_feature_flags()
        if not flags.get("chain_of_verification", True):
            return content, None

        # Detect if this is a factual/research task that needs verification
        if not self._needs_cove_verification(content, query):
            logger.debug("CoVe: Skipping - content doesn't require verification")
            return content, None

        try:
            logger.info("CoVe: Starting verification pipeline...")
            result = await self._cove.verify_and_refine(
                query=query,
                response=content,
                skip_if_short=True,
            )

            if result.has_contradictions:
                logger.warning(
                    f"CoVe: Found {result.claims_contradicted} contradictions, "
                    f"confidence: {result.confidence_score:.2f}"
                )
                # Record insight about hallucination detection
                self._context_manager.add_insight(
                    insight_type=InsightType.ERROR_LEARNING,
                    content=f"CoVe detected {result.claims_contradicted} contradicted claims",
                    confidence=0.9,
                    tags=["hallucination", "cove", "verification"],
                )
                return result.verified_response, result
            if result.claims_uncertain > 0:
                logger.info(
                    f"CoVe: {result.claims_verified} verified, "
                    f"{result.claims_uncertain} uncertain, "
                    f"confidence: {result.confidence_score:.2f}"
                )
                # If many uncertain claims, still use refined response
                if result.claims_uncertain > result.claims_verified:
                    return result.verified_response, result
            else:
                logger.info(
                    f"CoVe: All {result.claims_verified} claims verified, confidence: {result.confidence_score:.2f}"
                )

            return content, result

        except Exception as e:
            logger.warning(f"CoVe verification failed (continuing with original): {e}")
            return content, None

    # ── Critic Revision (Dormant — No Active Callers) ──────────────────

    async def apply_critic_revision(self, message_content: str, attachments: list[FileInfo]) -> str:
        """Apply critic review with actual revision support.

        This method implements a revision loop that actually improves the output
        based on critic feedback, rather than just appending notes.

        Note: Currently dormant — the critic revision loop in summarize() is
        intentionally disabled. Kept for future re-enablement.

        Args:
            message_content: The original message content
            attachments: List of file attachments

        Returns:
            Revised content (or original if approved/revision failed)
        """
        from app.domain.services.agents.critic import CriticVerdict

        max_revisions = self._critic.config.max_revision_attempts
        current_content = message_content
        revision_count = 0

        while revision_count < max_revisions:
            try:
                review = await self._critic.review_output(
                    user_request=self._user_request,
                    output=current_content,
                    task_context="Task completion summary",
                    files=[f.file_path for f in attachments] if attachments else None,
                )

                logger.info(
                    f"Critic review (attempt {revision_count + 1}): {review.verdict.value} ({review.confidence:.2f})"
                )

                # If approved, return the current content
                if review.verdict == CriticVerdict.APPROVE:
                    logger.debug("Critic approved output")
                    return current_content

                # If rejected, log and return original (can't fix fundamental issues)
                if review.verdict == CriticVerdict.REJECT:
                    logger.warning(f"Critic rejected output: {review.summary}")
                    return current_content

                # If revision needed, actually revise the content
                if review.verdict == CriticVerdict.REVISE and review.issues:
                    revision_count += 1
                    logger.info(f"Critic requested revision {revision_count}: {review.summary}")

                    # Build revision prompt
                    revision_guidance = await self._critic.get_revision_guidance(current_content, review)

                    # Ask LLM to revise the content
                    try:
                        revision_messages = [
                            {
                                "role": "system",
                                "content": (
                                    "You are revising your previous output based on quality feedback. "
                                    "Make the specific improvements requested while preserving the good parts. "
                                    "Return the complete revised output in the same format."
                                ),
                            },
                            {"role": "user", "content": revision_guidance},
                        ]

                        response = await self._llm.ask(revision_messages, tools=None, tool_choice=None)

                        revised_content = response.get("content", "")
                        if revised_content and len(revised_content) > 100:
                            logger.info(
                                f"Revision {revision_count} applied "
                                f"(original: {len(current_content)} chars, "
                                f"revised: {len(revised_content)} chars)"
                            )
                            current_content = revised_content
                        else:
                            logger.warning("Revision produced insufficient content, keeping original")
                            break

                    except Exception as e:
                        logger.warning(f"Revision attempt failed: {e}")
                        break
                else:
                    # No issues identified, accept current content
                    break

            except Exception as e:
                logger.warning(f"Critic review failed (continuing with current content): {e}")
                break

        # If we exhausted revisions, add a note about best-effort improvement
        if revision_count >= max_revisions:
            logger.info(f"Max revisions ({max_revisions}) reached, delivering best version")

        return current_content
