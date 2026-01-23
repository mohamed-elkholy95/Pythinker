"""
Centralized error handling for agent operations.

Provides error classification, context tracking, and recovery strategies
for various failure modes in the agent execution pipeline. Integrates
with error pattern analysis for proactive guidance.
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Classification of error types for targeted handling"""
    JSON_PARSE = "json_parse"
    TOKEN_LIMIT = "token_limit"
    TOOL_EXECUTION = "tool_execution"
    LLM_API = "llm_api"
    LLM_EMPTY_RESPONSE = "llm_empty_response"
    MCP_CONNECTION = "mcp_connection"
    TIMEOUT = "timeout"
    STUCK_LOOP = "stuck_loop"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error handling and recovery"""
    error_type: ErrorType
    message: str
    original_exception: Optional[Exception] = None
    recoverable: bool = True
    recovery_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3

    def can_retry(self) -> bool:
        """Check if the error can be retried"""
        return self.recoverable and self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter"""
        self.retry_count += 1


class ErrorHandler:
    """
    Centralized error handler with type-specific recovery strategies.

    Classifies errors by type and provides appropriate recovery mechanisms
    or graceful degradation paths.
    """

    def __init__(self):
        self._handlers: Dict[ErrorType, Callable[[ErrorContext], Awaitable[Optional[str]]]] = {}
        self._error_history: list[ErrorContext] = []
        self._max_history = 100

    def classify_error(self, exception: Exception, context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """
        Classify an exception into an ErrorContext with appropriate type and recovery strategy.

        Args:
            exception: The exception to classify
            context: Optional additional context information

        Returns:
            ErrorContext with classification and recovery strategy
        """
        context = context or {}
        error_message = str(exception)
        error_type = self._determine_error_type(exception, error_message)

        recovery_strategy, recoverable = self._get_recovery_strategy(error_type, error_message)

        error_context = ErrorContext(
            error_type=error_type,
            message=error_message,
            original_exception=exception,
            recoverable=recoverable,
            recovery_strategy=recovery_strategy,
            metadata=context
        )

        self._record_error(error_context)
        logger.warning(f"Classified error as {error_type.value}: {error_message[:100]}")

        return error_context

    def _determine_error_type(self, exception: Exception, message: str) -> ErrorType:
        """Determine the error type based on exception and message"""
        message_lower = message.lower()
        exception_type = type(exception).__name__.lower()

        # JSON parsing errors
        if any(term in message_lower for term in ['json', 'decode', 'parse']) or \
           any(term in exception_type for term in ['json', 'decode']):
            return ErrorType.JSON_PARSE

        # Token/context limit errors
        if any(term in message_lower for term in [
            'context_length_exceeded', 'token', 'context length',
            'maximum context', 'too long', 'max_tokens'
        ]):
            return ErrorType.TOKEN_LIMIT

        # Timeout errors
        if any(term in message_lower for term in ['timeout', 'timed out']) or \
           'timeout' in exception_type:
            return ErrorType.TIMEOUT

        # MCP connection errors
        if any(term in message_lower for term in ['mcp', 'connection', 'disconnect']):
            return ErrorType.MCP_CONNECTION

        # LLM API errors (OpenAI, etc.)
        if any(term in message_lower for term in [
            'openai', 'api', 'rate limit', 'authentication',
            'invalid_api_key', 'insufficient_quota'
        ]):
            return ErrorType.LLM_API

        # Tool execution errors
        if any(term in message_lower for term in ['tool', 'function', 'execute', 'invoke']):
            return ErrorType.TOOL_EXECUTION

        # Empty response errors from LLM
        if any(term in message_lower for term in ['empty response', 'no content', 'empty content']):
            return ErrorType.LLM_EMPTY_RESPONSE

        return ErrorType.UNKNOWN

    def _get_recovery_strategy(self, error_type: ErrorType, message: str) -> tuple[Optional[str], bool]:
        """
        Get recovery strategy and recoverability for an error type.

        Returns:
            Tuple of (recovery_strategy, is_recoverable)
        """
        strategies = {
            ErrorType.JSON_PARSE: (
                "Retry with explicit JSON formatting instruction",
                True
            ),
            ErrorType.TOKEN_LIMIT: (
                "Trim context and retry with reduced history",
                True
            ),
            ErrorType.TIMEOUT: (
                "Retry with exponential backoff",
                True
            ),
            ErrorType.MCP_CONNECTION: (
                "Attempt reconnection to MCP server",
                True
            ),
            ErrorType.LLM_API: self._get_llm_api_strategy(message),
            ErrorType.TOOL_EXECUTION: (
                "Retry tool execution with error context",
                True
            ),
            ErrorType.STUCK_LOOP: (
                "Inject recovery prompt to break loop",
                True
            ),
            ErrorType.LLM_EMPTY_RESPONSE: (
                "Retry with simplified prompt or different approach",
                True
            ),
            ErrorType.UNKNOWN: (
                "Log and escalate to user",
                False
            )
        }

        return strategies.get(error_type, ("Unknown error handling", False))

    def _get_llm_api_strategy(self, message: str) -> tuple[Optional[str], bool]:
        """Get specific strategy for LLM API errors"""
        message_lower = message.lower()

        if 'rate limit' in message_lower:
            return ("Wait and retry with exponential backoff", True)
        elif 'authentication' in message_lower or 'api_key' in message_lower:
            return ("Check API key configuration", False)
        elif 'insufficient_quota' in message_lower:
            return ("API quota exceeded, notify user", False)
        else:
            return ("Retry LLM request", True)

    def _record_error(self, error_context: ErrorContext) -> None:
        """Record error in history for analysis"""
        self._error_history.append(error_context)

        # Keep history bounded
        if len(self._error_history) > self._max_history:
            self._error_history = self._error_history[-self._max_history:]

    def get_recovery_prompt(
        self,
        error_context: ErrorContext,
        tool_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a recovery prompt based on error context.

        Includes pattern-based insights when available.

        Args:
            error_context: The error context
            tool_name: Optional tool name for pattern-specific guidance

        Returns:
            Recovery prompt string
        """
        prompts = {
            ErrorType.JSON_PARSE: (
                "Your previous response was not valid JSON. Please respond with "
                "properly formatted JSON only, ensuring all strings are properly escaped "
                "and the structure matches the expected schema."
            ),
            ErrorType.STUCK_LOOP: (
                "It appears you may be repeating similar actions. Please take a different "
                "approach to solve this task. Consider:\n"
                "1. Re-reading the original request\n"
                "2. Trying an alternative method\n"
                "3. Breaking down the task differently\n"
                "4. Reporting if you're blocked and need user input"
            ),
            ErrorType.TOOL_EXECUTION: (
                f"The previous tool execution failed with: {error_context.message[:200]}. "
                "Please try a different approach or use an alternative tool."
            ),
            ErrorType.TOKEN_LIMIT: (
                "The context has been trimmed due to length limits. Please continue "
                "from where you left off, focusing on the most recent task."
            ),
            ErrorType.LLM_EMPTY_RESPONSE: (
                "Your previous response was empty. Please provide a response by either:\n"
                "1. Using a tool to accomplish the task, OR\n"
                "2. Providing a text response if the task is complete.\n"
                "You must respond with either a tool call or content."
            )
        }

        base_prompt = prompts.get(error_context.error_type, "")

        # Try to add pattern-based insights
        pattern_insights = self._get_pattern_insights(tool_name)
        if pattern_insights:
            if base_prompt:
                return f"{base_prompt}\n\n{pattern_insights}"
            return pattern_insights

        return base_prompt if base_prompt else None

    def _get_pattern_insights(self, tool_name: Optional[str] = None) -> Optional[str]:
        """Get insights from error pattern analysis"""
        try:
            from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer

            analyzer = get_error_pattern_analyzer()
            patterns = analyzer.analyze_patterns()

            if not patterns:
                return None

            # Get relevant patterns
            if tool_name:
                relevant = [p for p in patterns if tool_name in p.affected_tools]
                if relevant:
                    return relevant[0].to_context_signal()

            # Return most confident pattern
            if patterns:
                best = max(patterns, key=lambda p: p.confidence)
                return best.to_context_signal()

        except Exception as e:
            logger.debug(f"Could not get pattern insights: {e}")

        return None

    def record_tool_error(
        self,
        tool_name: str,
        error_context: ErrorContext,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a tool error for pattern analysis"""
        try:
            from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer

            analyzer = get_error_pattern_analyzer()
            analyzer.record_error(tool_name, error_context, metadata)

        except Exception as e:
            logger.debug(f"Could not record tool error: {e}")

    def record_tool_success(self, tool_name: str) -> None:
        """Record a tool success to break failure streaks"""
        try:
            from app.domain.services.agents.error_pattern_analyzer import get_error_pattern_analyzer

            analyzer = get_error_pattern_analyzer()
            analyzer.record_success(tool_name)

        except Exception as e:
            logger.debug(f"Could not record tool success: {e}")

    def get_recent_errors(self, error_type: Optional[ErrorType] = None, limit: int = 10) -> list[ErrorContext]:
        """Get recent errors, optionally filtered by type"""
        errors = self._error_history

        if error_type:
            errors = [e for e in errors if e.error_type == error_type]

        return errors[-limit:]

    def clear_history(self) -> None:
        """Clear error history"""
        self._error_history.clear()


class TokenLimitExceeded(Exception):
    """Exception raised when token/context limit is exceeded"""

    def __init__(self, message: str, current_tokens: Optional[int] = None, max_tokens: Optional[int] = None):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens
