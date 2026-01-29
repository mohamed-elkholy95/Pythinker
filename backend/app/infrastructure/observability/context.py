"""Request Context Management for Observability.

Provides ContextVar-based request context propagation for:
- Request ID correlation across logs and traces
- Session ID tracking
- User ID attribution

Usage:
    # In middleware
    request_context.set(request_id="abc123", session_id="sess-456")

    # In any module
    ctx = get_request_context()
    logger.info(f"Processing request {ctx.request_id}")

    # With structured logging
    logger.info("message", extra=ctx.to_log_extra())
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestContext:
    """Request-scoped context for observability."""

    request_id: str = ""
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None

    # Additional metadata
    client_ip: str | None = None
    user_agent: str | None = None
    path: str | None = None
    method: str | None = None

    # Timing
    start_time_ms: float = 0.0

    # Custom attributes
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_log_extra(self) -> dict[str, Any]:
        """Convert to extra dict for structured logging."""
        extra = {
            "request_id": self.request_id,
        }

        if self.session_id:
            extra["session_id"] = self.session_id
        if self.user_id:
            extra["user_id"] = self.user_id
        if self.agent_id:
            extra["agent_id"] = self.agent_id
        if self.trace_id:
            extra["trace_id"] = self.trace_id
        if self.span_id:
            extra["span_id"] = self.span_id
        if self.path:
            extra["path"] = self.path
        if self.method:
            extra["method"] = self.method

        return extra

    def to_dict(self) -> dict[str, Any]:
        """Convert to full dictionary."""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "path": self.path,
            "method": self.method,
            "start_time_ms": self.start_time_ms,
            "attributes": self.attributes,
        }


# ContextVar for request-scoped context
_request_context: ContextVar[RequestContext | None] = ContextVar(
    'request_context', default=None
)


def get_request_context() -> RequestContext:
    """Get the current request context.

    Returns a default context if none is set.
    """
    ctx = _request_context.get()
    if ctx is None:
        return RequestContext(request_id=str(uuid.uuid4())[:8])
    return ctx


def set_request_context(ctx: RequestContext) -> Token[RequestContext | None]:
    """Set the request context for the current async context.

    Returns:
        Token for resetting the context
    """
    return _request_context.set(ctx)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    """Reset the request context using a token."""
    _request_context.reset(token)


@contextmanager
def request_context_scope(
    request_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    **kwargs
):
    """Context manager for setting request context.

    Usage:
        with request_context_scope(request_id="abc", session_id="sess"):
            # All code here has access to the context
            ctx = get_request_context()
    """
    import time

    ctx = RequestContext(
        request_id=request_id or str(uuid.uuid4())[:8],
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        start_time_ms=time.time() * 1000,
        **kwargs
    )

    token = set_request_context(ctx)
    try:
        yield ctx
    finally:
        reset_request_context(token)


# Convenience accessors
def get_request_id() -> str:
    """Get current request ID."""
    return get_request_context().request_id


def get_session_id() -> str | None:
    """Get current session ID."""
    return get_request_context().session_id


def get_user_id() -> str | None:
    """Get current user ID."""
    return get_request_context().user_id


def get_agent_id() -> str | None:
    """Get current agent ID."""
    return get_request_context().agent_id


# Context update helpers
def set_session_id(session_id: str) -> None:
    """Update session ID in current context."""
    ctx = _request_context.get()
    if ctx:
        ctx.session_id = session_id


def set_user_id(user_id: str) -> None:
    """Update user ID in current context."""
    ctx = _request_context.get()
    if ctx:
        ctx.user_id = user_id


def set_agent_id(agent_id: str) -> None:
    """Update agent ID in current context."""
    ctx = _request_context.get()
    if ctx:
        ctx.agent_id = agent_id


def add_context_attribute(key: str, value: Any) -> None:
    """Add a custom attribute to the current context."""
    ctx = _request_context.get()
    if ctx:
        ctx.attributes[key] = value
