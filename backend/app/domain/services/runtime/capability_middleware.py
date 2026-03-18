"""Capability middleware — builds a CapabilityManifest and attaches it to context.

Runs during ``before_run`` so all downstream middlewares and prompt builders
can read the typed manifest from ``ctx.metadata["capability_manifest"]``
without re-computing it.
"""

from __future__ import annotations

from app.domain.models.capability_manifest import (
    CapabilityManifest,
    ModelCapabilities,
    SandboxState,
)
from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class CapabilityMiddleware(RuntimeMiddleware):
    """Runtime middleware that builds and stores the per-session CapabilityManifest.

    All constructor parameters are optional so the middleware can be created
    with sensible defaults for sessions that have minimal configuration.

    Args:
        active_skills: Names of skill packages active for this session.
        mcp_servers: MCP server identifiers connected for this session.
        tool_categories: Set of tool-category labels (e.g. ``{"browser", "file"}``).
        model_name: Identifier of the language model in use.
        supports_vision: Whether the model accepts image inputs.
        supports_thinking: Whether the model emits extended thinking tokens.
        max_tokens: Maximum output token budget for the model.
        sandbox_active: Whether a Docker sandbox is running.
        sandbox_id: Container / sandbox identifier (``None`` if inactive).
        max_concurrent_delegates: Delegate concurrency limit for this session.
    """

    def __init__(
        self,
        *,
        active_skills: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        tool_categories: set[str] | None = None,
        model_name: str = "default",
        supports_vision: bool = False,
        supports_thinking: bool = False,
        max_tokens: int = 4096,
        sandbox_active: bool = False,
        sandbox_id: str | None = None,
        max_concurrent_delegates: int = 3,
    ) -> None:
        self._active_skills = active_skills or []
        self._mcp_servers = mcp_servers or []
        self._tool_categories = tool_categories or set()
        self._model_name = model_name
        self._supports_vision = supports_vision
        self._supports_thinking = supports_thinking
        self._max_tokens = max_tokens
        self._sandbox_active = sandbox_active
        self._sandbox_id = sandbox_id
        self._max_concurrent_delegates = max_concurrent_delegates

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        """Build CapabilityManifest from stored config and attach to ctx."""
        manifest = CapabilityManifest(
            session_id=ctx.session_id,
            active_skills=list(self._active_skills),
            mcp_servers=list(self._mcp_servers),
            tool_categories=set(self._tool_categories),
            model=ModelCapabilities(
                name=self._model_name,
                supports_vision=self._supports_vision,
                supports_thinking=self._supports_thinking,
                max_tokens=self._max_tokens,
            ),
            sandbox=SandboxState(
                active=self._sandbox_active,
                sandbox_id=self._sandbox_id,
            ),
            max_concurrent_delegates=self._max_concurrent_delegates,
        )
        ctx.metadata["capability_manifest"] = manifest
        return ctx
