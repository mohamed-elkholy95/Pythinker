"""Deferred tool registry for lazy tool instantiation.

Tools registered here are not loaded until explicitly requested by name.
When instantiated, they are handed back to the caller — this registry does
not manage the active toolset; that is DynamicToolsetManager's concern.

Cache invalidation: every registration/deregistration bumps a monotonic
generation counter so ToolSearchTool can detect stale description caches.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeferredToolEntry:
    """Metadata for a lazily-loaded tool."""

    name: str
    description: str
    category: str
    factory: Callable[[], Any]  # Returns a BaseTool instance


class DeferredToolRegistry:
    """Maps tool names to (description, factory) for deferred instantiation.

    Usage:
        registry = DeferredToolRegistry()
        registry.register("canvas_draw", "Draw on canvas", "canvas", lambda: CanvasTool())
        tool = registry.instantiate("canvas_draw")  # lazy — only now is CanvasTool built
    """

    def __init__(self) -> None:
        self._entries: dict[str, DeferredToolEntry] = {}
        self._generation: int = 0  # bumped on every mutation

    @property
    def generation(self) -> int:
        """Monotonic counter — increment means descriptions may have changed."""
        return self._generation

    def register(
        self,
        name: str,
        description: str,
        category: str,
        factory: Callable[[], Any],
    ) -> None:
        """Register a deferred tool.

        Replaces any existing entry with the same name.
        """
        self._entries[name] = DeferredToolEntry(
            name=name,
            description=description,
            category=category,
            factory=factory,
        )
        self._generation += 1
        logger.debug("DeferredToolRegistry: registered %r (gen=%d)", name, self._generation)

    def deregister(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it existed."""
        if name not in self._entries:
            return False
        del self._entries[name]
        self._generation += 1
        logger.debug("DeferredToolRegistry: deregistered %r (gen=%d)", name, self._generation)
        return True

    def instantiate(self, name: str) -> Any | None:
        """Call the factory for *name* and return the result, or None if unknown."""
        entry = self._entries.get(name)
        if entry is None:
            return None
        logger.debug("DeferredToolRegistry: instantiating %r", name)
        return entry.factory()

    def search(self, query: str) -> list[DeferredToolEntry]:
        """Return entries whose name or description contains *query* (case-insensitive)."""
        q = query.lower()
        return [e for e in self._entries.values() if q in e.name.lower() or q in e.description.lower()]

    def all_entries(self) -> list[DeferredToolEntry]:
        """Return all registered entries."""
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        return name in self._entries
