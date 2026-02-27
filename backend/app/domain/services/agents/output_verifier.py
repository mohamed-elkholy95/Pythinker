"""Output verification and hallucination detection for ExecutionAgent.

Encapsulates all verification pipelines extracted from ExecutionAgent:
- LettuceDetect encoder-based hallucination verification (primary)
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


class OutputVerifier:
    """Owns all verification / hallucination-detection logic.

    Responsibilities:
    - Apply LettuceDetect encoder-based hallucination detection
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
        "_lettuce_enabled",
        "_llm",
        "_metrics",
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
        lettuce_enabled: bool = True,
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
        self._lettuce_enabled: bool = lettuce_enabled

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

        Returns each source snippet as a separate list element — LettuceDetect's
        predict() API expects list[str] where each item is an independent
        context chunk. Truncation to 4K total chars is handled by LettuceVerifier.

        Returns:
            List of source context strings.
        """
        collected = self._source_tracker._collected_sources
        if not collected:
            return []

        chunks: list[str] = []
        for source in collected:
            snippet = source.snippet or ""
            if snippet.strip():
                chunks.append(snippet)

        return chunks

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
        """Apply hallucination verification using LettuceDetect (or CoVe fallback).

        LettuceDetect uses a ModernBERT encoder to classify each token in the
        answer as supported or hallucinated, grounded against collected source
        context. This runs in ~100ms with zero LLM calls.

        Falls back to CoVe if LettuceDetect is disabled or unavailable.

        Args:
            content: The content to verify.
            query: Original user query for context.

        Returns:
            Verified content (hallucinated spans redacted if detected).
        """
        from app.domain.services.agents.context_manager import InsightType

        flags = self._resolve_feature_flags()

        # Try LettuceDetect first (preferred: fast, no LLM cost)
        if self._lettuce_enabled and flags.get("lettuce_verification", True):
            try:
                from app.domain.services.agents.lettuce_verifier import get_lettuce_verifier

                verifier = get_lettuce_verifier()

                # Build grounding context from collected sources
                source_context = self.build_source_context()

                result = verifier.verify(
                    context=source_context,
                    question=query,
                    answer=content,
                )

                if not result.skipped and result.has_hallucinations:
                    logger.warning(
                        "LettuceDetect: %d hallucinated span(s), confidence: %.2f, ratio: %.1f%%",
                        len(result.hallucinated_spans),
                        result.confidence_score,
                        result.hallucination_ratio * 100,
                    )
                    self._context_manager.add_insight(
                        insight_type=InsightType.ERROR_LEARNING,
                        content=(
                            f"LettuceDetect found {len(result.hallucinated_spans)} hallucinated span(s) "
                            f"({result.hallucination_ratio:.1%} of text)"
                        ),
                        confidence=0.9,
                        tags=["hallucination", "lettuce", "verification"],
                    )

                    # Record Prometheus metric
                    self._metrics.increment(
                        "pythinker_hallucination_detections_total",
                        labels={
                            "method": "lettuce",
                            "span_count": str(len(result.hallucinated_spans)),
                        },
                    )

                    # Tiered response based on hallucination severity:
                    # - >25%: disclaimer (too many spans to redact cleanly)
                    # - 10-25%: redact individual spans with […] markers
                    # - <10%: pass through (noise-level, not actionable)
                    if result.hallucination_ratio > 0.25:
                        disclaimer = (
                            "\n\n> **Note:** Some information in this response "
                            "could not be fully verified against available sources."
                        )
                        return content + disclaimer
                    if result.hallucination_ratio > 0.10:
                        # Redact individual hallucinated spans with neutral markers
                        redacted = verifier.redact_hallucinations(content, result.hallucinated_spans)
                        logger.info(
                            "LettuceDetect: redacted %d span(s) (ratio=%.1f%%)",
                            len(result.hallucinated_spans),
                            result.hallucination_ratio * 100,
                        )
                        return redacted
                    return content

                if not result.skipped:
                    logger.info("LettuceDetect: %s", result.get_summary())

                return content

            except Exception as e:
                logger.warning("LettuceDetect failed, falling back to CoVe: %s", e)

        # Fallback: CoVe (deprecated, disabled by default)
        if self._cove_enabled and flags.get("chain_of_verification", False):
            verified, _ = await self.apply_cove_verification(content, query)
            return verified

        return content

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
