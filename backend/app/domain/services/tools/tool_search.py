"""ToolSearchTool — agent-accessible tool discovery with description caching.

Allows the agent to search for available (active + deferred) tools by keyword.
Memoizes description snapshots keyed by DeferredToolRegistry.generation so the
cache is invalidated automatically when deferred tools are registered/removed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool
from app.domain.services.tools.deferred_registry import DeferredToolRegistry

logger = logging.getLogger(__name__)


class ToolSearchTool(BaseTool):
    """Search available tools by keyword.

    Integrates with DeferredToolRegistry so deferred tools are discoverable
    before they are instantiated.  Description snapshots are memoized and
    automatically invalidated when the registry generation changes.
    """

    name: str = "tool_search"

    def __init__(
        self,
        active_tools: list[BaseTool] | None = None,
        deferred_registry: DeferredToolRegistry | None = None,
    ) -> None:
        super().__init__(
            defaults=ToolDefaults(
                is_read_only=True,
                is_concurrency_safe=True,
                category="system",
                user_facing_name="Tool Search",
            )
        )
        self._active_tools: list[BaseTool] = active_tools or []
        self._deferred_registry: DeferredToolRegistry = (
            deferred_registry if deferred_registry is not None else DeferredToolRegistry()
        )

        # Description cache: generation → list[dict]
        self._cache_generation: int = -1
        self._cached_descriptions: list[dict[str, Any]] = []

    def update_active_tools(self, tools: list[BaseTool]) -> None:
        """Replace the active tool list and invalidate the description cache."""
        self._active_tools = tools
        self._cache_generation = -1  # force rebuild on next search

    # ── Internal helpers ──────────────────────────────────────────────

    def _build_descriptions(self) -> list[dict[str, Any]]:
        """Build a flat list of {name, description, category, source} dicts.

        Merges active tool schemas and deferred registry entries.
        Called only when the cache is stale.
        """
        descriptions: list[dict[str, Any]] = []

        # Active tools
        for tool_instance in self._active_tools:
            for schema in tool_instance.get_tools():
                fn = schema.get("function", {})
                descriptions.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "category": (getattr(tool_instance, "_defaults", None) and tool_instance._defaults.category)
                        or "general",
                        "source": "active",
                    }
                )

        # Deferred tools
        descriptions.extend(
            {
                "name": entry.name,
                "description": entry.description,
                "category": entry.category,
                "source": "deferred",
            }
            for entry in self._deferred_registry.all_entries()
        )

        return descriptions

    def _get_descriptions(self) -> list[dict[str, Any]]:
        """Return cached descriptions, rebuilding if the registry changed."""
        current_gen = self._deferred_registry.generation
        if self._cache_generation != current_gen:
            self._cached_descriptions = self._build_descriptions()
            self._cache_generation = current_gen
            logger.debug(
                "ToolSearchTool: rebuilt description cache (%d entries, gen=%d)",
                len(self._cached_descriptions),
                current_gen,
            )
        return self._cached_descriptions

    # ── Exposed tool ──────────────────────────────────────────────────

    @tool(
        name="tool_search",
        description=(
            "Search for available tools by keyword. "
            "Returns matching tool names, descriptions, and categories. "
            "Use this to discover tools before attempting to call them."
        ),
        parameters={
            "query": {
                "type": "string",
                "description": "Keyword(s) to search for in tool names and descriptions.",
            },
            "category": {
                "type": "string",
                "description": "Optional: filter results to this category (e.g. 'shell', 'file', 'search').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 20, max 50).",
            },
        },
        required=["query"],
        is_read_only=True,
        is_concurrency_safe=True,
    )
    async def tool_search(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> ToolResult:
        """Search for available tools by keyword.

        Args:
            query: Keyword(s) to search for.
            category: Optional category filter.
            limit: Maximum results (capped at 50).

        Returns:
            ToolResult with JSON list of matching tools.
        """
        if not query or not query.strip():
            return ToolResult(success=False, message="'query' must not be empty.")

        limit = min(max(1, limit), 50)
        q = query.lower().strip()

        descriptions = self._get_descriptions()

        matches: list[dict[str, Any]] = []
        for entry in descriptions:
            name = entry.get("name", "")
            desc = entry.get("description", "")
            cat = entry.get("category", "")

            if category and cat != category:
                continue

            if q in name.lower() or q in desc.lower():
                matches.append(
                    {
                        "name": name,
                        "description": desc,
                        "category": cat,
                        "source": entry.get("source", "active"),
                    }
                )
            if len(matches) >= limit:
                break

        if not matches:
            return ToolResult(
                success=True,
                message=f"No tools found matching '{query}'.",
                data={"results": [], "query": query, "total": 0},
            )

        return ToolResult(
            success=True,
            message=json.dumps(matches, indent=2),
            data={"results": matches, "query": query, "total": len(matches)},
        )
