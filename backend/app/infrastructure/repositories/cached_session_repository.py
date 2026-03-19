"""Cache-aside wrapper for session repository.

Adds a Redis cache layer around hot session lookups to reduce MongoDB load.
Falls back to the underlying repository on cache miss or Redis unavailability.
"""

import contextlib
import logging
from datetime import datetime
from typing import Any

from app.domain.models.event import BaseEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, PendingAction, PendingActionStatus, Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.external.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)

# Cache key patterns
_SESSION_KEY = "session:{session_id}"


def _get_session_ttl() -> int:
    """Get session cache TTL from settings."""
    from app.core.config import get_settings

    return get_settings().session_cache_ttl_seconds


class CachedSessionRepository(SessionRepository):
    """Cache-aside wrapper that caches hot session data in Redis.

    Delegates all writes directly to the underlying repository and
    invalidates the cache entry. Reads check Redis first, falling back
    to MongoDB on cache miss.
    """

    def __init__(self, inner: SessionRepository, cache: RedisCache):
        self._inner = inner
        self._cache = cache

    def _cache_key(self, session_id: str) -> str:
        return _SESSION_KEY.format(session_id=session_id)

    async def _invalidate(self, session_id: str) -> None:
        """Remove session from cache after a write."""
        with contextlib.suppress(Exception):
            await self._cache.delete(self._cache_key(session_id))

    async def _cache_session(self, session: Session) -> None:
        """Populate cache with a session."""
        with contextlib.suppress(Exception):
            key = self._cache_key(session.id)
            await self._cache.set(key, session.model_dump(mode="json"), ttl=_get_session_ttl())

    async def _get_cached(self, session_id: str) -> Session | None:
        """Try to get a session from cache."""
        with contextlib.suppress(Exception):
            cached = await self._cache.get(self._cache_key(session_id))
            if cached is not None:
                return Session.model_validate(cached)
        return None

    # --- Write methods (delegate + invalidate) ---

    async def save(self, session: Session) -> None:
        await self._inner.save(session)
        await self._invalidate(session.id)

    async def delete(self, session_id: str) -> None:
        await self._inner.delete(session_id)
        await self._invalidate(session_id)

    async def update_title(self, session_id: str, title: str) -> None:
        await self._inner.update_title(session_id, title)
        await self._invalidate(session_id)

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        await self._inner.update_latest_message(session_id, message, timestamp)
        await self._invalidate(session_id)

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        await self._inner.add_event(session_id, event)
        await self._invalidate(session_id)

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        await self._inner.add_file(session_id, file_info)
        await self._invalidate(session_id)

    async def remove_file(self, session_id: str, file_id: str) -> None:
        await self._inner.remove_file(session_id, file_id)
        await self._invalidate(session_id)

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        await self._inner.update_status(session_id, status)
        await self._invalidate(session_id)

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        await self._inner.update_unread_message_count(session_id, count)
        await self._invalidate(session_id)

    async def increment_unread_message_count(self, session_id: str) -> None:
        await self._inner.increment_unread_message_count(session_id)
        await self._invalidate(session_id)

    async def decrement_unread_message_count(self, session_id: str) -> None:
        await self._inner.decrement_unread_message_count(session_id)
        await self._invalidate(session_id)

    async def update_shared_status(self, session_id: str, is_shared: bool) -> None:
        await self._inner.update_shared_status(session_id, is_shared)
        await self._invalidate(session_id)

    async def update_mode(self, session_id: str, mode: AgentMode) -> None:
        await self._inner.update_mode(session_id, mode)
        await self._invalidate(session_id)

    async def update_pending_action(
        self,
        session_id: str,
        pending_action: PendingAction | None,
        status: PendingActionStatus | None,
    ) -> None:
        await self._inner.update_pending_action(session_id, pending_action, status)
        await self._invalidate(session_id)

    async def update_by_id(self, session_id: str, updates: dict[str, Any]) -> None:
        await self._inner.update_by_id(session_id, updates)
        await self._invalidate(session_id)

    # --- Read methods with cache-aside ---

    async def find_by_id(self, session_id: str) -> Session | None:
        cached = await self._get_cached(session_id)
        if cached is not None:
            return cached
        session = await self._inner.find_by_id(session_id)
        if session is not None:
            await self._cache_session(session)
        return session

    async def find_by_id_full(self, session_id: str) -> Session | None:
        # Full payloads not cached (too large with events/files)
        return await self._inner.find_by_id_full(session_id)

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        return await self._inner.find_by_user_id(user_id)

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Session | None:
        cached = await self._get_cached(session_id)
        if cached is not None and cached.user_id == user_id:
            return cached
        session = await self._inner.find_by_id_and_user_id(session_id, user_id)
        if session is not None:
            await self._cache_session(session)
        return session

    async def find_by_id_and_user_id_full(self, session_id: str, user_id: str) -> Session | None:
        return await self._inner.find_by_id_and_user_id_full(session_id, user_id)

    async def get_file_by_path(self, session_id: str, file_path: str) -> FileInfo | None:
        return await self._inner.get_file_by_path(session_id, file_path)

    async def get_all(self) -> list[Session]:
        return await self._inner.get_all()

    # --- Timeline query methods (delegated, no caching) ---

    async def get_events_paginated(self, session_id: str, offset: int = 0, limit: int = 100) -> list[BaseEvent]:
        return await self._inner.get_events_paginated(session_id, offset=offset, limit=limit)

    async def get_events_in_range(self, session_id: str, start_time: datetime, end_time: datetime) -> list[BaseEvent]:
        return await self._inner.get_events_in_range(session_id, start_time, end_time)

    async def get_event_count(self, session_id: str) -> int:
        return await self._inner.get_event_count(session_id)

    async def get_event_by_sequence(self, session_id: str, sequence: int) -> BaseEvent | None:
        return await self._inner.get_event_by_sequence(session_id, sequence)

    async def get_event_by_id(self, session_id: str, event_id: str) -> BaseEvent | None:
        return await self._inner.get_event_by_id(session_id, event_id)
