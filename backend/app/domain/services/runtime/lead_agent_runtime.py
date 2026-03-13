"""LeadAgentRuntime — facade that wires all runtime middlewares into one pipeline.

Assembles the ordered middleware stack and exposes a clean lifecycle API:

    runtime = LeadAgentRuntime(session_id="abc", agent_id="agent-1")
    ctx = await runtime.initialize()      # BEFORE_RUN
    ctx = await runtime.before_step()     # BEFORE_STEP (per reasoning step)
    ctx = await runtime.after_step()      # AFTER_STEP
    ctx = await runtime.finalize()        # AFTER_RUN

Middleware execution order (important — do not change without updating tests):
    1. WorkspaceMiddleware          — session-scoped path resolution
    2. CapabilityMiddleware         — per-session capability manifest
    3. SkillDiscoveryMiddleware     — filesystem skill scanning (optional)
    4. DanglingToolCallMiddleware   — conversation history sanitisation
    5. QualityGateMiddleware        — tool filtering + grounding/coverage
    6. ClarificationMiddleware      — pending-question surface gate
    7. InsightPromotionMiddleware   — ContextGraph → Qdrant (optional)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domain.services.runtime.capability_middleware import CapabilityMiddleware
from app.domain.services.runtime.clarification_middleware import ClarificationMiddleware
from app.domain.services.runtime.dangling_tool_middleware import DanglingToolCallMiddleware
from app.domain.services.runtime.insight_promotion_middleware import (
    InsightPromotionMiddleware,
)
from app.domain.services.runtime.middleware import (
    RuntimeContext,
    RuntimeHook,
    RuntimeMiddleware,
    RuntimePipeline,
)
from app.domain.services.runtime.quality_gate_middleware import QualityGateMiddleware
from app.domain.services.runtime.skill_discovery_middleware import (
    SkillDiscoveryMiddleware,
)
from app.domain.services.runtime.workspace_middleware import WorkspaceMiddleware


def build_runtime_pipeline(
    session_id: str,
    agent_id: str,
    workspace_base: str = "/home/ubuntu",
    *,
    memory_service: Any | None = None,
    toolset_manager: Any | None = None,
    coverage_validator: Any | None = None,
    grounding_validator: Any | None = None,
    active_skills: list[str] | None = None,
    mcp_servers: list[str] | None = None,
    tool_categories: set[str] | None = None,
    model_name: str = "default",
    max_concurrent_delegates: int = 3,
    skills_root: Path | str | None = None,
) -> RuntimePipeline:
    """Construct an ordered :class:`RuntimePipeline` for a single agent session.

    Args:
        session_id: Unique identifier for the running session.
        agent_id: Identifier of the lead agent being executed.
        workspace_base: Root directory under which per-session workspaces are
            created.  Defaults to ``/home/ubuntu`` (sandbox default).
        memory_service: Optional memory service for insight promotion.
        toolset_manager: Optional tool-filtering manager for quality gates.
        coverage_validator: Optional coverage validator for quality gates.
        grounding_validator: Optional grounding validator for quality gates.
        active_skills: Skill names active for this session.
        mcp_servers: MCP server identifiers.
        tool_categories: Tool category labels.
        model_name: Language model identifier.
        max_concurrent_delegates: Delegate concurrency cap.
        skills_root: Root directory for filesystem skill scanning.

    Returns:
        A :class:`RuntimePipeline` with middlewares in the prescribed order.
    """
    middlewares: list[RuntimeMiddleware] = [
        WorkspaceMiddleware(base_dir=workspace_base),  # 1. WorkspaceMiddleware
        CapabilityMiddleware(  # 2. CapabilityMiddleware
            active_skills=active_skills,
            mcp_servers=mcp_servers,
            tool_categories=tool_categories,
            model_name=model_name,
            max_concurrent_delegates=max_concurrent_delegates,
        ),
        DanglingToolCallMiddleware(),  # 4. DanglingToolCallMiddleware
        QualityGateMiddleware(  # 5. QualityGateMiddleware
            toolset_manager=toolset_manager,
            coverage_validator=coverage_validator,
            grounding_validator=grounding_validator,
        ),
        ClarificationMiddleware(),  # 6. ClarificationMiddleware
    ]

    # 3. SkillDiscoveryMiddleware (optional) — inserted after capability middleware.
    if skills_root:
        middlewares.insert(2, SkillDiscoveryMiddleware(skills_root=skills_root))

    # 7. InsightPromotionMiddleware (optional) — always last.
    if memory_service:
        middlewares.append(InsightPromotionMiddleware(memory_service=memory_service))

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
        *,
        memory_service: Any | None = None,
        toolset_manager: Any | None = None,
        coverage_validator: Any | None = None,
        grounding_validator: Any | None = None,
        active_skills: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        tool_categories: set[str] | None = None,
        model_name: str = "default",
        max_concurrent_delegates: int = 3,
        skills_root: Path | str | None = None,
    ) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._pipeline: RuntimePipeline = build_runtime_pipeline(
            session_id=session_id,
            agent_id=agent_id,
            workspace_base=workspace_base,
            memory_service=memory_service,
            toolset_manager=toolset_manager,
            coverage_validator=coverage_validator,
            grounding_validator=grounding_validator,
            active_skills=active_skills,
            mcp_servers=mcp_servers,
            tool_categories=tool_categories,
            model_name=model_name,
            max_concurrent_delegates=max_concurrent_delegates,
            skills_root=skills_root,
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

    async def before_tool(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run the BEFORE_TOOL hook before each tool invocation.

        Args:
            ctx: Optional context override.  Uses ``self._ctx`` when omitted.

        Returns:
            The (possibly mutated) context after all BEFORE_TOOL handlers.

        Raises:
            RuntimeError: If no context is available (runtime not initialised
                and no override supplied).
        """
        active_ctx = ctx if ctx is not None else self._ctx
        if active_ctx is None:
            raise RuntimeError("Runtime not initialized")
        active_ctx = await self._pipeline.run_hook(RuntimeHook.before_tool, active_ctx)
        self._ctx = active_ctx
        return active_ctx

    async def after_tool(self, ctx: RuntimeContext | None = None) -> RuntimeContext:
        """Run the AFTER_TOOL hook after each tool invocation.

        Args:
            ctx: Optional context override.  Uses ``self._ctx`` when omitted.

        Returns:
            The (possibly mutated) context after all AFTER_TOOL handlers.

        Raises:
            RuntimeError: If no context is available (runtime not initialised
                and no override supplied).
        """
        active_ctx = ctx if ctx is not None else self._ctx
        if active_ctx is None:
            raise RuntimeError("Runtime not initialized")
        active_ctx = await self._pipeline.run_hook(RuntimeHook.after_tool, active_ctx)
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
