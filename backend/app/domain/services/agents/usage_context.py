"""Usage context management for tracking LLM calls by user/session.

This module provides context variables that allow LLM providers to know
which user and session a call belongs to for usage tracking.

Usage:
    # At the start of execution
    set_usage_context(user_id="user123", session_id="session456")

    # LLM providers can retrieve context
    ctx = get_usage_context()
    if ctx:
        user_id, session_id = ctx

    # At the end of execution
    clear_usage_context()
"""
from contextvars import ContextVar
from typing import Optional, Tuple, NamedTuple
from dataclasses import dataclass


@dataclass
class UsageContext:
    """Context for tracking usage attribution."""
    user_id: str
    session_id: str
    model_override: Optional[str] = None  # Override model name for billing


# Context variable for usage tracking
_usage_context: ContextVar[Optional[UsageContext]] = ContextVar(
    "usage_context",
    default=None
)


def set_usage_context(
    user_id: str,
    session_id: str,
    model_override: Optional[str] = None
) -> None:
    """Set the current usage context.

    Call this at the start of an execution to attribute LLM calls
    to a specific user and session.

    Args:
        user_id: The user ID to attribute usage to
        session_id: The session ID to attribute usage to
        model_override: Optional model name override for billing
    """
    ctx = UsageContext(
        user_id=user_id,
        session_id=session_id,
        model_override=model_override
    )
    _usage_context.set(ctx)


def get_usage_context() -> Optional[UsageContext]:
    """Get the current usage context.

    Returns:
        UsageContext if set, None otherwise
    """
    return _usage_context.get()


def clear_usage_context() -> None:
    """Clear the current usage context.

    Call this at the end of an execution.
    """
    _usage_context.set(None)


class UsageContextManager:
    """Context manager for usage tracking.

    Usage:
        with UsageContextManager(user_id="user123", session_id="session456"):
            # LLM calls within this block will be attributed to this user/session
            await llm.chat(...)
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        model_override: Optional[str] = None
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.model_override = model_override
        self._previous_context: Optional[UsageContext] = None

    def __enter__(self) -> "UsageContextManager":
        self._previous_context = get_usage_context()
        set_usage_context(
            user_id=self.user_id,
            session_id=self.session_id,
            model_override=self.model_override
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._previous_context:
            _usage_context.set(self._previous_context)
        else:
            clear_usage_context()

    async def __aenter__(self) -> "UsageContextManager":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)
