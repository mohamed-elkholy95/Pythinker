"""LLM Tracer Interface for Agent Observability.

Provides a unified interface for tracing LLM calls with prompt/response capture,
token costs, and latency tracking. Supports multiple backends (Langfuse, LangSmith, OTEL).

Usage:
    tracer = get_llm_tracer()

    # Trace a single LLM call
    async with tracer.trace_generation(
        name="planning",
        model="gpt-4",
        input_messages=[{"role": "user", "content": "..."}],
        metadata={"session_id": "..."}
    ) as trace:
        response = await llm.ask(messages)
        trace.set_output(response)
        trace.set_token_usage(prompt_tokens=100, completion_tokens=50)
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Context variables for trace correlation
current_trace_id: ContextVar[str | None] = ContextVar('current_trace_id', default=None)
current_span_id: ContextVar[str | None] = ContextVar('current_span_id', default=None)


# Token cost estimates per 1K tokens (USD) - 2026 pricing
MODEL_COSTS: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    # Anthropic
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    "claude-sonnet-4": {"input": 0.003, "output": 0.015},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    # DeepSeek
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
    # Ollama (local - no cost)
    "llama3.2": {"input": 0.0, "output": 0.0},
    "llama3.1": {"input": 0.0, "output": 0.0},
    "mistral": {"input": 0.0, "output": 0.0},
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int
) -> float:
    """Estimate cost in USD for token usage.

    Args:
        model: Model name (will attempt fuzzy match)
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens

    Returns:
        Estimated cost in USD
    """
    # Find matching model (fuzzy match)
    model_lower = model.lower()
    costs = None

    for model_name, model_costs in MODEL_COSTS.items():
        if model_name in model_lower or model_lower in model_name:
            costs = model_costs
            break

    if costs is None:
        # Default to GPT-4o pricing as fallback
        costs = MODEL_COSTS["gpt-4o"]

    input_cost = (prompt_tokens / 1000) * costs["input"]
    output_cost = (completion_tokens / 1000) * costs["output"]

    return input_cost + output_cost


@dataclass
class LLMTrace:
    """Complete trace record for an LLM call."""
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str = "llm_call"
    model: str = ""

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    latency_ms: float = 0.0

    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_cost_usd: float = 0.0

    # Content (may be truncated for storage)
    input_messages: list[dict[str, Any]] = field(default_factory=list)
    output_content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    status: str = "pending"  # pending, success, error

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def complete(
        self,
        output: str = "",
        tool_calls: list[dict] | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        error: str | None = None
    ) -> None:
        """Complete the trace with results."""
        self.end_time = datetime.now()
        self.latency_ms = (self.end_time - self.start_time).total_seconds() * 1000

        self.output_content = output
        if tool_calls:
            self.tool_calls = tool_calls

        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cached_tokens = cached_tokens
        self.total_cost_usd = estimate_cost(
            self.model, prompt_tokens, completion_tokens
        )

        if error:
            self.error = error
            self.status = "error"
        else:
            self.status = "success"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "model": self.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "input_messages_count": len(self.input_messages),
            "output_length": len(self.output_content),
            "tool_calls_count": len(self.tool_calls),
            "metadata": self.metadata,
            "error": self.error,
            "status": self.status,
        }


@dataclass
class ToolTrace:
    """Trace record for a tool call."""
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    tool_name: str = ""
    function_name: str = ""

    # Timing
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    latency_ms: float = 0.0

    # Content
    arguments: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    success: bool = False

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def complete(
        self,
        result: str = "",
        success: bool = True,
        error: str | None = None
    ) -> None:
        """Complete the tool trace."""
        self.end_time = datetime.now()
        self.latency_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.result = result
        self.success = success
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "tool_name": self.tool_name,
            "function_name": self.function_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "latency_ms": self.latency_ms,
            "arguments": self.arguments,
            "result_length": len(self.result) if self.result else 0,
            "success": self.success,
            "metadata": self.metadata,
            "error": self.error,
        }


class LLMTracerInterface(ABC):
    """Abstract interface for LLM tracing implementations."""

    @abstractmethod
    async def trace_llm_call(
        self,
        name: str,
        model: str,
        input_messages: list[dict[str, Any]],
        output: str,
        tool_calls: list[dict] | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        latency_ms: float = 0.0,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMTrace:
        """Record a completed LLM call.

        Args:
            name: Human-readable name for the call
            model: Model identifier
            input_messages: Input messages sent to the LLM
            output: LLM response content
            tool_calls: Any tool calls in the response
            prompt_tokens: Input token count
            completion_tokens: Output token count
            cached_tokens: Cached token count (if supported)
            latency_ms: Call duration in milliseconds
            error: Error message if call failed
            metadata: Additional context (session_id, user_id, etc.)

        Returns:
            LLMTrace with complete information
        """
        pass

    @abstractmethod
    async def trace_tool_call(
        self,
        tool_name: str,
        function_name: str,
        arguments: dict[str, Any],
        result: str,
        success: bool = True,
        latency_ms: float = 0.0,
        error: str | None = None,
        parent_trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTrace:
        """Record a tool call execution.

        Args:
            tool_name: Name of the tool
            function_name: Function being called
            arguments: Function arguments
            result: Tool result
            success: Whether execution succeeded
            latency_ms: Execution duration
            error: Error message if failed
            parent_trace_id: Parent trace for correlation
            metadata: Additional context

        Returns:
            ToolTrace with execution information
        """
        pass

    @abstractmethod
    def get_trace_url(self, trace_id: str) -> str | None:
        """Get URL to view trace in external platform.

        Args:
            trace_id: The trace identifier

        Returns:
            URL string or None if not applicable
        """
        pass

    @abstractmethod
    async def flush(self) -> None:
        """Flush any pending traces to the backend."""
        pass


class NoOpLLMTracer(LLMTracerInterface):
    """No-op tracer that stores traces locally for metrics but doesn't export."""

    def __init__(self):
        self._traces: list[LLMTrace] = []
        self._tool_traces: list[ToolTrace] = []
        self._max_history = 1000

    async def trace_llm_call(
        self,
        name: str,
        model: str,
        input_messages: list[dict[str, Any]],
        output: str,
        tool_calls: list[dict] | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        latency_ms: float = 0.0,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMTrace:
        trace = LLMTrace(
            trace_id=current_trace_id.get() or str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            parent_span_id=current_span_id.get(),
            name=name,
            model=model,
            input_messages=input_messages,
            metadata=metadata or {},
        )

        trace.complete(
            output=output,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            error=error,
        )

        # Override latency if provided (more accurate)
        if latency_ms > 0:
            trace.latency_ms = latency_ms

        self._traces.append(trace)
        if len(self._traces) > self._max_history:
            self._traces = self._traces[-500:]

        return trace

    async def trace_tool_call(
        self,
        tool_name: str,
        function_name: str,
        arguments: dict[str, Any],
        result: str,
        success: bool = True,
        latency_ms: float = 0.0,
        error: str | None = None,
        parent_trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ToolTrace:
        trace = ToolTrace(
            trace_id=parent_trace_id or current_trace_id.get() or str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            parent_span_id=current_span_id.get(),
            tool_name=tool_name,
            function_name=function_name,
            arguments=arguments,
            metadata=metadata or {},
        )

        trace.complete(result=result, success=success, error=error)
        if latency_ms > 0:
            trace.latency_ms = latency_ms

        self._tool_traces.append(trace)
        if len(self._tool_traces) > self._max_history:
            self._tool_traces = self._tool_traces[-500:]

        return trace

    def get_trace_url(self, trace_id: str) -> str | None:
        return None

    async def flush(self) -> None:
        pass

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get aggregated metrics from stored traces."""
        if not self._traces:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "error_rate": 0.0,
            }

        total_tokens = sum(t.total_tokens for t in self._traces)
        total_cost = sum(t.total_cost_usd for t in self._traces)
        error_count = sum(1 for t in self._traces if t.status == "error")
        avg_latency = sum(t.latency_ms for t in self._traces) / len(self._traces)

        # Group by model
        by_model: dict[str, dict[str, Any]] = {}
        for trace in self._traces:
            if trace.model not in by_model:
                by_model[trace.model] = {
                    "calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                    "avg_latency_ms": 0.0,
                    "latencies": [],
                }
            by_model[trace.model]["calls"] += 1
            by_model[trace.model]["tokens"] += trace.total_tokens
            by_model[trace.model]["cost_usd"] += trace.total_cost_usd
            by_model[trace.model]["latencies"].append(trace.latency_ms)

        # Calculate averages
        for model_stats in by_model.values():
            latencies = model_stats.pop("latencies")
            model_stats["avg_latency_ms"] = sum(latencies) / len(latencies) if latencies else 0

        return {
            "total_calls": len(self._traces),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_latency_ms": round(avg_latency, 2),
            "error_rate": error_count / len(self._traces) if self._traces else 0,
            "by_model": by_model,
            "tool_calls": len(self._tool_traces),
        }


# Generation context manager for convenient tracing
class GenerationContext:
    """Context manager for tracing a generation (LLM call)."""

    def __init__(
        self,
        tracer: LLMTracerInterface,
        name: str,
        model: str,
        input_messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ):
        self._tracer = tracer
        self._name = name
        self._model = model
        self._input_messages = input_messages
        self._metadata = metadata or {}
        self._start_time = time.perf_counter()
        self._output = ""
        self._tool_calls: list[dict] | None = None
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cached_tokens = 0
        self._error: str | None = None
        self._trace: LLMTrace | None = None

    def set_output(self, output: str) -> None:
        """Set the LLM output content."""
        self._output = output

    def set_tool_calls(self, tool_calls: list[dict]) -> None:
        """Set any tool calls in the response."""
        self._tool_calls = tool_calls

    def set_token_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> None:
        """Set token usage information."""
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._cached_tokens = cached_tokens

    def set_error(self, error: str) -> None:
        """Set error if the call failed."""
        self._error = error

    @property
    def trace(self) -> LLMTrace | None:
        """Get the completed trace (available after context exit)."""
        return self._trace


# Global tracer instance
_llm_tracer: LLMTracerInterface | None = None


def get_llm_tracer() -> LLMTracerInterface:
    """Get the global LLM tracer instance."""
    global _llm_tracer
    if _llm_tracer is None:
        _llm_tracer = NoOpLLMTracer()
    return _llm_tracer


def configure_llm_tracer(tracer: LLMTracerInterface) -> None:
    """Configure the global LLM tracer."""
    global _llm_tracer
    _llm_tracer = tracer
    logger.info(f"LLM tracer configured: {type(tracer).__name__}")


@asynccontextmanager
async def trace_generation(
    name: str,
    model: str,
    input_messages: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
):
    """Context manager for tracing an LLM generation.

    Usage:
        async with trace_generation("planning", "gpt-4", messages) as ctx:
            response = await llm.ask(messages)
            ctx.set_output(response.content)
            ctx.set_token_usage(prompt_tokens=100, completion_tokens=50)
    """
    tracer = get_llm_tracer()
    ctx = GenerationContext(tracer, name, model, input_messages, metadata)
    start_time = time.perf_counter()

    try:
        yield ctx
    except Exception as e:
        ctx.set_error(str(e))
        raise
    finally:
        latency_ms = (time.perf_counter() - start_time) * 1000
        ctx._trace = await tracer.trace_llm_call(
            name=ctx._name,
            model=ctx._model,
            input_messages=ctx._input_messages,
            output=ctx._output,
            tool_calls=ctx._tool_calls,
            prompt_tokens=ctx._prompt_tokens,
            completion_tokens=ctx._completion_tokens,
            cached_tokens=ctx._cached_tokens,
            latency_ms=latency_ms,
            error=ctx._error,
            metadata=ctx._metadata,
        )
