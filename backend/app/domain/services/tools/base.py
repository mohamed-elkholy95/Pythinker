import inspect
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.cache_layer import (
    _generate_cache_key,
    _get_tool_ttl,
    _should_cache_tool,
    get_cache_stats,
)


@dataclass
class ToolSchema:
    """Schema definition for a tool function.

    Used to define tool parameters and metadata for LLM tool calling.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

logger = logging.getLogger(__name__)


class ProgressCallback(Protocol):
    """Protocol for progress callback functions."""

    async def __call__(
        self,
        tool_call_id: str,
        tool_name: str,
        function_name: str,
        progress_percent: int,
        current_step: str,
        steps_completed: int,
        steps_total: int | None,
        elapsed_ms: float,
        checkpoint_id: str | None = None,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> None:
        """Called when tool progress updates."""
        ...


@dataclass
class ToolProgress:
    """Tracks progress of a tool execution.

    Used for long-running operations to provide real-time feedback
    and enable checkpointing for resume capability.
    """

    tool_call_id: str
    tool_name: str
    function_name: str
    start_time: float = field(default_factory=time.time)

    # Progress state
    steps_completed: int = 0
    steps_total: int | None = None
    current_step: str = "Initializing"

    # Checkpointing
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    last_checkpoint_id: str | None = None

    # Callback for progress updates
    _callback: ProgressCallback | None = None

    @property
    def progress_percent(self) -> int:
        """Calculate progress percentage."""
        if self.steps_total is None or self.steps_total == 0:
            return 0
        return min(100, int((self.steps_completed / self.steps_total) * 100))

    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000

    @property
    def estimated_remaining_ms(self) -> float | None:
        """Estimate remaining time based on current progress."""
        if self.steps_completed == 0 or self.steps_total is None:
            return None
        elapsed = self.elapsed_ms
        rate = elapsed / self.steps_completed
        remaining_steps = self.steps_total - self.steps_completed
        return rate * remaining_steps

    async def update(
        self,
        current_step: str,
        steps_completed: int | None = None,
        steps_total: int | None = None,
    ) -> None:
        """Update progress and notify callback.

        Args:
            current_step: Description of current action
            steps_completed: Number of steps completed (increments if None)
            steps_total: Total steps (updates if provided)
        """
        self.current_step = current_step
        if steps_completed is not None:
            self.steps_completed = steps_completed
        else:
            self.steps_completed += 1
        if steps_total is not None:
            self.steps_total = steps_total

        await self._emit_progress()

    async def checkpoint(self, checkpoint_data: dict[str, Any]) -> str:
        """Create a checkpoint for resume capability.

        Args:
            checkpoint_data: State to save for resume

        Returns:
            Checkpoint ID
        """
        checkpoint_id = str(uuid.uuid4())[:8]
        self.checkpoints.append(
            {
                "id": checkpoint_id,
                "step": self.steps_completed,
                "current_step": self.current_step,
                "data": checkpoint_data,
                "timestamp": time.time(),
            }
        )
        self.last_checkpoint_id = checkpoint_id

        await self._emit_progress(checkpoint_id=checkpoint_id, checkpoint_data=checkpoint_data)
        return checkpoint_id

    async def _emit_progress(
        self,
        checkpoint_id: str | None = None,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> None:
        """Emit progress update via callback."""
        if self._callback:
            try:
                await self._callback(
                    tool_call_id=self.tool_call_id,
                    tool_name=self.tool_name,
                    function_name=self.function_name,
                    progress_percent=self.progress_percent,
                    current_step=self.current_step,
                    steps_completed=self.steps_completed,
                    steps_total=self.steps_total,
                    elapsed_ms=self.elapsed_ms,
                    checkpoint_id=checkpoint_id,
                    checkpoint_data=checkpoint_data,
                )
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def get_last_checkpoint(self) -> dict[str, Any] | None:
        """Get the last checkpoint for resume."""
        if self.checkpoints:
            return self.checkpoints[-1]
        return None


# Default observation limits per tool category (in characters)
DEFAULT_MAX_OBSERVE = 8000
TOOL_OBSERVATION_LIMITS = {
    "browser": 10000,  # Browser content can be verbose
    "shell": 5000,  # Command output usually shorter
    "file": 8000,  # File content moderate
    "search": 8000,  # Search results moderate
    "mcp": 6000,  # MCP resources varied
    "message": 2000,  # Messages should be concise
}


def _truncate_output(content: str, max_length: int, preserve_end: bool = True) -> str:
    """Truncate content intelligently, preserving structure.

    Args:
        content: Content to truncate
        max_length: Maximum length
        preserve_end: Whether to preserve some content from the end

    Returns:
        Truncated content with indicator
    """
    if len(content) <= max_length:
        return content

    if preserve_end:
        # Reserve 20% for the end portion
        end_reserve = int(max_length * 0.2)
        start_length = max_length - end_reserve - 50  # 50 for truncation message

        # Find natural break points
        start_content = content[:start_length]
        last_newline = start_content.rfind("\n")
        if last_newline > start_length * 0.8:
            start_content = start_content[:last_newline]

        end_content = content[-end_reserve:]
        first_newline = end_content.find("\n")
        if first_newline > 0 and first_newline < end_reserve * 0.2:
            end_content = end_content[first_newline + 1 :]

        truncated_chars = len(content) - len(start_content) - len(end_content)
        return f"{start_content}\n\n... [{truncated_chars:,} characters truncated] ...\n\n{end_content}"
    # Simple truncation from end
    truncated = content[:max_length]
    last_newline = truncated.rfind("\n")
    if last_newline > max_length * 0.8:
        truncated = truncated[:last_newline]

    truncated_chars = len(content) - len(truncated)
    return f"{truncated}\n\n... [{truncated_chars:,} characters truncated]"


# ===== Validation Utilities =====


class ToolValidationError(Exception):
    """Exception raised when tool input validation fails."""

    pass


def validate_url(url: str) -> str:
    """Validate URL has valid scheme.

    Args:
        url: URL to validate

    Returns:
        The validated URL

    Raises:
        ToolValidationError: If URL is invalid
    """
    if not url:
        raise ToolValidationError("URL cannot be empty")
    if not url.startswith(("http://", "https://")):
        raise ToolValidationError(f"Invalid URL scheme: {url}")
    return url


def validate_path_in_sandbox(path: str, sandbox_base: str = "/workspace") -> str:
    """Validate path is within sandbox directory.

    Prevents path traversal attacks by ensuring the resolved path
    stays within the allowed base directory.

    Args:
        path: Path to validate
        sandbox_base: Allowed base directory

    Returns:
        The validated path

    Raises:
        ToolValidationError: If path traversal detected
    """
    import os

    if not path:
        raise ToolValidationError("Path cannot be empty")

    # Normalize and resolve the path
    normalized = os.path.normpath(path)

    # Check for path traversal attempts
    if ".." in normalized.split(os.sep):
        raise ToolValidationError(f"Path traversal detected: {path}")

    # Ensure it's within sandbox (if absolute path)
    if os.path.isabs(normalized) and not normalized.startswith(sandbox_base):
        raise ToolValidationError(f"Path outside sandbox: {path}")

    return normalized


def validate_required_params(params: dict[str, Any], required: list[str]) -> None:
    """Validate all required parameters are present.

    Args:
        params: Dictionary of parameters
        required: List of required parameter names

    Raises:
        ToolValidationError: If required parameter is missing
    """
    missing = [p for p in required if p not in params or params[p] is None]
    if missing:
        raise ToolValidationError(f"Missing required parameters: {', '.join(missing)}")


# ===== Error Handling =====


def handle_tool_errors(func: Callable) -> Callable:
    """Decorator for standardized tool error handling.

    Catches exceptions and returns appropriate ToolResult.

    Usage:
        @handle_tool_errors
        async def my_tool_function(self, param: str) -> ToolResult:
            # Your code here
            pass
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> ToolResult:
        try:
            return await func(*args, **kwargs)
        except ToolValidationError as e:
            logger.warning(f"Validation error in {func.__name__}: {e}")
            return ToolResult.error(message=str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}")
            return ToolResult.error(message=f"Tool error: {type(e).__name__}: {e}")

    return wrapper


# ===== Logging Utilities =====


def log_tool_start(tool_name: str, function_name: str, params: dict[str, Any] | None = None) -> float:
    """Log tool execution start and return start time.

    Args:
        tool_name: Name of the tool
        function_name: Name of the function being called
        params: Optional parameters (will be truncated for logging)

    Returns:
        Start time for duration calculation
    """
    from app.domain.utils.text import TextTruncator

    start_time = time.time()
    if params:
        safe_params = TextTruncator.truncate_for_logging(params, max_value_length=50)
        logger.info(f"[{tool_name}] {function_name} started", extra={"params": safe_params})
    else:
        logger.info(f"[{tool_name}] {function_name} started")
    return start_time


def log_tool_end(
    tool_name: str,
    function_name: str,
    start_time: float,
    success: bool,
    message: str | None = None,
) -> None:
    """Log tool execution end.

    Args:
        tool_name: Name of the tool
        function_name: Name of the function
        start_time: Start time from log_tool_start
        success: Whether execution succeeded
        message: Optional result message
    """
    duration_ms = (time.time() - start_time) * 1000
    log_method = logger.info if success else logger.warning
    log_method(
        f"[{tool_name}] {function_name} completed",
        extra={
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "result_message": message[:100] if message else None,
        },
    )


def tool(name: str, description: str, parameters: dict[str, dict[str, Any]], required: list[str]) -> Callable:
    """Tool registration decorator

    Args:
        name: Tool name
        description: Tool description
        parameters: Tool parameter definitions
        required: List of required parameters

    Returns:
        Decorator function
    """

    def decorator(func):
        # Create tool schema directly using provided parameters, without automatic extraction
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": parameters, "required": required},
            },
        }

        # Store tool information
        func._function_name = name
        func._tool_description = description
        func._tool_schema = schema

        return func

    return decorator


class BaseTool:
    """Base tool class, providing common tool calling methods with observation limiting and caching"""

    name: str = ""
    max_observe: int | None = None  # Per-tool observation limit (None = use category default)
    enable_caching: bool = False  # Enable result caching for this tool
    supports_progress: bool = False  # Whether this tool supports progress tracking

    def __init__(
        self,
        max_observe: int | None = None,
        enable_caching: bool = False,
        progress_callback: ProgressCallback | None = None,
    ):
        """Initialize base tool class

        Args:
            max_observe: Optional custom observation limit for this tool instance
            enable_caching: Enable result caching for cacheable tools
            progress_callback: Optional callback for progress updates
        """
        self._tools_cache = None
        self._result_cache = None  # Redis cache instance
        self.enable_caching = enable_caching
        self._progress_callback = progress_callback
        self._active_progress: ToolProgress | None = None

        if max_observe is not None:
            self.max_observe = max_observe
        elif self.name and self.name in TOOL_OBSERVATION_LIMITS:
            self.max_observe = TOOL_OBSERVATION_LIMITS[self.name]
        else:
            # Try to find category match
            for category, limit in TOOL_OBSERVATION_LIMITS.items():
                if category in self.name.lower():
                    self.max_observe = limit
                    break
            else:
                self.max_observe = DEFAULT_MAX_OBSERVE

    def set_progress_callback(self, callback: ProgressCallback | None) -> None:
        """Set the progress callback for this tool.

        Args:
            callback: Callback function for progress updates
        """
        self._progress_callback = callback

    def create_progress(
        self,
        tool_call_id: str,
        function_name: str,
        steps_total: int | None = None,
    ) -> ToolProgress:
        """Create a progress tracker for a tool execution.

        Args:
            tool_call_id: Unique ID for this tool call
            function_name: Name of the function being executed
            steps_total: Total number of steps (if known)

        Returns:
            ToolProgress instance for tracking
        """
        progress = ToolProgress(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            function_name=function_name,
            steps_total=steps_total,
            _callback=self._progress_callback,
        )
        self._active_progress = progress
        return progress

    def get_active_progress(self) -> ToolProgress | None:
        """Get the currently active progress tracker.

        Returns:
            Active ToolProgress or None
        """
        return self._active_progress

    async def resume_from_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_data: dict[str, Any],
    ) -> ToolResult | None:
        """Resume execution from a checkpoint.

        Override in subclasses to support checkpoint resume.

        Args:
            checkpoint_id: ID of checkpoint to resume from
            checkpoint_data: Saved checkpoint state

        Returns:
            ToolResult if resume is successful, None if not supported
        """
        logger.warning(f"Tool {self.name} does not support checkpoint resume")
        return None

    def get_tools(self) -> list[dict[str, Any]]:
        """Get all registered tools

        Returns:
            List of tools
        """
        if self._tools_cache is not None:
            return self._tools_cache

        tools = []
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, "_tool_schema"):
                tools.append(method._tool_schema)

        self._tools_cache = tools
        return tools

    def has_function(self, function_name: str) -> bool:
        """Check if specified function exists

        Args:
            function_name: Function name

        Returns:
            Whether the tool exists
        """
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, "_function_name") and method._function_name == function_name:
                return True
        return False

    def _filter_parameters(self, method: Callable, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Filter parameters to match method signature

        Args:
            method: Target method
            kwargs: Input parameters

        Returns:
            Filtered parameters that match the method signature
        """
        # Get method signature
        sig = inspect.signature(method)

        # Filter kwargs to only include parameters that the method accepts
        filtered_kwargs = {}
        for param_name, param_value in kwargs.items():
            if param_name in sig.parameters:
                filtered_kwargs[param_name] = param_value

        return filtered_kwargs

    async def _get_result_cache(self):
        """Lazy-load the result cache."""
        if self._result_cache is None and self.enable_caching:
            try:
                from app.domain.external.cache import get_cache

                self._result_cache = get_cache()
            except Exception as e:
                logger.warning(f"Failed to initialize result cache: {e}")
        return self._result_cache

    async def invoke_function(self, function_name: str, **kwargs) -> ToolResult:
        """Invoke specified tool with observation limiting and optional caching

        Args:
            function_name: Function name
            **kwargs: Parameters

        Returns:
            Invocation result with potentially truncated output

        Raises:
            ValueError: Raised when tool doesn't exist
        """
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, "_function_name") and method._function_name == function_name:
                # Filter parameters to match method signature
                filtered_kwargs = self._filter_parameters(method, kwargs)

                # Structured logging for tool execution
                start_time = log_tool_start(self.name, function_name, filtered_kwargs)

                # Check cache if enabled
                result = None
                cache_key = None
                stats = get_cache_stats()

                if self.enable_caching and _should_cache_tool(function_name):
                    cache = await self._get_result_cache()
                    if cache:
                        cache_key = _generate_cache_key(function_name, filtered_kwargs)
                        try:
                            cached_value = await cache.get(cache_key)
                            if cached_value is not None:
                                logger.debug(f"Cache hit for {function_name}")
                                stats.record_hit()
                                result = ToolResult(**cached_value)
                        except Exception as e:
                            logger.warning(f"Cache get failed: {e}")
                            stats.record_error()

                # Execute if not cached
                if result is None:
                    if self.enable_caching and _should_cache_tool(function_name):
                        stats.record_miss()

                    result = await method(**filtered_kwargs)

                    # Store in cache if successful
                    if self.enable_caching and cache_key and result.success:
                        cache = await self._get_result_cache()
                        if cache:
                            try:
                                ttl = _get_tool_ttl(function_name)
                                cache_value = {
                                    "success": result.success,
                                    "message": result.message,
                                    "data": (
                                        result.data.model_dump() if hasattr(result.data, "model_dump") else result.data
                                    )
                                    if result.data
                                    else None,
                                }
                                await cache.set(cache_key, cache_value, ttl=ttl)
                                logger.debug(f"Cached {function_name} for {ttl}s")
                            except Exception as e:
                                logger.warning(f"Cache set failed: {e}")
                                stats.record_error()

                # Apply observation limiting to result message
                if self.max_observe and result.message:
                    original_length = len(result.message)
                    if original_length > self.max_observe:
                        result.message = _truncate_output(result.message, self.max_observe, preserve_end=True)
                        logger.debug(
                            f"Truncated {function_name} output from {original_length:,} "
                            f"to {len(result.message):,} chars (limit: {self.max_observe:,})"
                        )

                log_tool_end(self.name, function_name, start_time, result.success, result.message)
                return result

        raise ValueError(f"Tool '{function_name}' not found")

    def set_max_observe(self, limit: int | None) -> None:
        """Set custom observation limit for this tool instance.

        Args:
            limit: New observation limit, or None to disable limiting
        """
        self.max_observe = limit

    def get_observation_stats(self, result: ToolResult) -> dict[str, Any]:
        """Get statistics about observation limiting for a result.

        Args:
            result: Tool result to analyze

        Returns:
            Dict with truncation stats
        """
        message_length = len(result.message) if result.message else 0
        return {
            "message_length": message_length,
            "max_observe": self.max_observe,
            "would_truncate": self.max_observe and message_length > self.max_observe,
            "truncation_amount": max(0, message_length - (self.max_observe or message_length)),
        }
