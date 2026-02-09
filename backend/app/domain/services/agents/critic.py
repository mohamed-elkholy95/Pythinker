"""CriticAgent for self-correction and quality assurance.

The CriticAgent reviews outputs before they are delivered to the user,
checking for accuracy, completeness, security issues, and alignment with
the original request. This implements the "Self-Correction Loops" pattern
from the AI Agent Management Framework.

Usage:
    critic = CriticAgent(llm, json_parser)

    # Review an output
    review = await critic.review_output(
        user_request="Create a login form",
        output="<html>...",
        task_context="Frontend development task"
    )

    if review.verdict == CriticVerdict.REVISE:
        # Get revision suggestions and rerun
        revised = await executor.revise(review.suggestions)
"""

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_feature_flags
from app.domain.external.llm import LLM
from app.domain.external.observability import MetricsPort, get_null_metrics
from app.domain.models.claim_provenance import ProvenanceStore
from app.domain.models.event import BaseEvent, MessageEvent
from app.domain.models.source_attribution import AttributionSummary, SourceAttribution
from app.domain.models.url_verification import BatchURLVerificationResult, URLVerificationStatus
from app.domain.services.agents.content_hallucination_detector import (
    ContentHallucinationDetector,
    HallucinationAnalysisResult,
)
from app.domain.services.agents.grounding_validator import EnhancedGroundingResult
from app.domain.services.agents.reward_scoring import RewardScorer
from app.domain.services.agents.task_state_manager import get_task_state_manager
from app.domain.services.prompts.critic import (
    CRITIC_SYSTEM_PROMPT,
    FACT_CHECK_PROMPT,
    FIVE_CHECK_PROMPT,
    QUICK_VALIDATE_PROMPT,
    REVIEW_CODE_PROMPT,
    REVIEW_OUTPUT_PROMPT,
    REVIEW_RESEARCH_PROMPT,
    REVISION_PROMPT,
    STRUCTURED_FEEDBACK_PROMPT,
)
from app.domain.services.tools.tool_tracing import get_tool_tracer
from app.domain.utils.json_parser import JsonParser

# Module-level metrics instance (can be overridden for testing)
_metrics: MetricsPort = get_null_metrics()


def set_metrics(metrics: MetricsPort) -> None:
    """Set the metrics instance for this module."""
    global _metrics
    _metrics = metrics


logger = logging.getLogger(__name__)


class CriticVerdict(str, Enum):
    """Possible verdicts from the critic review."""

    APPROVE = "approve"  # Output is good, deliver as-is
    REVISE = "revise"  # Output needs improvements
    REJECT = "reject"  # Output is fundamentally flawed, needs full redo


class ReviewType(str, Enum):
    """Type of content being reviewed."""

    GENERAL = "general"
    CODE = "code"
    RESEARCH = "research"


class CriticReview(BaseModel):
    """Structured review from the CriticAgent."""

    verdict: CriticVerdict = Field(description="Review verdict")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in verdict")
    issues: list[str] = Field(default_factory=list, description="Identified issues")
    suggestions: list[str] = Field(default_factory=list, description="Improvement suggestions")
    summary: str = Field(description="Brief explanation of the verdict")
    review_type: ReviewType = Field(default=ReviewType.GENERAL, description="Type of review performed")


class FactCheckRecommendation(str, Enum):
    """Recommendation from fact-checking analysis."""

    DELIVER = "deliver"  # Safe to deliver as-is
    ADD_CAVEATS = "add_caveats"  # Add disclaimers/caveats
    NEEDS_VERIFICATION = "needs_verification"  # Requires manual verification
    REJECT = "reject"  # Contains likely hallucinations


class FactCheckResult(BaseModel):
    """Result of pre-delivery fact checking."""

    claims_analyzed: int = Field(default=0, description="Number of claims analyzed")
    verified: int = Field(default=0, description="Number of verified claims")
    unverified: int = Field(default=0, description="Number of unverified claims")
    contradicted: int = Field(default=0, description="Number of contradicted claims")
    red_flags: list[str] = Field(default_factory=list, description="Specific concerns")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Overall confidence")
    recommendation: FactCheckRecommendation = Field(
        default=FactCheckRecommendation.DELIVER, description="Delivery recommendation"
    )
    caveats_to_add: list[str] = Field(
        default_factory=list, description="Disclaimers to add if recommendation is add_caveats"
    )


class StructuredImprovement(BaseModel):
    """Single structured improvement suggestion."""

    category: str = Field(description="Category: accuracy/completeness/clarity/security/performance")
    severity: str = Field(description="Severity: critical/major/minor/suggestion")
    issue: str = Field(description="Specific issue description")
    fix: str = Field(description="How to fix it")
    location: str | None = Field(default=None, description="Where in the output")


# ============================================================================
# 5-Check Framework (Phase 3 Enhancement)
# ============================================================================


class CheckSeverity(str, Enum):
    """Severity level for check failures."""

    CRITICAL = "critical"  # Must be fixed before delivery
    MAJOR = "major"  # Should be fixed
    MINOR = "minor"  # Nice to fix
    PASS = "pass"  # Check passed


class CheckResult(BaseModel):
    """Result of a single check in the 5-check framework."""

    check_name: str = Field(default="unknown", description="Name of the check")
    passed: bool = Field(default=True, description="Whether the check passed")
    severity: CheckSeverity = Field(default=CheckSeverity.PASS, description="Severity if failed")
    issues: list[str] = Field(default_factory=list, description="Specific issues found")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confidence in the result")
    remediation: str | None = Field(default=None, description="How to fix the issues")


class DataAsymmetryIssue(BaseModel):
    """Specific data asymmetry issue detected in comparisons."""

    item_a: str = Field(description="First item being compared")
    item_a_metric_type: str = Field(description="Type of metric for item A (quantitative/qualitative/none)")
    item_b: str = Field(description="Second item being compared")
    item_b_metric_type: str = Field(description="Type of metric for item B (quantitative/qualitative/none)")
    context: str = Field(description="The comparison context")
    suggestion: str = Field(description="How to fix the asymmetry")


def _default_check_result() -> CheckResult:
    """Create a default passing CheckResult for when LLM doesn't provide one."""
    return CheckResult(
        check_name="default",
        passed=True,
        severity=CheckSeverity.PASS,
        confidence=0.5,
    )


class FiveCheckResult(BaseModel):
    """Result of the comprehensive 5-check framework.

    The 5-check framework addresses:
    1. Factual Accuracy - Are claims verifiable?
    2. Completeness - Does output address the full request?
    3. Consistency - Is output internally consistent?
    4. Data Symmetry - Are comparisons using equivalent metrics?
    5. Grounding - Is output grounded in sources/tools?
    """

    accuracy_check: CheckResult = Field(
        default_factory=_default_check_result,
        description="Factual accuracy verification",
    )
    completeness_check: CheckResult = Field(
        default_factory=_default_check_result,
        description="Completeness of response",
    )
    consistency_check: CheckResult = Field(
        default_factory=_default_check_result,
        description="Internal consistency",
    )
    symmetry_check: CheckResult = Field(
        default_factory=_default_check_result,
        description="Data symmetry in comparisons",
    )
    grounding_check: CheckResult = Field(
        default_factory=_default_check_result,
        description="Source grounding verification",
    )

    overall_passed: bool = Field(default=True, description="Whether all critical checks passed")
    overall_confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall confidence score")
    critical_issues: list[str] = Field(default_factory=list, description="Critical issues to address")
    asymmetry_issues: list[DataAsymmetryIssue] = Field(
        default_factory=list, description="Specific data asymmetry issues"
    )

    def get_failed_checks(self) -> list[str]:
        """Get list of failed check names."""
        failed = []
        for check in [
            self.accuracy_check,
            self.completeness_check,
            self.consistency_check,
            self.symmetry_check,
            self.grounding_check,
        ]:
            if not check.passed:
                failed.append(check.check_name)
        return failed

    def has_critical_failures(self) -> bool:
        """Check if there are any critical severity failures."""
        for check in [
            self.accuracy_check,
            self.completeness_check,
            self.consistency_check,
            self.symmetry_check,
            self.grounding_check,
        ]:
            if check.severity == CheckSeverity.CRITICAL:
                return True
        return False

    def get_summary(self) -> str:
        """Get a summary of the 5-check results."""
        passed = sum(
            1
            for c in [
                self.accuracy_check,
                self.completeness_check,
                self.consistency_check,
                self.symmetry_check,
                self.grounding_check,
            ]
            if c.passed
        )
        failed = self.get_failed_checks()
        if not failed:
            return f"All 5 checks passed (confidence: {self.overall_confidence:.2f})"
        return f"{passed}/5 checks passed. Failed: {', '.join(failed)}. Confidence: {self.overall_confidence:.2f}"


class StructuredFeedback(BaseModel):
    """Structured feedback with actionable improvements."""

    overall_quality: float = Field(ge=0.0, le=1.0, description="Quality score")
    strengths: list[str] = Field(default_factory=list, description="Things done well")
    improvements: list[StructuredImprovement] = Field(default_factory=list, description="Actionable improvements")
    missing_elements: list[str] = Field(default_factory=list, description="Missing items")
    priority_order: list[int] = Field(default_factory=list, description="Priority ranking")


class CriticConfig(BaseModel):
    """Configuration for critic behavior."""

    enabled: bool = Field(default=True, description="Whether critic is active")
    min_confidence_threshold: float = Field(default=0.7, description="Minimum confidence to accept a verdict")
    max_revision_attempts: int = Field(default=2, description="Maximum revision attempts before accepting")
    auto_approve_simple_tasks: bool = Field(default=True, description="Skip review for simple tasks")
    review_code_security: bool = Field(default=True, description="Always review code for security issues")


@dataclass
class ReviewContext:
    """Context for a review operation."""

    user_request: str
    output: str
    task_context: str = ""
    files: list[str] = None
    sources: list[str] = None
    review_type: ReviewType = ReviewType.GENERAL
    language: str = ""  # For code reviews


class CriticAgent:
    """Agent that reviews outputs for quality assurance.

    The critic provides a second opinion on generated outputs, helping catch:
    - Hallucinations or factual errors
    - Security vulnerabilities in code
    - Incomplete or off-topic responses
    - Quality issues before delivery

    The critic is designed to be:
    - Fast: Uses efficient prompts and caching
    - Accurate: High precision to avoid false positives
    - Actionable: Provides specific, fixable feedback
    """

    def __init__(self, llm: LLM, json_parser: JsonParser, config: CriticConfig | None = None):
        """Initialize the CriticAgent.

        Args:
            llm: Language model for review
            json_parser: Parser for structured responses
            config: Optional configuration
        """
        self.llm = llm
        self.json_parser = json_parser
        self.config = config or CriticConfig()

        # Track review history for learning
        self._review_history: list[CriticReview] = []
        self._revision_count: int = 0

        # Initialize hallucination detector
        self._hallucination_detector = ContentHallucinationDetector()

    @property
    def _config(self) -> CriticConfig:
        """Backward-compatible config alias."""
        return self.config

    @_config.setter
    def _config(self, value: CriticConfig) -> None:
        self.config = value

    def _detect_review_type(self, output: str, task_context: str) -> ReviewType:
        """Automatically detect the type of content being reviewed."""
        output_lower = output.lower()
        context_lower = task_context.lower()

        # Code indicators
        code_indicators = [
            "def ",
            "function ",
            "class ",
            "import ",
            "const ",
            "let ",
            "var ",
            "```python",
            "```javascript",
            "```typescript",
            "```java",
            "public static",
            "private ",
            "#include",
            "package ",
        ]
        if any(indicator in output_lower for indicator in code_indicators):
            return ReviewType.CODE

        # Research indicators
        research_indicators = [
            "according to",
            "research shows",
            "studies indicate",
            "source:",
            "reference:",
            "citation",
            "findings suggest",
        ]
        if any(indicator in output_lower for indicator in research_indicators):
            return ReviewType.RESEARCH

        if any(term in context_lower for term in ["research", "investigate", "find information"]):
            return ReviewType.RESEARCH

        return ReviewType.GENERAL

    def _detect_code_language(self, output: str) -> str:
        """Detect programming language from code output."""
        if "```python" in output or "def " in output:
            return "python"
        if "```javascript" in output or "function " in output:
            return "javascript"
        if "```typescript" in output or "interface " in output:
            return "typescript"
        if "```java" in output or "public class " in output:
            return "java"
        if "```go" in output or "func " in output:
            return "go"
        if "```rust" in output or "fn " in output:
            return "rust"
        return "unknown"

    def _should_skip_review(self, output: str, task_context: str) -> bool:
        """Determine if review should be skipped for simple tasks."""
        if not self.config.auto_approve_simple_tasks:
            return False

        # Skip for very short outputs (likely simple acknowledgments)
        if len(output) < 100:
            return True

        # Skip for simple confirmations
        simple_patterns = ["done", "completed", "created", "updated", "file saved", "task complete"]
        output_lower = output.lower()
        return bool(any(pattern in output_lower for pattern in simple_patterns) and len(output) < 500)

    async def review_output(
        self,
        user_request: str,
        output: str,
        task_context: str = "",
        files: list[str] | None = None,
        sources: list[str] | None = None,
        force_review_type: ReviewType | None = None,
    ) -> CriticReview:
        """Review an output for quality assurance.

        Args:
            user_request: The original user request
            output: The generated output to review
            task_context: Additional context about the task
            files: List of files created/modified (for code reviews)
            sources: List of sources used (for research reviews)
            force_review_type: Override automatic review type detection

        Returns:
            CriticReview with verdict and feedback
        """
        if not self.config.enabled:
            logger.debug("Critic disabled, auto-approving")
            return CriticReview(
                verdict=CriticVerdict.APPROVE, confidence=1.0, summary="Critic disabled - auto-approved"
            )

        # Check if we should skip review
        if self._should_skip_review(output, task_context):
            logger.debug("Simple task detected, skipping critic review")
            return CriticReview(verdict=CriticVerdict.APPROVE, confidence=0.95, summary="Simple task - auto-approved")

        # Detect review type
        review_type = force_review_type or self._detect_review_type(output, task_context)
        logger.info(f"Critic reviewing output (type: {review_type.value})")

        # For research and comparison content, run 5-check framework first
        five_check_result = None
        if review_type == ReviewType.RESEARCH or self._detect_comparison_content(output, user_request):
            logger.info("Critic: Running 5-check framework for research/comparison content")
            five_check_result = await self.run_five_checks(
                output=output,
                user_request=user_request,
                sources_context="\n".join(sources) if sources else None,
            )

            # If 5-check found critical issues, reject immediately
            if five_check_result.has_critical_failures():
                logger.warning(f"5-check critical failures: {five_check_result.get_failed_checks()}")
                issues = five_check_result.critical_issues or []

                # Add asymmetry issues to the list
                for asym in five_check_result.asymmetry_issues[:3]:
                    issues.append(
                        f"Data asymmetry: {asym.item_a} has {asym.item_a_metric_type} metric but "
                        f"{asym.item_b} has {asym.item_b_metric_type}"
                    )

                review = CriticReview(
                    verdict=CriticVerdict.REVISE,
                    confidence=five_check_result.overall_confidence,
                    issues=issues,
                    suggestions=[
                        c.remediation
                        for c in [
                            five_check_result.accuracy_check,
                            five_check_result.symmetry_check,
                        ]
                        if c.remediation
                    ],
                    summary=f"5-check failed: {five_check_result.get_summary()}",
                    review_type=review_type,
                )
                self._record_review(review)
                return review

        # Reward hacking detection (log-only)
        flags = get_feature_flags()
        if flags.get("reward_hacking_detection"):
            try:
                task_state_manager = get_task_state_manager()
                recent_actions = task_state_manager.get_recent_actions() if task_state_manager else []
                traces = get_tool_tracer().get_recent_traces(limit=20)
                score = RewardScorer().score_output(
                    output=output,
                    user_request=user_request,
                    recent_actions=recent_actions,
                    tool_traces=traces,
                )
                if score.signals:
                    for signal in score.signals:
                        _metrics.record_reward_hacking_signal(signal.signal_type, signal.severity)
                    logger.warning(
                        "Reward hacking signals detected during critic review (log-only)",
                        extra={
                            "signals": [s.signal_type for s in score.signals],
                            "overall_score": score.overall,
                        },
                    )
            except Exception as e:
                logger.debug(f"Reward hacking detection failed: {e}")

        # Build review context
        context = ReviewContext(
            user_request=user_request,
            output=output,
            task_context=task_context,
            files=files or [],
            sources=sources or [],
            review_type=review_type,
            language=self._detect_code_language(output) if review_type == ReviewType.CODE else "",
        )

        # Get the appropriate prompt
        prompt = self._build_review_prompt(context)

        # Call LLM for review
        try:
            messages = [{"role": "system", "content": CRITIC_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

            # Try structured output first
            if hasattr(self.llm, "ask_structured"):
                try:
                    review = await self.llm.ask_structured(messages=messages, response_model=CriticReview)
                    review.review_type = review_type
                    self._record_review(review)
                    return review
                except Exception as e:
                    logger.warning(f"Structured critic review failed: {e}")

            # Fallback to JSON parsing
            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            # Normalize verdict
            verdict_str = parsed.get("verdict", "approve").lower()
            if verdict_str == "approve":
                verdict = CriticVerdict.APPROVE
            elif verdict_str == "reject":
                verdict = CriticVerdict.REJECT
            else:
                verdict = CriticVerdict.REVISE

            review = CriticReview(
                verdict=verdict,
                confidence=float(parsed.get("confidence", 0.8)),
                issues=parsed.get("issues", []),
                suggestions=parsed.get("suggestions", []),
                summary=parsed.get("summary", "Review completed"),
                review_type=review_type,
            )

            self._record_review(review)
            return review

        except Exception as e:
            logger.error(f"Critic review failed: {e}")
            # On error, approve with low confidence (fail-open)
            return CriticReview(
                verdict=CriticVerdict.APPROVE, confidence=0.5, summary=f"Review error (fail-open): {e!s}"
            )

    def _build_review_prompt(self, context: ReviewContext) -> str:
        """Build the appropriate review prompt based on context."""
        if context.review_type == ReviewType.CODE:
            return REVIEW_CODE_PROMPT.format(
                user_request=context.user_request,
                language=context.language or "code",
                code=context.output,
                context=context.task_context or "No additional context",
            )
        if context.review_type == ReviewType.RESEARCH:
            sources_text = "\n".join(f"- {s}" for s in context.sources) if context.sources else "No sources provided"
            return REVIEW_RESEARCH_PROMPT.format(
                user_request=context.user_request, output=context.output, sources=sources_text
            )
        files_text = "\n".join(f"- {f}" for f in context.files) if context.files else "No files"
        return REVIEW_OUTPUT_PROMPT.format(
            user_request=context.user_request,
            task_context=context.task_context or "No additional context",
            output=context.output,
            files=files_text,
        )

    async def get_revision_guidance(self, original_output: str, review: CriticReview) -> str:
        """Get detailed guidance for revising output based on review.

        Args:
            original_output: The original output that was reviewed
            review: The critic's review

        Returns:
            Revision prompt with specific guidance
        """
        issues_text = "\n".join(f"- {issue}" for issue in review.issues)
        suggestions_text = "\n".join(f"- {sug}" for sug in review.suggestions)

        return REVISION_PROMPT.format(
            original_output=original_output,
            verdict=review.verdict.value,
            issues=issues_text or "No specific issues identified",
            suggestions=suggestions_text or "No specific suggestions",
            summary=review.summary,
        )

    async def review_and_revise(
        self, user_request: str, output: str, revision_handler, task_context: str = "", max_attempts: int | None = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Review output and iterate through revisions if needed.

        This is the main entry point for self-correction loops.

        Args:
            user_request: Original user request
            output: Generated output to review
            revision_handler: Async function to revise output given guidance
            task_context: Additional context
            max_attempts: Override default max revision attempts

        Yields:
            Events from the review/revision process
        """
        max_attempts = max_attempts or self.config.max_revision_attempts
        current_output = output
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            self._revision_count += 1

            # Review current output
            review = await self.review_output(
                user_request=user_request, output=current_output, task_context=task_context
            )

            logger.info(
                f"Critic review (attempt {attempt}): {review.verdict.value} (confidence: {review.confidence:.2f})"
            )

            # If approved or rejected, we're done
            if review.verdict == CriticVerdict.APPROVE:
                yield MessageEvent(message=f"Output approved by critic (confidence: {review.confidence:.2f})")
                return

            if review.verdict == CriticVerdict.REJECT:
                yield MessageEvent(message=f"Output rejected by critic: {review.summary}")
                return

            # Need revision
            if attempt >= max_attempts:
                logger.warning(f"Max revision attempts ({max_attempts}) reached, accepting output")
                yield MessageEvent(message=f"Max revisions reached, accepting output with issues: {review.summary}")
                return

            # Get revision guidance
            guidance = await self.get_revision_guidance(current_output, review)

            # Yield progress event
            yield MessageEvent(message=f"Revision needed (attempt {attempt}/{max_attempts}): {review.summary}")

            # Call revision handler
            try:
                current_output = await revision_handler(guidance)
            except Exception as e:
                logger.error(f"Revision handler failed: {e}")
                yield MessageEvent(message=f"Revision failed: {e!s}")
                return

    def _record_review(self, review: CriticReview) -> None:
        """Record a review for history/analytics."""
        self._review_history.append(review)
        # Keep last 100 reviews
        if len(self._review_history) > 100:
            self._review_history = self._review_history[-50:]

    def get_review_stats(self) -> dict[str, Any]:
        """Get statistics about critic reviews."""
        if not self._review_history:
            return {"total_reviews": 0}

        verdicts = [r.verdict.value for r in self._review_history]
        confidences = [r.confidence for r in self._review_history]

        return {
            "total_reviews": len(self._review_history),
            "total_revisions": self._revision_count,
            "verdict_breakdown": {
                "approve": verdicts.count("approve"),
                "revise": verdicts.count("revise"),
                "reject": verdicts.count("reject"),
            },
            "average_confidence": sum(confidences) / len(confidences),
            "issues_found": sum(len(r.issues) for r in self._review_history),
        }

    def reset_stats(self) -> None:
        """Reset review statistics."""
        self._review_history = []
        self._revision_count = 0

    async def fact_check(
        self, output: str, task_context: str = "", source_attributions: list[SourceAttribution] | None = None
    ) -> FactCheckResult:
        """Perform pre-delivery fact checking to detect potential hallucinations.

        This is a lightweight check focused on identifying claims that may be
        hallucinated and providing recommendations for delivery.

        Enhanced with:
        - Content hallucination detection for engagement metrics
        - Source attribution validation
        - Cross-referencing claims against verified sources

        Args:
            output: The output to fact-check
            task_context: Context about what the task was
            source_attributions: Optional list of source attributions for cross-referencing

        Returns:
            FactCheckResult with analysis and recommendations
        """
        if not self.config.enabled:
            return FactCheckResult(confidence_score=1.0, recommendation=FactCheckRecommendation.DELIVER)

        # Skip for very short outputs
        if len(output) < 100:
            return FactCheckResult(confidence_score=0.95, recommendation=FactCheckRecommendation.DELIVER)

        red_flags: list[str] = []
        caveats_to_add: list[str] = []

        # Step 1: Run hallucination pattern detection
        verified_claims = set()
        if source_attributions:
            verified_claims = {attr.claim for attr in source_attributions if attr.is_verified()}

        hallucination_result = self._hallucination_detector.analyze(output, verified_claims)

        if hallucination_result.has_high_risk_patterns:
            for issue in hallucination_result.issues:
                red_flags.append(f"{issue.description}: '{issue.matched_text[:50]}'")
            logger.warning(f"Hallucination detection: {hallucination_result.high_risk_count} high-risk patterns found")

        # Step 2: Check source attribution quality
        if source_attributions:
            summary = AttributionSummary()
            for attr in source_attributions:
                summary.add_attribution(attr)

            if summary.needs_caveats():
                if summary.has_paywall_sources:
                    caveats_to_add.append("Some sources were behind paywalls; information may be incomplete")
                if summary.inferred_claims > summary.verified_claims:
                    caveats_to_add.append("Some information is inferred from context, not directly stated")
                if summary.average_confidence < 0.7:
                    caveats_to_add.append("Source verification confidence is below threshold")

        # Step 3: Determine initial recommendation based on pattern detection
        if hallucination_result.high_risk_count > 2:
            # Multiple high-risk patterns - needs verification
            initial_recommendation = FactCheckRecommendation.NEEDS_VERIFICATION
            initial_confidence = 0.4
        elif hallucination_result.high_risk_count > 0:
            # Some high-risk patterns - add caveats
            initial_recommendation = FactCheckRecommendation.ADD_CAVEATS
            initial_confidence = 0.6
        elif hallucination_result.medium_risk_count > 3:
            # Multiple medium-risk patterns
            initial_recommendation = FactCheckRecommendation.ADD_CAVEATS
            initial_confidence = 0.7
        else:
            initial_recommendation = FactCheckRecommendation.DELIVER
            initial_confidence = 0.9

        try:
            prompt = FACT_CHECK_PROMPT.format(output=output, task_context=task_context or "No additional context")

            # Add hallucination context to prompt if issues found
            if hallucination_result.issues:
                hallucination_summary = self._hallucination_detector.get_risk_summary(hallucination_result)
                prompt += f"\n\nAutomated Pattern Detection Results:\n{hallucination_summary}"

            messages = [{"role": "system", "content": CRITIC_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

            # Try structured output
            if hasattr(self.llm, "ask_structured"):
                try:
                    result = await self.llm.ask_structured(messages=messages, response_model=FactCheckResult)
                    # Merge in our pattern detection results
                    result.red_flags.extend(red_flags)
                    result.caveats_to_add.extend(caveats_to_add)

                    # Adjust recommendation if pattern detection found issues
                    if hallucination_result.has_high_risk_patterns:
                        if result.recommendation == FactCheckRecommendation.DELIVER:
                            result.recommendation = initial_recommendation
                        result.confidence_score = min(result.confidence_score, initial_confidence)

                    logger.info(
                        f"Fact check: {result.claims_analyzed} claims, "
                        f"{result.verified} verified, "
                        f"{hallucination_result.high_risk_count} hallucination risks, "
                        f"recommendation: {result.recommendation.value}"
                    )
                    return result
                except Exception as e:
                    logger.warning(f"Structured fact check failed: {e}")

            # Fallback to JSON parsing
            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            # Normalize recommendation
            rec_str = parsed.get("recommendation", "deliver").lower()
            rec_map = {
                "deliver": FactCheckRecommendation.DELIVER,
                "add_caveats": FactCheckRecommendation.ADD_CAVEATS,
                "needs_verification": FactCheckRecommendation.NEEDS_VERIFICATION,
                "reject": FactCheckRecommendation.REJECT,
            }

            llm_recommendation = rec_map.get(rec_str, FactCheckRecommendation.DELIVER)

            # Use stricter of LLM vs pattern detection recommendation
            if hallucination_result.has_high_risk_patterns:
                if initial_recommendation == FactCheckRecommendation.NEEDS_VERIFICATION:
                    final_recommendation = FactCheckRecommendation.NEEDS_VERIFICATION
                elif llm_recommendation == FactCheckRecommendation.DELIVER:
                    final_recommendation = initial_recommendation
                else:
                    final_recommendation = llm_recommendation
            else:
                final_recommendation = llm_recommendation

            # Merge red flags and caveats
            all_red_flags = parsed.get("red_flags", []) + red_flags
            all_caveats = parsed.get("caveats_to_add", []) + caveats_to_add

            return FactCheckResult(
                claims_analyzed=int(parsed.get("claims_analyzed", 0)),
                verified=int(parsed.get("verified", 0)),
                unverified=int(parsed.get("unverified", 0)) + hallucination_result.high_risk_count,
                contradicted=int(parsed.get("contradicted", 0)),
                red_flags=all_red_flags,
                confidence_score=min(float(parsed.get("confidence_score", 0.8)), initial_confidence),
                recommendation=final_recommendation,
                caveats_to_add=all_caveats,
            )

        except Exception as e:
            logger.error(f"Fact check failed: {e}")
            # Fail-open but include pattern detection results
            return FactCheckResult(
                confidence_score=initial_confidence,
                recommendation=initial_recommendation,
                red_flags=[*red_flags, f"Fact check error: {e!s}"],
                caveats_to_add=caveats_to_add,
            )

    def detect_content_hallucinations(self, output: str) -> HallucinationAnalysisResult:
        """Run standalone hallucination detection on output.

        Useful for quick validation without full LLM fact-checking.

        Args:
            output: Text to analyze

        Returns:
            HallucinationAnalysisResult with detected issues
        """
        return self._hallucination_detector.analyze(output)

    def extract_quantitative_claims(self, output: str) -> list[str]:
        """Extract quantitative claims from output for verification.

        Args:
            output: Text to extract claims from

        Returns:
            List of quantitative claim strings
        """
        return self._hallucination_detector.extract_quantitative_claims(output)

    async def get_structured_feedback(
        self, output: str, user_request: str, focus_areas: list[str] | None = None
    ) -> StructuredFeedback:
        """Get detailed structured feedback with actionable improvements.

        Unlike review_output which gives a verdict, this provides granular
        feedback that can be used for iterative improvement.

        Args:
            output: The output to analyze
            user_request: The original user request
            focus_areas: Specific areas to focus on (optional)

        Returns:
            StructuredFeedback with detailed improvements
        """
        default_focus = ["accuracy", "completeness", "clarity", "relevance"]
        focus = focus_areas or default_focus

        try:
            prompt = STRUCTURED_FEEDBACK_PROMPT.format(
                output=output, user_request=user_request, focus_areas=", ".join(focus)
            )

            messages = [{"role": "system", "content": CRITIC_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

            # Try structured output
            if hasattr(self.llm, "ask_structured"):
                try:
                    return await self.llm.ask_structured(messages=messages, response_model=StructuredFeedback)
                except Exception as e:
                    logger.warning(f"Structured feedback failed: {e}")

            # Fallback to JSON parsing
            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            # Parse improvements
            improvements = []
            for imp in parsed.get("improvements", []):
                improvements.append(
                    StructuredImprovement(
                        category=imp.get("category", "general"),
                        severity=imp.get("severity", "minor"),
                        issue=imp.get("issue", ""),
                        fix=imp.get("fix", ""),
                        location=imp.get("location"),
                    )
                )

            return StructuredFeedback(
                overall_quality=float(parsed.get("overall_quality", 0.7)),
                strengths=parsed.get("strengths", []),
                improvements=improvements,
                missing_elements=parsed.get("missing_elements", []),
                priority_order=parsed.get("priority_order", []),
            )

        except Exception as e:
            logger.error(f"Structured feedback failed: {e}")
            return StructuredFeedback(overall_quality=0.7, strengths=["Unable to analyze"], improvements=[])

    async def quick_validate(
        self, output: str, user_request: str, expected_format: str = "any", required_elements: list[str] | None = None
    ) -> bool:
        """Perform a quick validation check.

        This is faster than full review and checks only basic requirements.

        Args:
            output: The output to validate
            user_request: The original request
            expected_format: Expected format (e.g., "markdown", "json", "code")
            required_elements: List of elements that must be present

        Returns:
            True if output passes basic validation
        """
        if not self.config.enabled:
            return True

        required = required_elements or []

        try:
            prompt = QUICK_VALIDATE_PROMPT.format(
                output=output[:2000],  # Truncate for speed
                user_request=user_request,
                expected_format=expected_format,
                required_elements=", ".join(required) if required else "None specified",
            )

            response = await self.llm.ask(
                messages=[
                    {"role": "system", "content": "You are a quick validator. Respond only with JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            passes = parsed.get("passes_validation", True)
            if not passes:
                logger.debug(f"Quick validation failed: {parsed.get('quick_fix', 'Unknown issue')}")

            return passes

        except Exception as e:
            logger.warning(f"Quick validation error (passing): {e}")
            return True  # Fail-open

    async def run_five_checks(
        self,
        output: str,
        user_request: str,
        sources_context: str | None = None,
        # Phase 5 Enhancement: Pre-verification data injection
        provenance_store: ProvenanceStore | None = None,
        url_verification_results: BatchURLVerificationResult | None = None,
        grounding_result: EnhancedGroundingResult | None = None,
    ) -> FiveCheckResult:
        """Run the comprehensive 5-check framework on output.

        The 5-check framework validates:
        1. Factual Accuracy - Are claims verifiable?
        2. Completeness - Does output address the full request?
        3. Consistency - Is output internally consistent?
        4. Data Symmetry - Are comparisons using equivalent metrics?
        5. Grounding - Is output grounded in sources?

        Phase 5 Enhancement: Now accepts pre-computed verification data from:
        - URL verification service (checks if cited URLs exist and were visited)
        - Claim provenance (links claims to source evidence)
        - Enhanced grounding validation (numeric and entity verification)

        This is particularly important for research outputs and comparisons
        where data asymmetry (e.g., "Model A: 92% MMLU" vs "Model B: Strong performance")
        can produce misleading results.

        Args:
            output: The output to check
            user_request: Original user request
            sources_context: Optional context about sources used
            provenance_store: Optional claim provenance data
            url_verification_results: Optional URL verification results
            grounding_result: Optional enhanced grounding validation result

        Returns:
            FiveCheckResult with detailed check results
        """
        if not self.config.enabled:
            # Return all-pass result if critic is disabled
            pass_result = CheckResult(check_name="disabled", passed=True, severity=CheckSeverity.PASS)
            return FiveCheckResult(
                accuracy_check=pass_result,
                completeness_check=pass_result,
                consistency_check=pass_result,
                symmetry_check=pass_result,
                grounding_check=pass_result,
                overall_passed=True,
                overall_confidence=1.0,
            )

        # Skip for very short outputs
        if len(output) < 100:
            logger.debug("5-check: Skipping for short output")
            pass_result = CheckResult(check_name="auto_pass", passed=True, severity=CheckSeverity.PASS)
            return FiveCheckResult(
                accuracy_check=pass_result,
                completeness_check=pass_result,
                consistency_check=pass_result,
                symmetry_check=pass_result,
                grounding_check=pass_result,
                overall_passed=True,
                overall_confidence=0.95,
            )

        try:
            # Run pre-check for comparison detection
            is_comparison = self._detect_comparison_content(output, user_request)
            if is_comparison:
                logger.info("5-check: Comparison content detected, applying strict symmetry checks")

            # Phase 5: Format pre-verification issues
            pre_verification_issues = self._format_pre_verification_issues(
                provenance_store=provenance_store,
                url_verification_results=url_verification_results,
                grounding_result=grounding_result,
            )

            if pre_verification_issues and pre_verification_issues != "No pre-verification issues detected.":
                logger.info("5-check: Injecting pre-verification issues into prompt")

            # Build prompt
            prompt = FIVE_CHECK_PROMPT.format(
                output=output[:6000],  # Truncate for token limits
                user_request=user_request,
                sources_context=sources_context or "No specific source context provided",
                pre_verification_issues=pre_verification_issues,
            )

            messages = [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            # Try structured output first
            if hasattr(self.llm, "ask_structured"):
                try:
                    result = await self.llm.ask_structured(messages=messages, response_model=FiveCheckResult)

                    # Log summary
                    logger.info(f"5-check result: {result.get_summary()}")
                    if result.asymmetry_issues:
                        logger.warning(f"5-check: Found {len(result.asymmetry_issues)} data asymmetry issues")
                        for issue in result.asymmetry_issues[:3]:
                            logger.warning(
                                f"  - Asymmetry: {issue.item_a} ({issue.item_a_metric_type}) vs "
                                f"{issue.item_b} ({issue.item_b_metric_type})"
                            )

                    return result
                except Exception as e:
                    logger.warning(f"Structured 5-check failed: {e}")

            # Fallback to JSON parsing
            response = await self.llm.ask(messages=messages, response_format={"type": "json_object"})
            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            # Parse individual check results
            def parse_check(data: dict, name: str) -> CheckResult:
                severity_str = data.get("severity", "pass").lower()
                severity_map = {
                    "critical": CheckSeverity.CRITICAL,
                    "major": CheckSeverity.MAJOR,
                    "minor": CheckSeverity.MINOR,
                    "pass": CheckSeverity.PASS,
                }
                return CheckResult(
                    check_name=name,
                    passed=data.get("passed", True),
                    severity=severity_map.get(severity_str, CheckSeverity.PASS),
                    issues=data.get("issues", []),
                    confidence=float(data.get("confidence", 0.8)),
                    remediation=data.get("remediation"),
                )

            # Parse asymmetry issues
            asymmetry_issues = []
            for issue_data in parsed.get("asymmetry_issues", []):
                try:
                    asymmetry_issues.append(
                        DataAsymmetryIssue(
                            item_a=issue_data.get("item_a", ""),
                            item_a_metric_type=issue_data.get("item_a_metric_type", "unknown"),
                            item_b=issue_data.get("item_b", ""),
                            item_b_metric_type=issue_data.get("item_b_metric_type", "unknown"),
                            context=issue_data.get("context", ""),
                            suggestion=issue_data.get("suggestion", ""),
                        )
                    )
                except Exception:
                    continue

            result = FiveCheckResult(
                accuracy_check=parse_check(parsed.get("accuracy_check", {}), "accuracy"),
                completeness_check=parse_check(parsed.get("completeness_check", {}), "completeness"),
                consistency_check=parse_check(parsed.get("consistency_check", {}), "consistency"),
                symmetry_check=parse_check(parsed.get("symmetry_check", {}), "symmetry"),
                grounding_check=parse_check(parsed.get("grounding_check", {}), "grounding"),
                overall_passed=parsed.get("overall_passed", True),
                overall_confidence=float(parsed.get("overall_confidence", 0.8)),
                critical_issues=parsed.get("critical_issues", []),
                asymmetry_issues=asymmetry_issues,
            )

            logger.info(f"5-check result: {result.get_summary()}")
            return result

        except Exception as e:
            logger.error(f"5-check failed: {e}")
            # Fail-open with low confidence
            fail_result = CheckResult(
                check_name="error",
                passed=True,
                severity=CheckSeverity.PASS,
                confidence=0.5,
            )
            return FiveCheckResult(
                accuracy_check=fail_result,
                completeness_check=fail_result,
                consistency_check=fail_result,
                symmetry_check=fail_result,
                grounding_check=fail_result,
                overall_passed=True,
                overall_confidence=0.5,
                critical_issues=[f"5-check error (fail-open): {e}"],
            )

    def _detect_comparison_content(self, output: str, user_request: str) -> bool:
        """Detect if content involves comparisons that need symmetry checking.

        Args:
            output: The output content
            user_request: Original request

        Returns:
            True if comparison content is detected
        """
        comparison_indicators = [
            "compare",
            "comparison",
            "versus",
            " vs ",
            " vs.",
            "vs ",
            "better than",
            "worse than",
            "difference between",
            "ranking",
            "ranked",
            "top ",
            "best ",
            "which is",
            "pros and cons",
            "advantages",
            "disadvantages",
        ]

        # Table indicators (comparisons often use tables)
        table_patterns = ["|", "---", "|-", "-|"]

        text = (output + " " + user_request).lower()

        has_comparison_words = any(ind in text for ind in comparison_indicators)
        has_tables = any(pat in output for pat in table_patterns)

        return has_comparison_words or has_tables

    def _format_pre_verification_issues(
        self,
        provenance_store: ProvenanceStore | None = None,
        url_verification_results: BatchURLVerificationResult | None = None,
        grounding_result: EnhancedGroundingResult | None = None,
    ) -> str:
        """Format pre-verification issues for injection into 5-check prompt.

        Phase 5 Enhancement: Aggregates issues from automated verification systems
        to provide factual data to the LLM critic, not just opinions.

        Args:
            provenance_store: Claim provenance data
            url_verification_results: URL verification results
            grounding_result: Enhanced grounding validation result

        Returns:
            Formatted string of pre-verification issues
        """
        issues = []

        # URL Verification Issues
        if url_verification_results:
            if url_verification_results.not_found_count > 0:
                issues.append("### URL Verification Failures")
                issues.append(f"**{url_verification_results.not_found_count} cited URLs do not exist:**")
                for url, result in url_verification_results.results.items():
                    if result.status == URLVerificationStatus.NOT_FOUND:
                        issues.append(f"  - FABRICATED URL: {url} (HTTP {result.http_status or 'N/A'})")

            if url_verification_results.placeholder_count > 0:
                issues.append(f"**{url_verification_results.placeholder_count} placeholder URLs detected:**")
                for url, result in url_verification_results.results.items():
                    if result.status == URLVerificationStatus.PLACEHOLDER:
                        issues.append(f"  - PLACEHOLDER: {url}")

            if url_verification_results.not_visited_count > 0:
                issues.append(f"**{url_verification_results.not_visited_count} URLs exist but were never visited:**")
                for url, result in url_verification_results.results.items():
                    if result.status == URLVerificationStatus.EXISTS_NOT_VISITED:
                        issues.append(f"  - NOT VISITED: {url}")

        # Claim Provenance Issues
        if provenance_store:
            fabricated = provenance_store.get_fabricated_claims()
            if fabricated:
                issues.append("### Fabricated Claims (No Source Found)")
                issues.append(f"**{len(fabricated)} claims have no source evidence:**")
                for claim in fabricated[:10]:  # Limit to 10
                    issues.append(f'  - FABRICATED: "{claim.claim_text[:80]}..."')

            unverified = provenance_store.get_unverified_claims()
            if unverified:
                issues.append(f"**{len(unverified)} claims could not be verified:**")
                for claim in unverified[:5]:  # Limit to 5
                    issues.append(f'  - UNVERIFIED: "{claim.claim_text[:60]}..."')

        # Enhanced Grounding Issues
        if grounding_result:
            if grounding_result.fabricated_numeric_claims:
                issues.append("### Fabricated Numeric Claims")
                issues.append(f"**{len(grounding_result.fabricated_numeric_claims)} numbers not found in any source:**")
                for claim in grounding_result.fabricated_numeric_claims[:10]:
                    issues.append(f"  - FABRICATED METRIC: {claim}")

            if grounding_result.fabricated_entity_claims:
                issues.append("### Unverified Entity Claims")
                issues.append(f"**{len(grounding_result.fabricated_entity_claims)} entity claims not in sources:**")
                for claim in grounding_result.fabricated_entity_claims[:10]:
                    issues.append(f"  - UNVERIFIED ENTITY: {claim}")

        if not issues:
            return "No pre-verification issues detected."

        return "\n".join(issues)

    async def detect_data_asymmetry(self, output: str) -> list[DataAsymmetryIssue]:
        """Quick detection of data asymmetry issues without full 5-check.

        This is a lightweight check specifically for comparison content.
        Use run_five_checks for comprehensive validation.

        Args:
            output: Text to analyze for asymmetry

        Returns:
            List of detected asymmetry issues
        """
        import re

        issues = []

        # Extract comparison-like structures (simple heuristic)
        # Look for patterns like "Item: value" in proximity

        # Pattern 1: "Name: Number%" vs "Name: Qualitative"
        metric_pattern = r"([A-Z][a-zA-Z0-9\s]+?):\s*(\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:ms|s|MB|GB|K|M)?)"
        qualitative_pattern = r"([A-Z][a-zA-Z0-9\s]+?):\s*([A-Z][a-z]+(?:\s+[a-z]+){0,3}(?:capabilities|performance|support|features|handling)?)"

        metrics = re.findall(metric_pattern, output)
        qualitatives = re.findall(qualitative_pattern, output)

        # Check for asymmetry (items with metrics vs items with only qualitative)
        metric_items = {m[0].strip().lower() for m in metrics}
        qual_items = {q[0].strip().lower() for q in qualitatives}

        # Items that only have qualitative descriptions but similar items have metrics
        asymmetric = qual_items - metric_items

        if asymmetric and metric_items:
            # There's potential asymmetry
            for qual in qualitatives:
                item_name = qual[0].strip()
                if item_name.lower() in asymmetric:
                    # Find a metric item to compare
                    metric_example = next(iter(metrics), ("Example", "X%"))
                    issues.append(
                        DataAsymmetryIssue(
                            item_a=metric_example[0],
                            item_a_metric_type="quantitative",
                            item_b=item_name,
                            item_b_metric_type="qualitative",
                            context=f"{item_name}: {qual[1]}",
                            suggestion=f"Provide equivalent metric for {item_name} or explicitly note data unavailable",
                        )
                    )

        return issues[:5]  # Limit to 5 issues
