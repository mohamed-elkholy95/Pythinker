"""MCP Connection Registry — singleton cache of MCPClientManager per user.

Provides centralized access to active MCP sessions for REST endpoints and
health monitoring. Entries auto-evict after idle timeout (default 10 min).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.services.tools.mcp import MCPClientManager, MCPHealthMonitor

logger = logging.getLogger(__name__)

# Default idle timeout before evicting an entry (seconds)
_DEFAULT_IDLE_TIMEOUT = 600.0  # 10 minutes


@dataclass
class _RegistryEntry:
    """Internal wrapper around a registered MCPClientManager."""

    manager: "MCPClientManager"
    health_monitor: "MCPHealthMonitor | None" = None
    last_access: float = field(default_factory=time.monotonic)


class MCPRegistry:
    """Per-user MCPClientManager registry with idle timeout eviction.

    Thread-safe for the single-threaded asyncio event loop (no locking needed).
    """

    def __init__(self, idle_timeout: float = _DEFAULT_IDLE_TIMEOUT) -> None:
        self._entries: dict[str, _RegistryEntry] = {}
        self._idle_timeout = idle_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        user_id: str,
        manager: "MCPClientManager",
        health_monitor: "MCPHealthMonitor | None" = None,
    ) -> None:
        """Register (or replace) a user's MCPClientManager."""
        self._entries[user_id] = _RegistryEntry(
            manager=manager,
            health_monitor=health_monitor,
        )
        logger.debug("MCPRegistry: registered user=%s", user_id)

    def get(self, user_id: str) -> _RegistryEntry | None:
        """Look up entry for *user_id*, refreshing its last-access timestamp."""
        entry = self._entries.get(user_id)
        if entry is not None:
            entry.last_access = time.monotonic()
        return entry

    def unregister(self, user_id: str) -> None:
        """Remove a user's entry (call on task/session teardown)."""
        removed = self._entries.pop(user_id, None)
        if removed:
            logger.debug("MCPRegistry: unregistered user=%s", user_id)

    def cleanup_idle(self) -> list[str]:
        """Evict entries that have been idle longer than *idle_timeout*.

        Returns the list of evicted user IDs.
        """
        now = time.monotonic()
        stale = [uid for uid, entry in self._entries.items() if (now - entry.last_access) > self._idle_timeout]
        for uid in stale:
            del self._entries[uid]
            logger.info("MCPRegistry: evicted idle user=%s", uid)
        return stale

    @property
    def active_count(self) -> int:
        return len(self._entries)

    def all_entries(self) -> dict[str, _RegistryEntry]:
        """Return a snapshot of all registry entries (read-only intent)."""
        return dict(self._entries)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    """Return the process-wide MCPRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry()
    return _registry
