"""
Centralized error handling for agent operations.

Provides error classification, context tracking, and recovery strategies
for various failure modes in the agent execution pipeline. Integrates
with error pattern analysis for proactive guidance.

Enhanced with exponential backoff retry support for recoverable errors.
"""

import logging
import asyncio
import secrets
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, Awaitable, List, Tuple, TypeVar
from datetime import datetime

logger = logging.getLogger(__name__)

T = TypeVar('T')


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
    # Browser-specific errors
    BROWSER_NAVIGATION = "browser_navigation"
    BROWSER_ELEMENT_NOT_FOUND = "browser_element_not_found"
    BROWSER_CONNECTION = "browser_connection"
    BROWSER_TIMEOUT = "browser_timeout"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error handling and recovery with backoff support"""
    error_type: ErrorType
    message: str
    original_exception: Optional[Exception] = None
    recoverable: bool = True
    recovery_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    # Backoff configuration
    backoff_factor: float = 1.5
    min_retry_delay: float = 0.3
    max_retry_delay: float = 30.0
    jitter: bool = True

    def can_retry(self) -> bool:
        """Check if the error can be retried"""
        return self.recoverable and self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter"""
        self.retry_count += 1

    def get_retry_delay(self) -> float:
        """Calculate retry delay with exponential backoff and optional jitter.

        Returns:
            Delay in seconds before next retry
        """
        # Exponential backoff: min_delay * (factor ^ retry_count)
        delay = self.min_retry_delay * (self.backoff_factor ** self.retry_count)
        delay = min(delay, self.max_retry_delay)

        if self.jitter:
            # Add cryptographically secure random jitter ±25% to prevent thundering herd
            jitter_range = delay * 0.25
            # Generate a random float between -1 and 1, then scale by jitter_range
            random_factor = (secrets.randbelow(2000001) - 1000000) / 1000000.0
            delay += jitter_range * random_factor

        return max(0.1, delay)  # Minimum 100ms

    def get_backoff_config(self) -> Dict[str, Any]:
        """Get current backoff configuration for logging/debugging."""
        return {
            "backoff_factor": self.backoff_factor,
            "min_retry_delay": self.min_retry_delay,
            "max_retry_delay": self.max_retry_delay,
            "jitter": self.jitter,
            "current_retry": self.retry_count,
            "next_delay": self.get_retry_delay() if self.can_retry() else None
        }


class ErrorHandler:
    """
    Centralized error handler with type-specific recovery strategies.

    Classifies errors by type and provides appropriate recovery mechanisms
    or graceful degradation paths. Supports exponential backoff retry.
    """

    def __init__(self):
        self._handlers: Dict[ErrorType, Callable[[ErrorContext], Awaitable[Optional[str]]]] = {}
        self._error_history: list[ErrorContext] = []
        self._max_history = 100
        # Recovery tracking for metrics
        self._recovery_stats: Dict[ErrorType, Dict[str, int]] = {}
        self._total_retry_attempts = 0
        self._successful_recoveries = 0

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

        # Browser-specific errors (check before generic timeout)
        if any(term in message_lower for term in [
            'browser', 'playwright', 'page', 'navigate', 'cdp'
        ]):
            # Browser element not found
            if any(term in message_lower for term in [
                'element', 'selector', 'not found', 'cannot find', 'no such element',
                'interactive element', 'index'
            ]):
                return ErrorType.BROWSER_ELEMENT_NOT_FOUND

            # Browser connection errors
            if any(term in message_lower for term in [
                'connection', 'disconnect', 'closed', 'cdp', 'chrome'
            ]):
                return ErrorType.BROWSER_CONNECTION

            # Browser navigation errors
            if any(term in message_lower for term in [
                'navigate', 'navigation', 'goto', 'url', 'load'
            ]):
                return ErrorType.BROWSER_NAVIGATION

            # Browser timeout
            if any(term in message_lower for term in ['timeout', 'timed out']):
                return ErrorType.BROWSER_TIMEOUT

        # Timeout errors (generic)
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
            # Browser-specific strategies
            ErrorType.BROWSER_NAVIGATION: (
                "Verify URL format and retry navigation, or try alternative URL",
                True
            ),
            ErrorType.BROWSER_ELEMENT_NOT_FOUND: (
                "Refresh element indices with browser_view before retry",
                True
            ),
            ErrorType.BROWSER_CONNECTION: (
                "Reinitialize browser connection with browser_restart",
                True
            ),
            ErrorType.BROWSER_TIMEOUT: (
                "Page may still be usable - check with browser_view",
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
            ),
            # Browser-specific recovery prompts
            ErrorType.BROWSER_NAVIGATION: (
                f"Browser navigation failed: {error_context.message[:150]}\n"
                "RECOVERY STEPS:\n"
                "1. Verify the URL is complete with protocol (https://)\n"
                "2. Try an alternative URL or search engine\n"
                "3. If persistent, use browser_restart then retry"
            ),
            ErrorType.BROWSER_ELEMENT_NOT_FOUND: (
                f"Browser element not found: {error_context.message[:150]}\n"
                "RECOVERY STEPS:\n"
                "1. Use browser_view to get FRESH interactive element indices\n"
                "2. Element indices change after page updates - always refresh\n"
                "3. The element may be off-screen - try browser_scroll_down first\n"
                "4. The page may have changed - verify you're on the right page"
            ),
            ErrorType.BROWSER_CONNECTION: (
                f"Browser connection issue: {error_context.message[:150]}\n"
                "RECOVERY STEPS:\n"
                "1. Use browser_restart to reinitialize the browser\n"
                "2. Then navigate to your target URL\n"
                "3. If persistent, the sandbox may need restart"
            ),
            ErrorType.BROWSER_TIMEOUT: (
                f"Browser operation timed out: {error_context.message[:150]}\n"
                "RECOVERY STEPS:\n"
                "1. The page may still be partially loaded - use browser_view to check\n"
                "2. For slow pages, give them time and retry\n"
                "3. Try a simpler page or alternative source"
            ),
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

    async def handle_with_retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args,
        max_retries: int = 3,
        context: Optional[Dict[str, Any]] = None,
        on_retry: Optional[Callable[[ErrorContext, int], Awaitable[None]]] = None,
        **kwargs
    ) -> Tuple[bool, T | ErrorContext]:
        """Execute operation with automatic retry and exponential backoff.

        Args:
            operation: Async callable to execute
            *args: Arguments for the operation
            max_retries: Maximum retry attempts (default: 3)
            context: Optional context for error classification
            on_retry: Optional callback before each retry (error_context, attempt_number)
            **kwargs: Keyword arguments for the operation

        Returns:
            Tuple of (success: bool, result or error_context)
        """
        last_error_context: Optional[ErrorContext] = None

        for attempt in range(max_retries + 1):
            try:
                result = await operation(*args, **kwargs)

                # Record recovery success if this was a retry
                if attempt > 0 and last_error_context:
                    self._record_recovery_success(last_error_context)
                    logger.info(
                        f"Recovery successful after {attempt} retries for "
                        f"{last_error_context.error_type.value}"
                    )

                return True, result

            except Exception as e:
                error_context = self.classify_error(e, context)
                error_context.retry_count = attempt
                error_context.max_retries = max_retries
                last_error_context = error_context

                self._total_retry_attempts += 1

                # Check if we should retry
                if not error_context.can_retry():
                    self._record_recovery_failure(error_context)
                    logger.warning(
                        f"Error not recoverable or max retries reached: "
                        f"{error_context.error_type.value} - {error_context.message[:100]}"
                    )
                    return False, error_context

                # Calculate delay
                delay = error_context.get_retry_delay()

                logger.info(
                    f"Retry {attempt + 1}/{max_retries} for {error_context.error_type.value} "
                    f"after {delay:.2f}s delay"
                )

                # Call retry callback if provided
                if on_retry:
                    try:
                        await on_retry(error_context, attempt + 1)
                    except Exception as callback_error:
                        logger.warning(f"Retry callback failed: {callback_error}")

                # Wait before retry
                await asyncio.sleep(delay)

                error_context.increment_retry()

        # Should not reach here, but handle edge case
        if last_error_context:
            self._record_recovery_failure(last_error_context)
            return False, last_error_context

        return False, ErrorContext(
            error_type=ErrorType.UNKNOWN,
            message="Unexpected retry loop exit",
            recoverable=False
        )

    def _record_recovery_success(self, error_context: ErrorContext) -> None:
        """Record successful recovery for metrics tracking."""
        error_type = error_context.error_type
        if error_type not in self._recovery_stats:
            self._recovery_stats[error_type] = {"success": 0, "failure": 0}
        self._recovery_stats[error_type]["success"] += 1
        self._successful_recoveries += 1

    def _record_recovery_failure(self, error_context: ErrorContext) -> None:
        """Record failed recovery for metrics tracking."""
        error_type = error_context.error_type
        if error_type not in self._recovery_stats:
            self._recovery_stats[error_type] = {"success": 0, "failure": 0}
        self._recovery_stats[error_type]["failure"] += 1

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get recovery statistics for monitoring.

        Returns:
            Dict with recovery success rates and stats
        """
        total_recoveries = self._successful_recoveries + sum(
            stats["failure"] for stats in self._recovery_stats.values()
        )
        success_rate = (
            self._successful_recoveries / total_recoveries
            if total_recoveries > 0 else 0.0
        )

        return {
            "total_retry_attempts": self._total_retry_attempts,
            "successful_recoveries": self._successful_recoveries,
            "success_rate": success_rate,
            "by_error_type": {
                error_type.value: stats
                for error_type, stats in self._recovery_stats.items()
            }
        }

    def reset_stats(self) -> None:
        """Reset recovery statistics."""
        self._recovery_stats.clear()
        self._total_retry_attempts = 0
        self._successful_recoveries = 0


class TokenLimitExceeded(Exception):
    """Exception raised when token/context limit is exceeded"""

    def __init__(self, message: str, current_tokens: Optional[int] = None, max_tokens: Optional[int] = None):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens
