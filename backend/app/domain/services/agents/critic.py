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
from enum import Enum
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
from pydantic import BaseModel, Field

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser
from app.domain.services.prompts.critic import (
    CRITIC_SYSTEM_PROMPT,
    REVIEW_OUTPUT_PROMPT,
    REVIEW_CODE_PROMPT,
    REVIEW_RESEARCH_PROMPT,
    REVISION_PROMPT,
)
from app.domain.models.event import BaseEvent, MessageEvent


logger = logging.getLogger(__name__)


class CriticVerdict(str, Enum):
    """Possible verdicts from the critic review."""
    APPROVE = "approve"  # Output is good, deliver as-is
    REVISE = "revise"    # Output needs improvements
    REJECT = "reject"    # Output is fundamentally flawed, needs full redo


class ReviewType(str, Enum):
    """Type of content being reviewed."""
    GENERAL = "general"
    CODE = "code"
    RESEARCH = "research"


class CriticReview(BaseModel):
    """Structured review from the CriticAgent."""
    verdict: CriticVerdict = Field(description="Review verdict")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in verdict")
    issues: List[str] = Field(default_factory=list, description="Identified issues")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")
    summary: str = Field(description="Brief explanation of the verdict")
    review_type: ReviewType = Field(default=ReviewType.GENERAL, description="Type of review performed")


class CriticConfig(BaseModel):
    """Configuration for critic behavior."""
    enabled: bool = Field(default=True, description="Whether critic is active")
    min_confidence_threshold: float = Field(
        default=0.7,
        description="Minimum confidence to accept a verdict"
    )
    max_revision_attempts: int = Field(
        default=2,
        description="Maximum revision attempts before accepting"
    )
    auto_approve_simple_tasks: bool = Field(
        default=True,
        description="Skip review for simple tasks"
    )
    review_code_security: bool = Field(
        default=True,
        description="Always review code for security issues"
    )


@dataclass
class ReviewContext:
    """Context for a review operation."""
    user_request: str
    output: str
    task_context: str = ""
    files: List[str] = None
    sources: List[str] = None
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

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        config: Optional[CriticConfig] = None
    ):
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
        self._review_history: List[CriticReview] = []
        self._revision_count: int = 0

    def _detect_review_type(self, output: str, task_context: str) -> ReviewType:
        """Automatically detect the type of content being reviewed."""
        output_lower = output.lower()
        context_lower = task_context.lower()

        # Code indicators
        code_indicators = [
            'def ', 'function ', 'class ', 'import ', 'const ', 'let ', 'var ',
            '```python', '```javascript', '```typescript', '```java',
            'public static', 'private ', '#include', 'package '
        ]
        if any(indicator in output_lower for indicator in code_indicators):
            return ReviewType.CODE

        # Research indicators
        research_indicators = [
            'according to', 'research shows', 'studies indicate',
            'source:', 'reference:', 'citation', 'findings suggest'
        ]
        if any(indicator in output_lower for indicator in research_indicators):
            return ReviewType.RESEARCH

        if any(term in context_lower for term in ['research', 'investigate', 'find information']):
            return ReviewType.RESEARCH

        return ReviewType.GENERAL

    def _detect_code_language(self, output: str) -> str:
        """Detect programming language from code output."""
        if '```python' in output or 'def ' in output:
            return 'python'
        if '```javascript' in output or 'function ' in output:
            return 'javascript'
        if '```typescript' in output or 'interface ' in output:
            return 'typescript'
        if '```java' in output or 'public class ' in output:
            return 'java'
        if '```go' in output or 'func ' in output:
            return 'go'
        if '```rust' in output or 'fn ' in output:
            return 'rust'
        return 'unknown'

    def _should_skip_review(self, output: str, task_context: str) -> bool:
        """Determine if review should be skipped for simple tasks."""
        if not self.config.auto_approve_simple_tasks:
            return False

        # Skip for very short outputs (likely simple acknowledgments)
        if len(output) < 100:
            return True

        # Skip for simple confirmations
        simple_patterns = [
            'done', 'completed', 'created', 'updated',
            'file saved', 'task complete'
        ]
        output_lower = output.lower()
        if any(pattern in output_lower for pattern in simple_patterns):
            if len(output) < 500:
                return True

        return False

    async def review_output(
        self,
        user_request: str,
        output: str,
        task_context: str = "",
        files: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        force_review_type: Optional[ReviewType] = None
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
                verdict=CriticVerdict.APPROVE,
                confidence=1.0,
                summary="Critic disabled - auto-approved"
            )

        # Check if we should skip review
        if self._should_skip_review(output, task_context):
            logger.debug("Simple task detected, skipping critic review")
            return CriticReview(
                verdict=CriticVerdict.APPROVE,
                confidence=0.95,
                summary="Simple task - auto-approved"
            )

        # Detect review type
        review_type = force_review_type or self._detect_review_type(output, task_context)
        logger.info(f"Critic reviewing output (type: {review_type.value})")

        # Build review context
        context = ReviewContext(
            user_request=user_request,
            output=output,
            task_context=task_context,
            files=files or [],
            sources=sources or [],
            review_type=review_type,
            language=self._detect_code_language(output) if review_type == ReviewType.CODE else ""
        )

        # Get the appropriate prompt
        prompt = self._build_review_prompt(context)

        # Call LLM for review
        try:
            messages = [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]

            # Try structured output first
            if hasattr(self.llm, 'ask_structured'):
                try:
                    review = await self.llm.ask_structured(
                        messages=messages,
                        response_model=CriticReview
                    )
                    review.review_type = review_type
                    self._record_review(review)
                    return review
                except Exception as e:
                    logger.warning(f"Structured critic review failed: {e}")

            # Fallback to JSON parsing
            response = await self.llm.ask(
                messages=messages,
                response_format={"type": "json_object"}
            )

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
                review_type=review_type
            )

            self._record_review(review)
            return review

        except Exception as e:
            logger.error(f"Critic review failed: {e}")
            # On error, approve with low confidence (fail-open)
            return CriticReview(
                verdict=CriticVerdict.APPROVE,
                confidence=0.5,
                summary=f"Review error (fail-open): {str(e)}"
            )

    def _build_review_prompt(self, context: ReviewContext) -> str:
        """Build the appropriate review prompt based on context."""
        if context.review_type == ReviewType.CODE:
            return REVIEW_CODE_PROMPT.format(
                user_request=context.user_request,
                language=context.language or "code",
                code=context.output,
                context=context.task_context or "No additional context"
            )
        elif context.review_type == ReviewType.RESEARCH:
            sources_text = "\n".join(f"- {s}" for s in context.sources) if context.sources else "No sources provided"
            return REVIEW_RESEARCH_PROMPT.format(
                user_request=context.user_request,
                output=context.output,
                sources=sources_text
            )
        else:
            files_text = "\n".join(f"- {f}" for f in context.files) if context.files else "No files"
            return REVIEW_OUTPUT_PROMPT.format(
                user_request=context.user_request,
                task_context=context.task_context or "No additional context",
                output=context.output,
                files=files_text
            )

    async def get_revision_guidance(
        self,
        original_output: str,
        review: CriticReview
    ) -> str:
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
            summary=review.summary
        )

    async def review_and_revise(
        self,
        user_request: str,
        output: str,
        revision_handler,
        task_context: str = "",
        max_attempts: Optional[int] = None
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
                user_request=user_request,
                output=current_output,
                task_context=task_context
            )

            logger.info(
                f"Critic review (attempt {attempt}): {review.verdict.value} "
                f"(confidence: {review.confidence:.2f})"
            )

            # If approved or rejected, we're done
            if review.verdict == CriticVerdict.APPROVE:
                yield MessageEvent(
                    message=f"Output approved by critic (confidence: {review.confidence:.2f})"
                )
                return

            if review.verdict == CriticVerdict.REJECT:
                yield MessageEvent(
                    message=f"Output rejected by critic: {review.summary}"
                )
                return

            # Need revision
            if attempt >= max_attempts:
                logger.warning(
                    f"Max revision attempts ({max_attempts}) reached, accepting output"
                )
                yield MessageEvent(
                    message=f"Max revisions reached, accepting output with issues: {review.summary}"
                )
                return

            # Get revision guidance
            guidance = await self.get_revision_guidance(current_output, review)

            # Yield progress event
            yield MessageEvent(
                message=f"Revision needed (attempt {attempt}/{max_attempts}): {review.summary}"
            )

            # Call revision handler
            try:
                current_output = await revision_handler(guidance)
            except Exception as e:
                logger.error(f"Revision handler failed: {e}")
                yield MessageEvent(message=f"Revision failed: {str(e)}")
                return

    def _record_review(self, review: CriticReview) -> None:
        """Record a review for history/analytics."""
        self._review_history.append(review)
        # Keep last 100 reviews
        if len(self._review_history) > 100:
            self._review_history = self._review_history[-50:]

    def get_review_stats(self) -> Dict[str, Any]:
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
