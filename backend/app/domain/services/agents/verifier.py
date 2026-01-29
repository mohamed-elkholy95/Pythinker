"""VerifierAgent for plan verification before execution.

The VerifierAgent validates plans BEFORE execution begins, checking for:
- Tool feasibility: Can available tools accomplish each step?
- Prerequisites: Does the plan assume capabilities we have?
- Dependencies: Are steps ordered correctly?
- Complexity: Is this a realistic plan?

This implements the Plan-Verify-Execute pattern to catch infeasible plans early
and avoid wasted execution cycles.

Usage:
    verifier = VerifierAgent(llm, json_parser, available_tools)

    # Verify a plan
    result = await verifier.verify_plan(
        plan=plan,
        user_request="Create a REST API",
        task_context="Backend development"
    )

    if result.verdict == VerificationVerdict.REVISE:
        # Return to planner with feedback
        new_plan = await planner.replan(result.revision_feedback)
"""

import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass
from pydantic import BaseModel, Field

from app.domain.external.llm import LLM
from app.domain.utils.json_parser import JsonParser
from app.domain.models.plan import Plan, Step
from app.domain.models.event import (
    BaseEvent,
    VerificationEvent,
    VerificationStatus,
)
from app.domain.models.agent_response import (
    VerificationResponse,
    VerificationVerdict,
    SimpleVerificationResponse,
    ToolFeasibility,
    PrerequisiteCheck,
    DependencyIssue,
)
from app.domain.services.prompts.verifier import (
    VERIFIER_SYSTEM_PROMPT,
    VERIFY_PLAN_PROMPT,
    VERIFY_SIMPLE_PLAN_PROMPT,
)
from app.domain.services.tools.base import BaseTool


logger = logging.getLogger(__name__)


@dataclass
class VerifierConfig:
    """Configuration for verifier behavior."""
    enabled: bool = True
    skip_simple_plans: bool = True
    simple_plan_max_steps: int = 2
    max_revision_loops: int = 2
    min_confidence_threshold: float = 0.6
    # Simple operation patterns that don't need verification
    simple_operations: tuple = (
        "search", "read", "list", "browse", "view", "find", "look up"
    )
    # Streaming short-circuit for faster verification
    enable_streaming_shortcircuit: bool = True
    early_pass_confidence_threshold: float = 0.85


class VerifierAgent:
    """Agent that verifies plans before execution begins.

    The verifier provides a gate between planning and execution:
    - PASS: Proceed to execution
    - REVISE: Return to planner with specific feedback
    - FAIL: Exit gracefully without wasted execution

    The verifier is designed to be:
    - Fast: Quick checks for simple plans, thorough for complex ones
    - Practical: Catches real issues, not theoretical problems
    - Fail-open: On error, proceed with execution (better than blocking)
    """

    def __init__(
        self,
        llm: LLM,
        json_parser: JsonParser,
        tools: List[BaseTool],
        config: Optional[VerifierConfig] = None
    ):
        """Initialize the VerifierAgent.

        Args:
            llm: Language model for verification
            json_parser: Parser for structured responses
            tools: List of available tools for feasibility checking
            config: Optional configuration
        """
        self.llm = llm
        self.json_parser = json_parser
        self.tools = tools
        self.config = config or VerifierConfig()

        # Extract tool names for prompts
        self._tool_names = self._get_tool_names()
        self._tool_descriptions = self._get_tool_descriptions()

    def _get_tool_names(self) -> List[str]:
        """Get list of available tool names."""
        names = []
        for tool in self.tools:
            for tool_def in tool.get_tools():
                func = tool_def.get("function", {})
                names.append(func.get("name", "unknown"))
        return names

    def _get_tool_descriptions(self) -> str:
        """Get formatted tool descriptions for prompts."""
        descriptions = []
        for tool in self.tools:
            for tool_def in tool.get_tools():
                func = tool_def.get("function", {})
                name = func.get("name", "unknown")
                desc = func.get("description", "No description")[:100]
                descriptions.append(f"- {name}: {desc}")
        return "\n".join(descriptions)

    def _should_skip_verification(self, plan: Plan) -> bool:
        """Determine if verification should be skipped for this plan."""
        if not self.config.enabled:
            return True

        if not self.config.skip_simple_plans:
            return False

        # Skip for very short plans
        if len(plan.steps) <= self.config.simple_plan_max_steps:
            # Check if all steps are simple operations
            all_simple = True
            for step in plan.steps:
                desc_lower = step.description.lower()
                is_simple = any(
                    op in desc_lower
                    for op in self.config.simple_operations
                )
                if not is_simple:
                    all_simple = False
                    break

            if all_simple:
                logger.debug(f"Skipping verification for simple plan: {plan.title}")
                return True

        return False

    def _format_steps(self, steps: List[Step]) -> str:
        """Format steps for prompt."""
        lines = []
        for step in steps:
            lines.append(f"Step {step.id}: {step.description}")
        return "\n".join(lines)

    async def verify_plan(
        self,
        plan: Plan,
        user_request: str,
        task_context: str = ""
    ) -> AsyncGenerator[BaseEvent, None]:
        """Verify a plan before execution.

        Args:
            plan: The plan to verify
            user_request: Original user request
            task_context: Additional context

        Yields:
            VerificationEvent with status updates and final result
        """
        # Check if we should skip verification
        if self._should_skip_verification(plan):
            logger.info(f"Verification skipped for plan: {plan.title}")
            yield VerificationEvent(
                status=VerificationStatus.PASSED,
                verdict="pass",
                confidence=0.95,
                summary="Simple plan - verification skipped"
            )
            return

        logger.info(f"Verifying plan: {plan.title} ({len(plan.steps)} steps)")

        # Emit started event
        yield VerificationEvent(
            status=VerificationStatus.STARTED,
            summary=f"Verifying plan with {len(plan.steps)} steps"
        )

        try:
            # Perform verification
            result = await self._do_verification(plan, user_request, task_context)

            # Emit appropriate event based on verdict
            if result.verdict == VerificationVerdict.PASS:
                yield VerificationEvent(
                    status=VerificationStatus.PASSED,
                    verdict="pass",
                    confidence=result.confidence,
                    summary=result.summary
                )
            elif result.verdict == VerificationVerdict.REVISE:
                yield VerificationEvent(
                    status=VerificationStatus.REVISION_NEEDED,
                    verdict="revise",
                    confidence=result.confidence,
                    summary=result.summary,
                    revision_feedback=result.revision_feedback
                )
            else:  # FAIL
                yield VerificationEvent(
                    status=VerificationStatus.FAILED,
                    verdict="fail",
                    confidence=result.confidence,
                    summary=result.summary
                )

        except Exception as e:
            logger.error(f"Verification failed with error: {e}")
            # Fail-open: proceed with execution on verification error
            yield VerificationEvent(
                status=VerificationStatus.PASSED,
                verdict="pass",
                confidence=0.5,
                summary=f"Verification error (fail-open): {str(e)[:100]}"
            )

    async def _do_verification(
        self,
        plan: Plan,
        user_request: str,
        task_context: str
    ) -> VerificationResponse:
        """Perform the actual verification.

        Uses streaming with short-circuit when enabled to detect early PASS
        signals and return faster for straightforward plans.
        """
        # Build the prompt
        prompt = VERIFY_PLAN_PROMPT.format(
            user_request=user_request,
            plan_title=plan.title,
            plan_goal=plan.goal,
            steps=self._format_steps(plan.steps),
            available_tools=self._tool_descriptions,
            task_context=task_context or "No additional context"
        )

        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        # Try streaming verification with short-circuit if enabled
        if self.config.enable_streaming_shortcircuit:
            early_result = await self._try_streaming_verification(messages, plan)
            if early_result:
                logger.debug(f"Streaming short-circuit: early {early_result.verdict.value} detected")
                return early_result

        # Fall back to standard verification
        response = await self.llm.ask(
            messages=messages,
            response_format={"type": "json_object"}
        )

        content = response.get("content", "")
        return await self._parse_verification_response(content)

    async def _try_streaming_verification(
        self,
        messages: List[Dict[str, Any]],
        plan: Plan
    ) -> Optional[VerificationResponse]:
        """Attempt streaming verification with early exit on clear PASS signal.

        Args:
            messages: LLM messages
            plan: Plan being verified

        Returns:
            Early VerificationResponse if PASS detected, None otherwise
        """
        if not hasattr(self.llm, 'stream') and not hasattr(self.llm, 'stream_ask'):
            return None

        try:
            accumulated = ""
            stream_method = getattr(self.llm, 'stream', None) or getattr(self.llm, 'stream_ask', None)

            # Some LLMs use different streaming interfaces
            if hasattr(self.llm, 'stream_ask'):
                stream = self.llm.stream_ask(
                    messages=messages,
                    response_format={"type": "json_object"}
                )
            elif hasattr(self.llm, 'stream'):
                stream = self.llm.stream(
                    messages=messages,
                    response_format={"type": "json_object"}
                )
            else:
                return None

            async for chunk in stream:
                # Extract token from chunk (format varies by LLM)
                if isinstance(chunk, dict):
                    token = chunk.get("content", "") or chunk.get("text", "")
                elif isinstance(chunk, str):
                    token = chunk
                else:
                    token = str(chunk)

                accumulated += token

                # Check for early PASS signal in accumulated content
                accumulated_lower = accumulated.lower()

                # Look for clear pass indicators early in the response
                if len(accumulated) > 50:  # Need some content
                    # Check for "verdict": "pass" pattern
                    if '"verdict"' in accumulated_lower and '"pass"' in accumulated_lower:
                        # Also check there's no revision feedback yet
                        if '"revision_feedback": null' in accumulated_lower or \
                           '"revision_feedback":null' in accumulated_lower:
                            # Early PASS detected
                            logger.info(f"Verification streaming: early PASS detected at {len(accumulated)} chars")
                            return VerificationResponse(
                                verdict=VerificationVerdict.PASS,
                                confidence=self.config.early_pass_confidence_threshold,
                                tool_feasibility=[],
                                prerequisite_checks=[],
                                dependency_issues=[],
                                revision_feedback=None,
                                summary=f"Plan verified (streaming early-exit, {len(plan.steps)} steps)"
                            )

                    # If we see REVISE or FAIL early, don't short-circuit - need full response
                    if '"verdict"' in accumulated_lower:
                        if '"revise"' in accumulated_lower or '"fail"' in accumulated_lower:
                            return None  # Fall back to full verification

                # Safety limit - if accumulated too much without clear signal, fall back
                if len(accumulated) > 500:
                    return None

            # If stream completed without early exit, return None to use full parsing
            return None

        except Exception as e:
            logger.debug(f"Streaming verification failed: {e}")
            return None

    async def _parse_verification_response(self, content: str) -> VerificationResponse:
        """Parse verification response content into VerificationResponse.

        Args:
            content: JSON response content

        Returns:
            Parsed VerificationResponse
        """
        parsed = await self.json_parser.parse(content)

        # Parse verdict
        verdict_str = parsed.get("verdict", "pass").lower()
        if verdict_str == "pass":
            verdict = VerificationVerdict.PASS
        elif verdict_str == "fail":
            verdict = VerificationVerdict.FAIL
        else:
            verdict = VerificationVerdict.REVISE

        # Build tool feasibility list
        tool_feasibility = []
        for tf in parsed.get("tool_feasibility", []):
            try:
                tool_feasibility.append(ToolFeasibility(
                    step_id=str(tf.get("step_id", "")),
                    tool=tf.get("tool", "unknown"),
                    feasible=tf.get("feasible", True),
                    reason=tf.get("reason", "")
                ))
            except Exception as e:
                logger.debug(f"Skipping malformed tool_feasibility entry: {e}")

        # Build prerequisite checks
        prerequisite_checks = []
        for pc in parsed.get("prerequisite_checks", []):
            try:
                prerequisite_checks.append(PrerequisiteCheck(
                    check=pc.get("check", ""),
                    satisfied=pc.get("satisfied", True),
                    detail=pc.get("detail", "")
                ))
            except Exception as e:
                logger.debug(f"Skipping malformed prerequisite_check entry: {e}")

        # Build dependency issues
        dependency_issues = []
        for di in parsed.get("dependency_issues", []):
            try:
                dependency_issues.append(DependencyIssue(
                    step_id=str(di.get("step_id", "")),
                    depends_on=di.get("depends_on", ""),
                    issue=di.get("issue", "")
                ))
            except Exception as e:
                logger.debug(f"Skipping malformed dependency_issue entry: {e}")

        return VerificationResponse(
            verdict=verdict,
            confidence=float(parsed.get("confidence", 0.8)),
            tool_feasibility=tool_feasibility,
            prerequisite_checks=prerequisite_checks,
            dependency_issues=dependency_issues,
            revision_feedback=parsed.get("revision_feedback"),
            summary=parsed.get("summary", "Verification completed")
        )

    async def quick_verify(
        self,
        plan: Plan,
        user_request: str
    ) -> SimpleVerificationResponse:
        """Quick verification for simple plans.

        Args:
            plan: The plan to verify
            user_request: Original user request

        Returns:
            SimpleVerificationResponse with verdict and summary
        """
        prompt = VERIFY_SIMPLE_PLAN_PROMPT.format(
            user_request=user_request,
            steps=self._format_steps(plan.steps),
            tool_names=", ".join(self._tool_names[:10])
        )

        messages = [
            {"role": "system", "content": "You are a quick plan verifier. Be concise."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = await self.llm.ask(
                messages=messages,
                response_format={"type": "json_object"}
            )

            content = response.get("content", "")
            parsed = await self.json_parser.parse(content)

            verdict_str = parsed.get("verdict", "pass").lower()
            if verdict_str == "pass":
                verdict = VerificationVerdict.PASS
            elif verdict_str == "fail":
                verdict = VerificationVerdict.FAIL
            else:
                verdict = VerificationVerdict.REVISE

            return SimpleVerificationResponse(
                verdict=verdict,
                confidence=float(parsed.get("confidence", 0.8)),
                summary=parsed.get("summary", "Quick verification completed")
            )

        except Exception as e:
            logger.error(f"Quick verification failed: {e}")
            # Fail-open
            return SimpleVerificationResponse(
                verdict=VerificationVerdict.PASS,
                confidence=0.5,
                summary=f"Verification error (fail-open): {str(e)[:50]}"
            )

    def get_revision_prompt_addition(
        self,
        verification_result: VerificationResponse
    ) -> str:
        """Generate additional prompt content for replanning based on verification.

        Args:
            verification_result: The verification result with issues

        Returns:
            String to add to the replanning prompt
        """
        lines = [
            "\n## Verification Feedback",
            f"The previous plan was flagged for revision: {verification_result.summary}",
        ]

        if verification_result.revision_feedback:
            lines.append(f"\nGuidance: {verification_result.revision_feedback}")

        if verification_result.tool_feasibility:
            infeasible = [tf for tf in verification_result.tool_feasibility if not tf.feasible]
            if infeasible:
                lines.append("\nInfeasible steps:")
                for tf in infeasible:
                    lines.append(f"- Step {tf.step_id}: {tf.reason}")

        if verification_result.dependency_issues:
            lines.append("\nDependency issues:")
            for di in verification_result.dependency_issues:
                lines.append(f"- Step {di.step_id}: {di.issue}")

        lines.append("\nPlease revise the plan to address these issues.")

        return "\n".join(lines)
