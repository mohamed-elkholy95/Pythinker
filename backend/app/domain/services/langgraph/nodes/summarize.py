"""Summarize node for the LangGraph PlanAct workflow.

This node generates the final summary using the ExecutionAgent.
Includes output validation for hallucination detection (logging only, non-blocking).

Phase 4 Enhancement: Integrates Chain-of-Verification (CoVe) for reports
to detect and correct fabricated claims before delivery.

Enhanced CoVe: Verifies claims against actual tool outputs to close the loop
between what the agent claims and what the tools actually returned.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, ClassVar

from app.core.config import get_feature_flags
from app.domain.models.event import DoneEvent, MessageEvent, PlanEvent, PlanStatus
from app.domain.models.plan import ExecutionStatus
from app.domain.models.source_attribution import SourceAttribution
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.chain_of_verification import (
    ChainOfVerification,
    CoVeResult,
)
from app.domain.services.agents.content_hallucination_detector import (
    ContentHallucinationDetector,
)
from app.domain.services.agents.grounding_validator import (
    EnhancedGroundingValidator,
)
from app.domain.services.agents.memory_manager import get_memory_manager
from app.domain.services.langgraph.state import PlanActState

logger = logging.getLogger(__name__)


@dataclass
class ClaimVerificationResult:
    """Result of verifying a claim against tool outputs.

    Attributes:
        claim: The claim being verified
        verified: Whether the claim is supported by tool output
        reason: Explanation of verification result
        confidence: Confidence score from 0 to 1
        source_output: The tool output that supports the claim (if any)
    """

    claim: str
    verified: bool
    reason: str
    confidence: float  # 0 to 1
    source_output: ToolResult[Any] | None = None


class ClaimVerifier:
    """Verifies claims against actual tool outputs.

    This closes the loop between what the agent claims and what
    the tools actually returned, providing ground-truth verification.
    """

    # Keywords that indicate numerical or factual claims
    FACTUAL_INDICATORS = re.compile(
        r"\b(\d+[\d,\.]*%?|\$[\d,\.]+|"
        r"\d{4}[-/]\d{2}[-/]\d{2}|"
        r"\d+(?:\s*(?:MB|GB|KB|ms|seconds?|minutes?|hours?|days?)))\b",
        re.IGNORECASE,
    )

    # Common claim patterns
    CLAIM_PATTERNS: ClassVar[list[str]] = [
        r"found\s+(\d+)\s+",
        r"contains?\s+(\d+)\s+",
        r"returned?\s+(\d+)\s+",
        r"shows?\s+(\d+)\s+",
        r"(\d+)\s+results?",
        r"(\d+)\s+files?",
        r"(\d+)\s+errors?",
        r"(\d+)\s+matches?",
    ]

    def __init__(
        self,
        similarity_threshold: float = 0.5,
        confidence_threshold: float = 0.7,
    ):
        """Initialize the claim verifier.

        Args:
            similarity_threshold: Minimum similarity for content matching (0-1)
            confidence_threshold: Threshold for marking claims as verified (0-1)
        """
        self.similarity_threshold = similarity_threshold
        self.confidence_threshold = confidence_threshold

    async def verify_claims_against_sources(
        self,
        claims: list[str],
        tool_outputs: list[ToolResult[Any]],
    ) -> list[ClaimVerificationResult]:
        """Verify extracted claims against actual tool outputs.

        This closes the loop between what the agent claims and what
        the tools actually returned.

        Args:
            claims: List of claims to verify
            tool_outputs: List of tool results to verify against

        Returns:
            List of verification results for each claim
        """
        results: list[ClaimVerificationResult] = []

        for claim in claims:
            # Find relevant tool outputs for this claim
            relevant_outputs = self._find_relevant_outputs(claim, tool_outputs)

            if not relevant_outputs:
                results.append(
                    ClaimVerificationResult(
                        claim=claim,
                        verified=False,
                        reason="No supporting tool output found",
                        confidence=0.2,
                    )
                )
                continue

            # Check if any output supports the claim
            best_match: ToolResult[Any] | None = None
            best_confidence = 0.0

            for output in relevant_outputs:
                confidence = self._calculate_support_confidence(claim, output)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = output

            # Determine tool name for the reason
            tool_name = "tool"
            if best_match and best_match.data:
                data = best_match.data
                if isinstance(data, dict) and "tool_name" in data:
                    tool_name = str(data["tool_name"])

            results.append(
                ClaimVerificationResult(
                    claim=claim,
                    verified=best_confidence >= self.confidence_threshold,
                    reason=(
                        f"Supported by {tool_name}"
                        if best_match and best_confidence >= self.confidence_threshold
                        else (f"Partial match ({best_confidence:.1%} confidence)" if best_match else "No match")
                    ),
                    confidence=best_confidence,
                    source_output=best_match,
                )
            )

        return results

    def _find_relevant_outputs(
        self,
        claim: str,
        tool_outputs: list[ToolResult[Any]],
    ) -> list[ToolResult[Any]]:
        """Find tool outputs that might support the claim.

        Uses keyword matching and content similarity to find
        potentially relevant outputs.

        Args:
            claim: The claim to find support for
            tool_outputs: All available tool outputs

        Returns:
            List of potentially relevant tool outputs
        """
        relevant: list[ToolResult[Any]] = []
        claim_lower = claim.lower()

        # Extract key terms from the claim
        claim_words = set(re.findall(r"\b\w{3,}\b", claim_lower))

        # Extract numbers from claim for matching
        claim_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", claim))

        for output in tool_outputs:
            # Get content from output
            content = self._extract_content(output)
            if not content:
                continue

            content_lower = content.lower()
            content_words = set(re.findall(r"\b\w{3,}\b", content_lower))

            # Check for keyword overlap
            overlap = claim_words & content_words
            if len(overlap) >= 2:  # At least 2 common words
                relevant.append(output)
                continue

            # Check for number matches (important for factual claims)
            content_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", content))
            if claim_numbers and claim_numbers & content_numbers:
                relevant.append(output)
                continue

            # Check string similarity as fallback
            similarity = SequenceMatcher(None, claim_lower, content_lower[:500]).ratio()
            if similarity >= self.similarity_threshold:
                relevant.append(output)

        return relevant

    def _calculate_support_confidence(
        self,
        claim: str,
        output: ToolResult[Any],
    ) -> float:
        """Calculate how well a tool output supports a claim.

        Uses multiple heuristics:
        - Exact text match in output
        - Number/value verification
        - Semantic similarity

        Args:
            claim: The claim to verify
            output: The tool output to check

        Returns:
            Confidence score from 0.0 to 1.0
        """
        content = self._extract_content(output)
        if not content:
            return 0.0

        confidence = 0.0
        claim_lower = claim.lower()
        content_lower = content.lower()

        # Check for exact or near-exact phrase match
        if claim_lower in content_lower:
            confidence = 0.95
        else:
            # Check if substantial portion of claim appears in content
            claim_words = claim_lower.split()
            matches = sum(1 for word in claim_words if word in content_lower)
            word_match_ratio = matches / len(claim_words) if claim_words else 0
            confidence = max(confidence, word_match_ratio * 0.7)

        # Boost confidence for number verification
        claim_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", claim)
        content_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", content)

        if claim_numbers:
            numbers_verified = sum(1 for n in claim_numbers if n in content_numbers)
            number_ratio = numbers_verified / len(claim_numbers)
            confidence = max(confidence, 0.5 + number_ratio * 0.4)

        # Check for factual indicator patterns
        if self.FACTUAL_INDICATORS.search(claim):
            # This is a factual claim, require stronger evidence
            for pattern in self.CLAIM_PATTERNS:
                claim_match = re.search(pattern, claim_lower)
                content_match = re.search(pattern, content_lower)
                if claim_match and content_match and claim_match.group(1) == content_match.group(1):
                    confidence = max(confidence, 0.9)
                    break

        # Use sequence similarity as additional signal
        similarity = SequenceMatcher(None, claim_lower, content_lower[:1000]).ratio()
        confidence = max(confidence, similarity * 0.6)

        # Ensure output was successful for higher confidence
        if output.success:
            confidence = min(confidence * 1.1, 1.0)
        else:
            confidence *= 0.7

        return min(confidence, 1.0)

    def _extract_content(self, output: ToolResult[Any]) -> str:
        """Extract text content from a tool result.

        Args:
            output: The tool result

        Returns:
            Extracted text content
        """
        parts = []

        if output.message:
            parts.append(output.message)

        if output.data:
            if isinstance(output.data, str):
                parts.append(output.data)
            elif isinstance(output.data, dict):
                # Extract common content fields
                for key in ["content", "text", "output", "result", "body"]:
                    if key in output.data:
                        value = output.data[key]
                        if isinstance(value, str):
                            parts.append(value)
                        elif isinstance(value, list):
                            parts.extend(str(item) for item in value if item)
                # Also include the full dict representation for number matching
                parts.append(str(output.data))
            elif isinstance(output.data, list):
                parts.extend(str(item) for item in output.data if item)

        return " ".join(parts)


# Singleton claim verifier instance
_claim_verifier: ClaimVerifier | None = None


def get_claim_verifier() -> ClaimVerifier:
    """Get or create shared claim verifier."""
    global _claim_verifier
    if _claim_verifier is None:
        _claim_verifier = ClaimVerifier()
    return _claim_verifier


# Singleton hallucination detector for validation
_output_validator: ContentHallucinationDetector | None = None
_enhanced_grounding_validator: EnhancedGroundingValidator | None = None


def get_output_validator() -> ContentHallucinationDetector:
    """Get or create shared output validator."""
    global _output_validator
    if _output_validator is None:
        _output_validator = ContentHallucinationDetector()
    return _output_validator


def get_enhanced_grounding_validator() -> EnhancedGroundingValidator:
    """Get or create shared enhanced grounding validator."""
    global _enhanced_grounding_validator
    if _enhanced_grounding_validator is None:
        _enhanced_grounding_validator = EnhancedGroundingValidator(
            strict_numeric_mode=True,
        )
    return _enhanced_grounding_validator


def _validate_output(output: str, source_attributions: list[SourceAttribution] | None = None) -> dict[str, Any]:
    """Validate output for potential hallucinations (non-blocking).

    This is a logging-only validation that doesn't block delivery.
    Results are logged for monitoring and optionally added to metadata.

    Args:
        output: The summary output to validate
        source_attributions: Optional source attributions for cross-reference

    Returns:
        Validation result dict with issues and flags
    """
    validator = get_output_validator()

    # Get verified claims from attributions
    verified_claims = set()
    if source_attributions:
        verified_claims = {attr.claim for attr in source_attributions if attr.is_verified()}

    # Run hallucination detection
    result = validator.analyze(output, verified_claims)

    validation_result = {
        "passed": not result.has_high_risk_patterns,
        "issues": [],
        "high_risk_count": result.high_risk_count,
        "medium_risk_count": result.medium_risk_count,
    }

    if result.issues:
        validation_result["issues"] = [
            {
                "type": issue.pattern_type,
                "text": issue.matched_text[:100],
                "risk": issue.risk.value,
                "suggestion": issue.suggestion,
            }
            for issue in result.issues[:10]  # Limit to 10 issues
        ]

    return validation_result


async def _run_cove_verification(
    content: str,
    state: PlanActState,
) -> tuple[str, CoVeResult | None]:
    """Run Chain-of-Verification on the content (Phase 4).

    This verifies claims in the content and generates a refined version
    if contradictions are found.

    Args:
        content: The summary content to verify
        state: Current workflow state for LLM access

    Returns:
        Tuple of (possibly refined content, CoVe result or None)
    """
    # Check feature flag
    feature_flags = get_feature_flags()
    if not feature_flags.get("cove_verification", True):
        logger.debug("CoVe verification disabled by feature flag")
        return content, None

    # Get LLM from executor
    executor = state.get("executor")
    if not executor:
        logger.warning("CoVe: No executor available, skipping verification")
        return content, None

    # Check minimum length (short responses don't need CoVe)
    if len(content) < 300:
        logger.debug(f"CoVe: Content too short ({len(content)} chars), skipping")
        return content, None

    try:
        # Import here to get json parser
        from app.domain.utils.json_parser import JsonParser

        json_parser = JsonParser()
        llm = executor._llm  # Access the LLM from executor

        # Create CoVe instance
        cove = ChainOfVerification(
            llm=llm,
            json_parser=json_parser,
            max_questions=5,
            parallel_verification=True,
            min_response_length=200,
        )

        # Run verification
        logger.info("Running Chain-of-Verification on summary content...")
        result = await cove.verify_and_refine(
            query="",  # No specific query context
            response=content,
            skip_if_short=True,
        )

        # Log results
        logger.info(
            f"CoVe completed: {result.claims_verified}/{len(result.verification_questions)} verified, "
            f"{result.claims_contradicted} contradicted, confidence={result.confidence_score:.2f}"
        )

        if result.claims_contradicted > 0:
            logger.warning(f"CoVe detected {result.claims_contradicted} contradicted claims. Using refined response.")
            # Log specific contradictions
            for q in result.verification_questions:
                if q.status.value == "contradicted":
                    logger.warning(f"  CONTRADICTED: {q.claim_being_verified[:80]}...")

        # Return refined content if there were contradictions
        if result.has_contradictions:
            return result.verified_response, result
        return content, result

    except Exception as e:
        logger.error(f"CoVe verification failed (non-blocking): {e}")
        return content, None


def _extract_claims_from_summary(content: str) -> list[str]:
    """Extract verifiable claims from summary content.

    Focuses on factual statements that can be verified against tool outputs:
    - Sentences with numbers, counts, or measurements
    - Sentences with specific named entities
    - Statements about file operations, search results, etc.

    Args:
        content: The summary content

    Returns:
        List of extracted claims
    """
    claims: list[str] = []

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", content)

    # Patterns indicating verifiable claims
    verifiable_patterns = [
        r"\b\d+\s+(?:file|result|error|match|item|record|entry|line)",
        r"\bfound\s+\d+",
        r"\bcreated?\s+\d+",
        r"\bdeleted?\s+\d+",
        r"\bmodified?\s+\d+",
        r"\breturned?\s+\d+",
        r"\bcontains?\s+\d+",
        r"\bshows?\s+\d+",
        r"\b\d+%",
        r"\b\d+\s*(?:MB|GB|KB|bytes?)",
        r"\b\d+\s*(?:ms|seconds?|minutes?)",
    ]

    combined_pattern = "|".join(verifiable_patterns)

    # Keywords that indicate tool-related actions
    tool_keywords = [
        "search result",
        "file content",
        "command output",
        "response",
        "returned",
        "executed",
        "completed",
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Check if sentence contains verifiable information or tool-related keywords
        sentence_lower = sentence.lower()
        has_verifiable_pattern = re.search(combined_pattern, sentence, re.IGNORECASE)
        has_tool_keyword = any(keyword in sentence_lower for keyword in tool_keywords)

        if has_verifiable_pattern or has_tool_keyword:
            claims.append(sentence)

    return claims[:10]  # Limit to 10 claims to avoid excessive verification


async def _run_claim_verification(
    content: str,
    tool_results: list[ToolResult[Any]],
) -> dict[str, Any]:
    """Run claim verification against tool outputs.

    This is the enhanced CoVe that verifies claims against actual
    tool outputs rather than just LLM knowledge.

    Args:
        content: Summary content with claims
        tool_results: Tool results to verify against

    Returns:
        Verification result dictionary
    """
    if not tool_results:
        return {"passed": True, "verified_claims": [], "unverified_claims": []}

    try:
        # Extract claims from content
        claims = _extract_claims_from_summary(content)
        if not claims:
            logger.debug("No verifiable claims extracted from summary")
            return {"passed": True, "verified_claims": [], "unverified_claims": []}

        # Run verification
        verifier = get_claim_verifier()
        results = await verifier.verify_claims_against_sources(claims, tool_results)

        # Categorize results
        verified = [r for r in results if r.verified]
        unverified = [r for r in results if not r.verified]

        # Calculate overall pass/fail
        total = len(results)
        verified_ratio = len(verified) / total if total > 0 else 1.0
        passed = verified_ratio >= 0.5  # Pass if at least half are verified

        # Log results
        if unverified:
            logger.warning(f"Claim verification: {len(verified)}/{total} claims verified, {len(unverified)} unverified")
            for r in unverified[:3]:
                logger.warning(f"  Unverified: {r.claim[:80]}... ({r.reason})")
        else:
            logger.info(f"Claim verification: all {total} claims verified against tool outputs")

        return {
            "passed": passed,
            "verified_claims": [
                {
                    "claim": r.claim,
                    "confidence": r.confidence,
                    "reason": r.reason,
                }
                for r in verified
            ],
            "unverified_claims": [
                {
                    "claim": r.claim,
                    "confidence": r.confidence,
                    "reason": r.reason,
                }
                for r in unverified
            ],
            "verification_ratio": verified_ratio,
        }

    except Exception as e:
        logger.error(f"Claim verification failed: {e}")
        return {"passed": True, "error": str(e)}


def _run_enhanced_grounding_check(
    content: str,
    source_contents: list[str],
) -> dict[str, Any]:
    """Run enhanced grounding validation with numeric verification (Phase 3).

    Args:
        content: Content to validate
        source_contents: List of source content strings

    Returns:
        Grounding validation result
    """
    if not source_contents:
        return {"passed": True, "fabricated_claims": []}

    try:
        validator = get_enhanced_grounding_validator()
        result = validator.validate_against_sources(content, source_contents)

        grounding_result = {
            "passed": not result.has_fabricated_data,
            "overall_score": result.overall_score,
            "level": result.level.value,
            "numeric_verification_rate": result.numeric_verification_rate,
            "entity_verification_rate": result.entity_verification_rate,
            "fabricated_claims": result.fabricated_numeric_claims + result.fabricated_entity_claims,
        }

        if result.has_fabricated_data:
            logger.warning(
                f"Enhanced grounding detected fabricated data: "
                f"{len(result.fabricated_numeric_claims)} numeric, "
                f"{len(result.fabricated_entity_claims)} entity claims"
            )
            for warning in result.get_fabrication_warnings()[:5]:
                logger.warning(f"  {warning}")

        return grounding_result

    except Exception as e:
        logger.error(f"Enhanced grounding check failed: {e}")
        return {"passed": True, "error": str(e)}


async def summarize_node(state: PlanActState) -> dict[str, Any]:
    """Summarize the completed work.

    This node invokes the ExecutionAgent to generate a summary of
    the completed task and emits completion events.

    Includes output validation for hallucination detection (logging only).
    Validation issues are logged for monitoring but don't block delivery.

    Args:
        state: Current workflow state

    Returns:
        State updates with summary events
    """
    executor = state.get("executor")
    plan = state.get("plan")

    if not executor:
        logger.warning("Summarize node: no executor available")
        return {
            "pending_events": [DoneEvent()],
        }

    logger.info("Summarizing completed work")

    # Get event queue for real-time streaming
    event_queue: asyncio.Queue | None = state.get("event_queue")

    pending_events = []
    summary_content = ""

    async for event in executor.summarize():
        # Capture summary content for validation
        if isinstance(event, MessageEvent) and hasattr(event, "message"):
            summary_content = event.message or ""

        if event_queue:
            await event_queue.put(event)
        else:
            pending_events.append(event)

    # Phase 4: Run Chain-of-Verification on summary content
    cove_result = None
    feature_flags = get_feature_flags()

    if summary_content and feature_flags.get("cove_verification", True):
        try:
            refined_content, cove_result = await _run_cove_verification(
                summary_content,
                state,
            )

            # If CoVe refined the content, update the summary
            if cove_result and cove_result.has_contradictions:
                logger.info(f"CoVe refined summary: removed {cove_result.claims_contradicted} contradicted claims")
                summary_content = refined_content

                # Emit updated message event with refined content
                refined_event = MessageEvent(message=refined_content)
                if event_queue:
                    await event_queue.put(refined_event)
                else:
                    pending_events.append(refined_event)

        except Exception as e:
            logger.error(f"CoVe verification error (non-blocking): {e}")

    # Enhanced CoVe: Verify claims against actual tool outputs
    claim_verification_result: dict[str, Any] = {}
    if summary_content and feature_flags.get("claim_verification", True):
        try:
            # Get tool results from state - handle both ToolResult objects and dicts
            tool_results_raw = state.get("tool_results", [])
            tool_results_typed: list[ToolResult[Any]] = []

            for result in tool_results_raw:
                if isinstance(result, ToolResult):
                    tool_results_typed.append(result)
                elif isinstance(result, dict):
                    # Convert dict to ToolResult for verification
                    tool_results_typed.append(
                        ToolResult(
                            success=result.get("success", True),
                            message=result.get("message") or result.get("content"),
                            data=result,
                        )
                    )

            if tool_results_typed:
                claim_verification_result = await _run_claim_verification(
                    summary_content,
                    tool_results_typed,
                )

        except Exception as e:
            logger.error(f"Claim verification error (non-blocking): {e}")

    # Phase 3: Run enhanced grounding validation with numeric verification
    grounding_result = {}
    if summary_content and feature_flags.get("enhanced_grounding", True):
        try:
            # Get source contents from state (tool results, search results)
            source_contents = []
            tool_results = state.get("tool_results", [])
            for result in tool_results:
                if isinstance(result, dict) and result.get("content"):
                    source_contents.append(str(result["content"]))

            # Also get from source attributions
            source_attributions = state.get("source_attributions", [])
            for attr in source_attributions:
                if hasattr(attr, "source_excerpt") and attr.source_excerpt:
                    source_contents.append(attr.source_excerpt)

            if source_contents:
                grounding_result = _run_enhanced_grounding_check(
                    summary_content,
                    source_contents,
                )

        except Exception as e:
            logger.error(f"Enhanced grounding check error (non-blocking): {e}")

    # Perform output validation (non-blocking, logging only)
    validation_flags = []
    if summary_content and len(summary_content) > 100:
        try:
            # Get source attributions from state if available
            source_attributions = state.get("source_attributions", [])

            validation = _validate_output(summary_content, source_attributions)

            if not validation["passed"]:
                logger.warning(
                    f"Output validation flagged {validation['high_risk_count']} high-risk, "
                    f"{validation['medium_risk_count']} medium-risk potential hallucinations"
                )
                for issue in validation["issues"][:5]:
                    logger.warning(
                        f"  - {issue['type']}: '{issue['text'][:50]}...' ({issue['risk']} risk) - {issue['suggestion']}"
                    )
                validation_flags = validation["issues"]
            else:
                logger.debug("Output validation passed with no high-risk issues")

        except Exception as e:
            # Validation errors should never block delivery
            logger.error(f"Output validation error (non-blocking): {e}")

    # Mark plan as completed and emit completion event
    if plan:
        plan.status = ExecutionStatus.COMPLETED
        # Store validation flags in plan metadata if available
        if validation_flags and hasattr(plan, "metadata"):
            if plan.metadata is None:
                plan.metadata = {}
            plan.metadata["validation_flags"] = validation_flags

        plan_event = PlanEvent(status=PlanStatus.COMPLETED, plan=plan)
        if event_queue:
            await event_queue.put(plan_event)
        else:
            pending_events.append(plan_event)

    # Always emit done event at the end
    done_event = DoneEvent()
    if event_queue:
        await event_queue.put(done_event)
    else:
        pending_events.append(done_event)

    # Optional context optimization after summary (Phase 3)
    # Reuse feature_flags from line 708 (get_feature_flags uses @lru_cache)
    if feature_flags.get("context_optimization") and executor:
        try:
            memory_manager = get_memory_manager()
            await executor._ensure_memory()
            messages = executor.memory.get_messages()
            optimized_messages, report = memory_manager.optimize_context(
                messages,
                preserve_recent=6,
                token_threshold=int(
                    memory_manager.get_pressure_status(executor.memory.estimate_tokens()).max_tokens * 0.6
                ),
            )
            if report.tokens_saved > 0:
                executor.memory.messages = optimized_messages
                agent_id = state.get("agent_id") or getattr(executor, "_agent_id", "unknown")
                await executor._repository.save_memory(agent_id, executor.name, executor.memory)
                logger.info(
                    f"LangGraph summary context optimization saved {report.tokens_saved} tokens "
                    f"(semantic={report.semantic_compacted}, temporal={report.temporal_compacted})"
                )
        except Exception as e:
            logger.warning(f"LangGraph summary context optimization failed: {e}")

    # Build CoVe metadata if available
    cove_metadata = None
    if cove_result:
        cove_metadata = {
            "claims_verified": cove_result.claims_verified,
            "claims_contradicted": cove_result.claims_contradicted,
            "claims_uncertain": cove_result.claims_uncertain,
            "confidence_score": cove_result.confidence_score,
            "processing_time_ms": cove_result.processing_time_ms,
            "refined": cove_result.has_contradictions,
        }

    return {
        "plan": plan,
        "pending_events": pending_events,
        "validation_flags": validation_flags,
        "cove_result": cove_metadata,
        "grounding_result": grounding_result,
        "claim_verification_result": claim_verification_result,
    }
