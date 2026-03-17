from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 7
DEFAULT_MAX_STATES_PER_USER = 5
DEFAULT_BASE_DIR = Path("/tmp/pythinker_browser_login_state")


class BrowserLoginStateStore:
    """File-backed storage for browser auth state snapshots."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
        max_states_per_user: int = DEFAULT_MAX_STATES_PER_USER,
    ) -> None:
        self._base_dir = Path(base_dir) if base_dir else DEFAULT_BASE_DIR
        self._ttl = timedelta(days=max(1, ttl_days))
        self._max_states_per_user = max(1, max_states_per_user)
        self._ensure_dir(self._base_dir)

    @staticmethod
    def _safe_hash(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()[:24]

    def _user_dir(self, user_id: str) -> Path:
        return self._base_dir / f"user_{self._safe_hash(user_id)}"

    def _state_path(self, user_id: str, session_id: str) -> Path:
        user_dir = self._user_dir(user_id)
        return user_dir / f"session_{self._safe_hash(session_id)}.json"

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o700)

    def _is_expired(self, path: Path, now: datetime) -> bool:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return True
        return now - mtime > self._ttl

    def _cleanup_expired_for_user(self, user_id: str) -> None:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return
        now = datetime.now(UTC)
        for file_path in user_dir.glob("session_*.json"):
            if self._is_expired(file_path, now):
                try:
                    file_path.unlink(missing_ok=True)
                except OSError:
                    logger.debug("Failed to remove expired browser state file: %s", file_path)

    def _trim_user_state_limit(self, user_id: str) -> None:
        user_dir = self._user_dir(user_id)
        if not user_dir.exists():
            return

        files = sorted(
            user_dir.glob("session_*.json"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0.0,
            reverse=True,
        )
        for stale in files[self._max_states_per_user :]:
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to prune browser state file: %s", stale)

    def save_state(self, user_id: str, session_id: str, storage_state: dict[str, Any]) -> bool:
        if not user_id or not session_id:
            return False

        try:
            self._cleanup_expired_for_user(user_id)
            user_dir = self._user_dir(user_id)
            self._ensure_dir(user_dir)

            payload = {
                "user_id": user_id,
                "session_id": session_id,
                "saved_at": datetime.now(UTC).isoformat(),
                "storage_state": storage_state,
            }
            target = self._state_path(user_id, session_id)
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(payload), encoding="utf-8")
            with contextlib.suppress(OSError):
                os.chmod(temp, 0o600)
            temp.replace(target)
            with contextlib.suppress(OSError):
                os.chmod(target, 0o600)

            self._trim_user_state_limit(user_id)
            return True
        except Exception as e:
            logger.warning("Failed to persist browser login state for session %s: %s", session_id, e)
            return False

    def load_state(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        if not user_id or not session_id:
            return None

        self._cleanup_expired_for_user(user_id)
        path = self._state_path(user_id, session_id)
        if not path.exists():
            return None

        if self._is_expired(path, datetime.now(UTC)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed removing expired browser login state: %s", path)
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("user_id") != user_id or payload.get("session_id") != session_id:
                return None
            storage_state = payload.get("storage_state")
            return storage_state if isinstance(storage_state, dict) else None
        except Exception as e:
            logger.warning("Failed to load browser login state for session %s: %s", session_id, e)
            return None

    def delete_state(self, user_id: str, session_id: str) -> None:
        if not user_id or not session_id:
            return
        path = self._state_path(user_id, session_id)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to delete browser login state for session %s", session_id)
