import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.domain.models.session import Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository

logger = logging.getLogger(__name__)


async def _has_active_chat_stream(session_id: str) -> bool:
    from app.domain.services.stream_guard import has_active_stream

    return await has_active_stream(session_id=session_id, endpoint="chat")


class StaleSessionCleanupPolicy:
    """Applies bounded stale-session cleanup before a new session is created."""

    DEFAULT_MIN_AGE_SECONDS = 30.0
    DEFAULT_PER_SESSION_TIMEOUT_SECONDS = 10.0
    DEFAULT_TOTAL_TIMEOUT_SECONDS = 12.0

    def __init__(
        self,
        session_repository: SessionRepository,
        stop_session: Callable[[str], Awaitable[None]],
        close_browser_for_sandbox: Callable[[str], Awaitable[None]],
        *,
        stale_min_age_seconds: float | None = None,
        per_session_timeout_seconds: float = DEFAULT_PER_SESSION_TIMEOUT_SECONDS,
        total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
    ) -> None:
        self._session_repository = session_repository
        self._stop_session = stop_session
        self._close_browser_for_sandbox = close_browser_for_sandbox
        self._stale_min_age_seconds = stale_min_age_seconds
        self._per_session_timeout_seconds = max(0.001, per_session_timeout_seconds)
        self._total_timeout_seconds = max(0.001, total_timeout_seconds)

    def _resolve_stale_age_seconds(self) -> float:
        if self._stale_min_age_seconds is not None:
            return max(0.0, self._stale_min_age_seconds)
        return max(
            0.0,
            float(getattr(get_settings(), "stale_session_autostop_min_age_seconds", self.DEFAULT_MIN_AGE_SECONDS)),
        )

    async def _collect_stale_sessions(self, user_id: str) -> list[Session]:
        active_statuses = {SessionStatus.RUNNING, SessionStatus.INITIALIZING, SessionStatus.PENDING}
        stale_cutoff = datetime.now(UTC) - timedelta(seconds=self._resolve_stale_age_seconds())
        sessions = await self._session_repository.find_by_user_id(user_id)

        stale_sessions: list[Session] = []
        for session in sessions:
            if session.status not in active_statuses:
                continue

            if await _has_active_chat_stream(session.id):
                logger.info(
                    "Skipping auto-stop for session %s (status=%s): active chat stream detected",
                    session.id,
                    session.status,
                )
                continue

            updated_at = session.updated_at
            if updated_at is not None:
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=UTC)
                if updated_at >= stale_cutoff:
                    logger.debug(
                        "Skipping auto-stop for recent session %s (status=%s, updated_at=%s)",
                        session.id,
                        session.status,
                        updated_at.isoformat(),
                    )
                    continue

            stale_sessions.append(session)

        return stale_sessions

    async def _stop_stale_session(self, user_id: str, session: Session) -> None:
        try:
            async with asyncio.timeout(self._per_session_timeout_seconds):
                logger.info(
                    "Auto-stopping stale session %s (status=%s) for user %s",
                    session.id,
                    session.status,
                    user_id,
                )
                if session.sandbox_id:
                    await self._close_browser_for_sandbox(session.sandbox_id)
                await self._stop_session(session.id)
        except TimeoutError:
            logger.warning(
                "Auto-stop of stale session %s timed out after %.3fs",
                session.id,
                self._per_session_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Failed to auto-stop stale session %s: %s", session.id, exc)

    async def cleanup_for_user(self, user_id: str) -> None:
        try:
            stale_sessions = await self._collect_stale_sessions(user_id)
            if not stale_sessions:
                return

            try:
                async with asyncio.timeout(self._total_timeout_seconds):
                    await asyncio.gather(*(self._stop_stale_session(user_id, session) for session in stale_sessions))
            except TimeoutError:
                logger.warning(
                    "Stale session cleanup exceeded %.3fs cap; %d session(s) may not have been fully stopped",
                    self._total_timeout_seconds,
                    len(stale_sessions),
                )

            logger.info("Cleaned up %d stale session(s) for user %s", len(stale_sessions), user_id)
        except Exception as exc:
            logger.warning("Stale session cleanup failed for user %s: %s", user_id, exc)
