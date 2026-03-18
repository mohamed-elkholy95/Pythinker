"""Cache-aside wrapper for session repository.

Adds a Redis cache layer around hot session lookups to reduce MongoDB load.
Falls back to the underlying repository on cache miss or Redis unavailability.
"""

import contextlib
import logging
from datetime import datetime

from app.domain.models.event import BaseEvent
from app.domain.models.session import Session
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

    # --- Read methods with cache-aside ---

    async def get_by_id(self, session_id: str) -> Session:
        """Get session by ID, checking cache first."""
        key = self._cache_key(session_id)

        # Try cache
        cached = await self._cache.get(key)
        if cached is not None:
            with contextlib.suppress(Exception):
                return Session.model_validate(cached)

        # Cache miss — fetch from MongoDB
        session = await self._inner.get_by_id(session_id)

        # Populate cache
        with contextlib.suppress(Exception):
            await self._cache.set(key, session.model_dump(mode="json"), ttl=_get_session_ttl())

        return session

    # --- Write methods (delegate + invalidate) ---

    async def create(self, session: Session) -> Session:
        return await self._inner.create(session)

    async def update(self, session: Session) -> Session:
        result = await self._inner.update(session)
        await self._invalidate(session.session_id)
        return result

    async def delete(self, session_id: str) -> bool:
        result = await self._inner.delete(session_id)
        await self._invalidate(session_id)
        return result

    # --- Delegated methods (no caching needed) ---

    async def get_by_user(self, user_id: str, limit: int = 50, offset: int = 0) -> list[Session]:
        return await self._inner.get_by_user(user_id, limit=limit, offset=offset)

    async def update_status(self, session_id: str, status: object) -> None:
        await self._inner.update_status(session_id, status)
        await self._invalidate(session_id)

    async def update_by_id(self, session_id: str, **updates: object) -> None:
        await self._inner.update_by_id(session_id, **updates)
        await self._invalidate(session_id)

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        await self._inner.add_event(session_id, event)
        await self._invalidate(session_id)

    async def get_events_paginated(self, session_id: str, offset: int = 0, limit: int = 100) -> list[BaseEvent]:
        return await self._inner.get_events_paginated(session_id, offset=offset, limit=limit)

    async def get_events_in_range(self, session_id: str, start_time: datetime, end_time: datetime) -> list[BaseEvent]:
        return await self._inner.get_events_in_range(session_id, start_time, end_time)

    async def get_event_count(self, session_id: str) -> int:
        return await self._inner.get_event_count(session_id)

    async def get_event_by_sequence(self, session_id: str, sequence: int) -> BaseEvent | None:
        return await self._inner.get_event_by_sequence(session_id, sequence)
