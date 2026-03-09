"""LeadAgentRuntime — facade that wires all runtime middlewares into one pipeline.

Assembles the ordered middleware stack and exposes a clean lifecycle API:

    runtime = LeadAgentRuntime(session_id="abc", agent_id="agent-1")
    ctx = await runtime.initialize()      # BEFORE_RUN
    ctx = await runtime.before_step()     # BEFORE_STEP (per reasoning step)
    ctx = await runtime.after_step()      # AFTER_STEP
    ctx = await runtime.finalize()        # AFTER_RUN

Middleware execution order (important — do not change without updating tests):
    1. WorkspaceMiddleware   — session-scoped path resolution
    2. DanglingToolCallMiddleware — conversation history sanitisation
    3. ClarificationMiddleware   — pending-question surface gate
"""

from __future__ import annotations

from app.domain.services.runtime.clarification_middleware import ClarificationMiddleware
from app.domain.services.runtime.dangling_tool_middleware import DanglingToolCallMiddleware
from app.domain.services.runtime.middleware import (
    RuntimeContext,
    RuntimeHook,
    RuntimePipeline,
)
from app.domain.services.runtime.workspace_middleware import WorkspaceMiddleware


def build_runtime_pipeline(
    session_id: str,
    agent_id: str,
    workspace_base: str = "/home/ubuntu",
) -> RuntimePipeline:
    """Construct an ordered :class:`RuntimePipeline` for a single agent session.

    Args:
        session_id: Unique identifier for the running session.
        agent_id: Identifier of the lead agent being executed.
        workspace_base: Root directory under which per-session workspaces are
            created.  Defaults to ``/home/ubuntu`` (sandbox default).

    Returns:
        A :class:`RuntimePipeline` with middlewares in the prescribed order.
    """
    middlewares = [
        WorkspaceMiddleware(base_dir=workspace_base),
        DanglingToolCallMiddleware(),
        ClarificationMiddleware(),
    ]
    return RuntimePipeline(middlewares=middlewares)


class LeadAgentRuntime:
    """Facade that drives the full agent lifecycle through the middleware pipeline.

    The runtime owns a single :class:`RuntimeContext` that is created during
    :meth:`initialize` and threaded through every subsequent lifecycle call.
    All public methods accept an optional *ctx* parameter so callers can supply
    an override context (useful in tests), but the stored ``self._ctx`` is
    always updated to whatever the pipeline returns.

    Raises:
        RuntimeError: If :meth:`before_step`, :meth:`after_step`, or
            :meth:`finalize` are called before :meth:`initialize`.
    """

    __slots__ = ("_agent_id", "_ctx", "_pipeline", "_session_id")

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        workspace_base: str = "/home/ubuntu",
    ) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._pipeline: RuntimePipeline = build_runtime_pipeline(
            session_id=session_id,
            agent_id=agent_id,
            workspace_base=workspace_base,
        )
        self._ctx: RuntimeContext | None = None

    # ──────────────────────────── Lifecycle ──────────────────────────────────

    async def initialize(self) -> RuntimeContext:
        """Create the shared context and run the BEFORE_RUN hook on all middlewares.

        Must be called exactly once before any step methods.

        Returns:
            The initialised :class:`RuntimeContext` after all middlewares have
            had a chance to populate it (e.g. workspace paths, contracts).
        """
        ctx = RuntimeContext(session_id=self._session_id, agent_id=self._agent_id)
        ctx = await self._pipeline.run_hook(RuntimeHook.before_run, ctx)
        self._ctx = ctx
        return ctx

    async def before_step(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run the BEFORE_STEP hook before each agent reasoning step.

        Args:
            ctx: Optional context override.  Uses ``self._ctx`` when omitted.

        Returns:
            The (possibly mutated) context after all BEFORE_STEP handlers.

        Raises:
            RuntimeError: If no context is available (runtime not initialised
                and no override supplied).
        """
        active_ctx = ctx if ctx is not None else self._ctx
        if active_ctx is None:
            raise RuntimeError("Runtime not initialized")
        active_ctx = await self._pipeline.run_hook(RuntimeHook.before_step, active_ctx)
        self._ctx = active_ctx
        return active_ctx

    async def after_step(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run the AFTER_STEP hook after each agent reasoning step.

        Args:
            ctx: Optional context override.  Uses ``self._ctx`` when omitted.

        Returns:
            The (possibly mutated) context after all AFTER_STEP handlers.

        Raises:
            RuntimeError: If no context is available (runtime not initialised
                and no override supplied).
        """
        active_ctx = ctx if ctx is not None else self._ctx
        if active_ctx is None:
            raise RuntimeError("Runtime not initialized")
        active_ctx = await self._pipeline.run_hook(RuntimeHook.after_step, active_ctx)
        self._ctx = active_ctx
        return active_ctx

    async def finalize(self) -> RuntimeContext:
        """Run the AFTER_RUN hook to clean up session resources.

        Returns:
            The finalised :class:`RuntimeContext`.

        Raises:
            RuntimeError: If the runtime has not been initialised.
        """
        if self._ctx is None:
            raise RuntimeError("Runtime not initialized")
        self._ctx = await self._pipeline.run_hook(RuntimeHook.after_run, self._ctx)
        return self._ctx

    # ──────────────────────────── Properties ─────────────────────────────────

    @property
    def context(self) -> RuntimeContext | None:
        """The current shared context, or ``None`` before :meth:`initialize`."""
        return self._ctx
