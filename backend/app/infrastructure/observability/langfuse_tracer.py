"""Langfuse LLM Tracer Implementation.

Provides integration with Langfuse for LLM observability, including:
- Prompt/response tracing with full content capture
- Token usage and cost tracking
- Latency monitoring
- Tool call tracing with parent correlation
- Session and user attribution

Requires:
    pip install langfuse>=2.0.0

Configuration via environment or Settings:
    LANGFUSE_PUBLIC_KEY: Project public key
    LANGFUSE_SECRET_KEY: Project secret key
    LANGFUSE_HOST: Langfuse host (default: https://cloud.langfuse.com)
"""

import logging
from typing import Any

from app.infrastructure.observability.llm_tracer import (
    LLMTrace,
    LLMTracerInterface,
    ToolTrace,
    current_span_id,
    current_trace_id,
    estimate_cost,
)

logger = logging.getLogger(__name__)

# Try to import langfuse - graceful degradation if not installed
try:
    from langfuse import Langfuse
    from langfuse.client import StatefulGenerationClient
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    logger.debug("Langfuse not installed, LangfuseTracer will be unavailable")


class LangfuseTracer(LLMTracerInterface):
    """Langfuse implementation of LLM tracing.

    Exports traces to Langfuse for observability dashboard,
    including prompt playground, cost tracking, and analytics.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
        release: str | None = None,
        debug: bool = False,
    ):
        """Initialize Langfuse tracer.

        Args:
            public_key: Langfuse project public key
            secret_key: Langfuse project secret key
            host: Langfuse host URL
            release: Optional release/version identifier
            debug: Enable debug logging
        """
        if not LANGFUSE_AVAILABLE:
            raise ImportError(
                "Langfuse is not installed. Install it with: pip install langfuse>=2.0.0"
            )

        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            release=release,
            debug=debug,
        )
        self._host = host
        self._traces: dict[str, Any] = {}  # Active traces for correlation
        logger.info(f"Langfuse tracer initialized (host: {host})")

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
        """Trace an LLM call to Langfuse."""
        metadata = metadata or {}

        # Get or create trace
        trace_id = current_trace_id.get()
        session_id = metadata.get("session_id")
        user_id = metadata.get("user_id")

        # Get or create Langfuse trace
        if trace_id and trace_id in self._traces:
            langfuse_trace = self._traces[trace_id]
        else:
            langfuse_trace = self._client.trace(
                id=trace_id,
                name=f"session:{session_id}" if session_id else "llm_session",
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
            )
            if trace_id:
                self._traces[trace_id] = langfuse_trace

        # Create generation span
        generation = langfuse_trace.generation(
            name=name,
            model=model,
            input=input_messages,
            output=output if not tool_calls else {"content": output, "tool_calls": tool_calls},
            usage={
                "input": prompt_tokens,
                "output": completion_tokens,
                "unit": "TOKENS",
            },
            metadata={
                "cached_tokens": cached_tokens,
                "latency_ms": latency_ms,
                **metadata,
            },
            level="ERROR" if error else "DEFAULT",
            status_message=error if error else None,
        )

        # Calculate cost
        cost = estimate_cost(model, prompt_tokens, completion_tokens)

        # Update generation with cost
        if cost > 0:
            generation.update(
                usage={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total_cost": cost,
                    "unit": "TOKENS",
                }
            )

        # Build return trace
        trace = LLMTrace(
            trace_id=trace_id or langfuse_trace.id,
            span_id=generation.id,
            parent_span_id=current_span_id.get(),
            name=name,
            model=model,
            input_messages=input_messages,
            metadata=metadata,
        )

        trace.complete(
            output=output,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            error=error,
        )
        trace.latency_ms = latency_ms

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
        """Trace a tool call to Langfuse."""
        metadata = metadata or {}
        trace_id = parent_trace_id or current_trace_id.get()

        # Get Langfuse trace
        if trace_id and trace_id in self._traces:
            langfuse_trace = self._traces[trace_id]
        else:
            langfuse_trace = self._client.trace(
                id=trace_id,
                name="tool_execution",
                metadata=metadata,
            )
            if trace_id:
                self._traces[trace_id] = langfuse_trace

        # Create span for tool call
        span = langfuse_trace.span(
            name=f"tool:{tool_name}.{function_name}",
            input=arguments,
            output=result[:2000] if result else None,  # Truncate large results
            metadata={
                "tool_name": tool_name,
                "function_name": function_name,
                "success": success,
                "latency_ms": latency_ms,
                **metadata,
            },
            level="ERROR" if error else "DEFAULT",
            status_message=error if error else None,
        )

        # Build return trace
        trace = ToolTrace(
            trace_id=trace_id or langfuse_trace.id,
            span_id=span.id,
            parent_span_id=current_span_id.get(),
            tool_name=tool_name,
            function_name=function_name,
            arguments=arguments,
            metadata=metadata,
        )

        trace.complete(result=result, success=success, error=error)
        trace.latency_ms = latency_ms

        return trace

    def get_trace_url(self, trace_id: str) -> str | None:
        """Get URL to view trace in Langfuse dashboard."""
        if not trace_id:
            return None
        # Langfuse trace URL format
        return f"{self._host}/trace/{trace_id}"

    async def flush(self) -> None:
        """Flush pending events to Langfuse."""
        try:
            self._client.flush()
            logger.debug("Langfuse flush completed")
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse events: {e}")

    def shutdown(self) -> None:
        """Shutdown the Langfuse client."""
        try:
            self._client.shutdown()
            logger.info("Langfuse tracer shutdown complete")
        except Exception as e:
            logger.warning(f"Error during Langfuse shutdown: {e}")

    def score_trace(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str | None = None,
    ) -> None:
        """Add a score/evaluation to a trace.

        Args:
            trace_id: The trace to score
            name: Score name (e.g., "accuracy", "relevance")
            value: Score value (typically 0-1)
            comment: Optional comment
        """
        try:
            self._client.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
            )
        except Exception as e:
            logger.warning(f"Failed to score trace {trace_id}: {e}")


def create_langfuse_tracer_from_settings() -> LangfuseTracer | None:
    """Create Langfuse tracer from application settings.

    Returns:
        LangfuseTracer instance or None if not configured
    """
    if not LANGFUSE_AVAILABLE:
        logger.debug("Langfuse not available")
        return None

    try:
        from app.core.config import get_settings
        settings = get_settings()

        public_key = getattr(settings, 'langfuse_public_key', None)
        secret_key = getattr(settings, 'langfuse_secret_key', None)

        if not public_key or not secret_key:
            logger.debug("Langfuse not configured (missing keys)")
            return None

        host = getattr(settings, 'langfuse_host', 'https://cloud.langfuse.com')

        return LangfuseTracer(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            debug=settings.debug,
        )
    except Exception as e:
        logger.warning(f"Failed to create Langfuse tracer: {e}")
        return None
