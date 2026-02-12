"""Smart Router for Reducing LLM Calls

Replaces LLM calls with deterministic code-based routing where possible.
Research shows hybrid code+LLM approaches reduce calls by 40-60%.

Key optimizations:
1. Simple routing decisions -> Python conditionals
2. Format validation -> Pydantic models
3. Template responses -> String formatting
4. Early termination detection -> Pattern matching
5. Tool selection -> Rule-based routing

This reduces latency, cost, and improves consistency.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class RouteDecision(str, Enum):
    """Possible routing decisions."""

    NEEDS_LLM = "needs_llm"  # Requires LLM reasoning
    DIRECT_RESPONSE = "direct_response"  # Can respond directly
    TOOL_CALL = "tool_call"  # Direct tool call
    CLARIFICATION = "clarification"  # Need user clarification
    EARLY_TERMINATE = "early_terminate"  # Task is complete
    ERROR = "error"  # Error condition


@dataclass
class RoutingResult:
    """Result of smart routing."""

    decision: RouteDecision
    response: str | None = None  # Direct response if applicable
    tool_name: str | None = None  # Tool to call if applicable
    tool_args: dict[str, Any] | None = None
    confidence: float = 1.0  # How confident we are in the decision
    reason: str = ""  # Explanation for the decision
    bypass_llm: bool = False  # Whether to skip LLM entirely


class SmartRouter:
    """Routes requests to avoid unnecessary LLM calls.

    Usage:
        router = SmartRouter()

        result = router.route("What time is it?")
        if result.bypass_llm:
            return result.response
        else:
            # Proceed with LLM call
    """

    IDENTITY_RESPONSE: ClassVar[str] = (
        "I am Pythinker, an AI assistant created by the Pythinker Team and Mohamed Elkholy."
    )
    MODEL_RESPONSE: ClassVar[str] = (
        "I am Pythinker. My exact backend model can vary by configuration, and I am created by the "
        "Pythinker Team and Mohamed Elkholy."
    )

    # Patterns for direct responses (no LLM needed)
    DIRECT_RESPONSE_PATTERNS: ClassVar[dict[str, str]] = {
        # Greetings
        r"^(hi|hello|hey|greetings)[\s!.]*$": "Hello! How can I help you today?",
        r"^(thanks|thank you|thx)[\s!.]*$": "You're welcome! Is there anything else I can help with?",
        r"^(bye|goodbye|see you)[\s!.]*$": "Goodbye! Feel free to return if you need assistance.",
        # Identity questions (use configured identity)
        r"^who\s+(?:are|r)\s+you[\s?.!]*$": IDENTITY_RESPONSE,
        r"^what\s+(?:are|r)\s+you[\s?.!]*$": IDENTITY_RESPONSE,
        r"^who\s+(?:made|created|built|developed)\s+you[\s?.!]*$": IDENTITY_RESPONSE,
        r"^who\s+is\s+your\s+(?:creator|maker|developer)[\s?.!]*$": IDENTITY_RESPONSE,
        r"^what(?:'s|\s+is)\s+your\s+(?:model|model\s+name|underlying\s+model)[\s?.!]*$": MODEL_RESPONSE,
        r"^what\s+model\s+(?:are\s+you|do\s+you\s+use|powers?\s+you)[\s?.!]*$": MODEL_RESPONSE,
        r"^which\s+model\s+(?:are\s+you|do\s+you\s+use|powers?\s+you)[\s?.!]*$": MODEL_RESPONSE,
    }

    # Patterns for direct tool calls (no LLM reasoning needed)
    DIRECT_TOOL_PATTERNS: ClassVar[dict[str, tuple[str, Any]]] = {
        # File operations
        r'^(?:read|show|display|cat)\s+(?:the\s+)?(?:file\s+)?["\']?([^\s"\']+)["\']?$': (
            "file_read",
            lambda m: {"path": m.group(1)},
        ),
        r'^(?:list|ls|show)\s+(?:files\s+in\s+)?(?:the\s+)?(?:directory\s+)?["\']?([^\s"\']+)["\']?$': (
            "file_list",
            lambda m: {"path": m.group(1)},
        ),
        # Shell commands
        r'^run\s+["\']?(.+)["\']?$': ("shell_exec", lambda m: {"command": m.group(1)}),
        r'^exec(?:ute)?\s+["\']?(.+)["\']?$': ("shell_exec", lambda m: {"command": m.group(1)}),
        # Search
        r'^search\s+(?:for\s+)?["\']?(.+)["\']?$': ("info_search_web", lambda m: {"query": m.group(1)}),
        r'^google\s+["\']?(.+)["\']?$': ("info_search_web", lambda m: {"query": m.group(1)}),
    }

    # Patterns indicating task completion
    COMPLETION_PATTERNS: ClassVar[list[str]] = [
        r"\b(done|finished|completed|all\s+set)\b",
        r"^(that\'?s?\s+)?all\s*(for\s+now)?[\s!.]*$",
        r"^nothing\s+(else|more)[\s!.]*$",
        r"^no\s+(thanks|thank\s+you)[\s!.]*$",
    ]

    # Patterns indicating need for clarification
    AMBIGUOUS_PATTERNS: ClassVar[list[str]] = [
        r"^(it|this|that|the\s+thing)$",  # Too vague
        r"^[a-z]{1,2}$",  # Single letters
        r"^\?+$",  # Just question marks
    ]

    # Simple questions that can be answered from context
    CONTEXT_ANSWER_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"what\s+(?:is|was)\s+the\s+(?:last|previous)\s+(?:file|path)", "last_file"),
        (r"what\s+(?:did|was)\s+(?:i|we)\s+(?:just\s+)?(?:do|did)", "last_action"),
    ]

    def __init__(
        self,
        enable_direct_responses: bool = True,
        enable_direct_tools: bool = True,
        confidence_threshold: float = 0.8,
    ):
        """Initialize the smart router.

        Args:
            enable_direct_responses: Enable direct response bypassing
            enable_direct_tools: Enable direct tool call bypassing
            confidence_threshold: Minimum confidence for bypassing LLM
        """
        self.enable_direct_responses = enable_direct_responses
        self.enable_direct_tools = enable_direct_tools
        self.confidence_threshold = confidence_threshold

        # Compile patterns
        self._direct_response_re = {re.compile(p, re.IGNORECASE): r for p, r in self.DIRECT_RESPONSE_PATTERNS.items()}
        self._direct_tool_re = {
            re.compile(p, re.IGNORECASE): (tool, arg_fn) for p, (tool, arg_fn) in self.DIRECT_TOOL_PATTERNS.items()
        }
        self._completion_re = [re.compile(p, re.IGNORECASE) for p in self.COMPLETION_PATTERNS]
        self._ambiguous_re = [re.compile(p, re.IGNORECASE) for p in self.AMBIGUOUS_PATTERNS]

        # Statistics
        self._stats = {
            "total_routes": 0,
            "llm_bypassed": 0,
            "direct_responses": 0,
            "direct_tools": 0,
            "early_terminations": 0,
        }

    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> RoutingResult:
        """Route a message to determine if LLM is needed.

        Args:
            message: User message
            context: Optional execution context

        Returns:
            RoutingResult with routing decision
        """
        self._stats["total_routes"] += 1

        if not message:
            return RoutingResult(
                decision=RouteDecision.CLARIFICATION,
                reason="Empty message",
            )

        message = message.strip()

        # Check for ambiguous input
        for pattern in self._ambiguous_re:
            if pattern.match(message):
                return RoutingResult(
                    decision=RouteDecision.CLARIFICATION,
                    response="Could you please provide more details about what you'd like me to do?",
                    reason="Ambiguous input",
                    bypass_llm=True,
                )

        # Check for completion signals
        for pattern in self._completion_re:
            if pattern.search(message):
                self._stats["early_terminations"] += 1
                return RoutingResult(
                    decision=RouteDecision.EARLY_TERMINATE,
                    response="Great! Let me know if you need anything else.",
                    reason="Task completion signal detected",
                    bypass_llm=True,
                )

        # Check for direct responses
        if self.enable_direct_responses:
            for pattern, response in self._direct_response_re.items():
                if pattern.match(message):
                    self._stats["direct_responses"] += 1
                    self._stats["llm_bypassed"] += 1
                    return RoutingResult(
                        decision=RouteDecision.DIRECT_RESPONSE,
                        response=response,
                        confidence=0.95,
                        reason="Direct response pattern matched",
                        bypass_llm=True,
                    )

        # Check for direct tool calls
        if self.enable_direct_tools:
            for pattern, (tool_name, arg_fn) in self._direct_tool_re.items():
                match = pattern.match(message)
                if match:
                    try:
                        tool_args = arg_fn(match)
                        self._stats["direct_tools"] += 1
                        self._stats["llm_bypassed"] += 1
                        return RoutingResult(
                            decision=RouteDecision.TOOL_CALL,
                            tool_name=tool_name,
                            tool_args=tool_args,
                            confidence=0.9,
                            reason=f"Direct tool pattern: {tool_name}",
                            bypass_llm=True,
                        )
                    except Exception as e:
                        logger.debug(f"Tool pattern match failed: {e}")

        # Default: needs LLM
        return RoutingResult(
            decision=RouteDecision.NEEDS_LLM,
            reason="No direct route found",
            bypass_llm=False,
        )

    def check_early_termination(
        self,
        step_result: str,
        remaining_steps: int,
        user_goal: str,
    ) -> tuple[bool, str | None]:
        """Check if task can be terminated early.

        Args:
            step_result: Result of the last step
            remaining_steps: Number of steps left in plan
            user_goal: The user's original goal

        Returns:
            Tuple of (should_terminate, reason)
        """
        if not step_result:
            return False, None

        result_lower = step_result.lower()

        # Check for explicit completion signals in result
        completion_signals = [
            "task completed",
            "successfully created",
            "successfully written",
            "file saved",
            "operation complete",
            "done",
        ]

        for signal in completion_signals:
            # If this is the primary goal, we might be done
            if signal in result_lower and remaining_steps <= 2:  # Only suggest if few steps left
                return True, f"Completion signal detected: '{signal}'"

        # Check for error states that should stop execution
        error_signals = [
            "permission denied",
            "file not found",
            "connection refused",
            "authentication failed",
        ]

        for signal in error_signals:
            if signal in result_lower:
                return True, f"Error condition detected: '{signal}'"

        return False, None

    def select_tool_by_task(
        self,
        task_description: str,
        available_tools: list[str],
    ) -> str | None:
        """Select the most appropriate tool for a task without LLM.

        Args:
            task_description: Description of the task
            available_tools: List of available tool names

        Returns:
            Tool name if confident selection possible, None otherwise
        """
        task_lower = task_description.lower()

        # Tool selection rules
        tool_rules = {
            "file_read": ["read", "view", "show", "display", "cat", "contents of"],
            "file_write": ["write", "create file", "save to", "output to file"],
            "file_list": ["list files", "directory", "folder contents", "ls"],
            "shell_exec": ["run command", "execute", "terminal", "bash", "shell"],
            "info_search_web": ["search", "find online", "google", "look up", "research"],
            "browsing": ["browse", "visit website", "open url", "web page"],
        }

        best_match = None
        best_score = 0

        for tool, keywords in tool_rules.items():
            if tool not in available_tools:
                continue

            score = sum(1 for kw in keywords if kw in task_lower)
            if score > best_score:
                best_score = score
                best_match = tool

        # Only return if confident (multiple keyword matches)
        if best_score >= 2:
            logger.debug(f"Rule-based tool selection: {best_match} (score={best_score})")
            return best_match

        return None

    def format_template_response(
        self,
        template_key: str,
        **kwargs: Any,
    ) -> str | None:
        """Generate a response from a template without LLM.

        Args:
            template_key: Key identifying the template
            **kwargs: Template variables

        Returns:
            Formatted response or None if no template
        """
        templates = {
            "file_created": "Successfully created file: {path}",
            "file_read": "Here's the content of {path}:\n\n{content}",
            "search_results": "Found {count} results for '{query}':\n\n{results}",
            "error_file_not_found": "The file '{path}' was not found.",
            "error_permission": "Permission denied for '{path}'.",
            "step_complete": "Step completed: {description}",
            "task_complete": "Task completed successfully.\n\n{summary}",
        }

        template = templates.get(template_key)
        if template:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing template variable: {e}")

        return None

    def get_stats(self) -> dict[str, Any]:
        """Get routing statistics."""
        total = self._stats["total_routes"]
        bypassed = self._stats["llm_bypassed"]

        return {
            **self._stats,
            "bypass_rate": f"{bypassed / max(total, 1):.1%}",
            "estimated_cost_savings": f"~{bypassed * 0.002:.4f} USD",  # Rough estimate
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        for key in self._stats:
            self._stats[key] = 0


class ResponseValidator:
    """Validates responses without LLM using Pydantic-style rules."""

    @staticmethod
    def is_valid_file_path(path: str) -> bool:
        """Validate file path format."""
        if not path:
            return False
        # Basic validation
        return not any(c in path for c in ["<", ">", "|", "\0"])

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate URL format."""
        url_pattern = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )
        return bool(url_pattern.match(url))

    @staticmethod
    def is_valid_json(text: str) -> bool:
        """Validate JSON format."""
        import json

        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def extract_code_blocks(text: str) -> list[tuple[str, str]]:
        """Extract code blocks from markdown without LLM.

        Returns:
            List of (language, code) tuples
        """
        pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        matches = pattern.findall(text)
        return [(lang or "text", code.strip()) for lang, code in matches]


# Singleton instance
_router: SmartRouter | None = None


def get_smart_router() -> SmartRouter:
    """Get the global smart router instance."""
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router


def try_bypass_llm(message: str, context: dict[str, Any] | None = None) -> RoutingResult:
    """Convenience function to attempt LLM bypass.

    Args:
        message: User message
        context: Optional context

    Returns:
        RoutingResult
    """
    return get_smart_router().route(message, context)
