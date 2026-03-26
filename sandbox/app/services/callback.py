"""Sandbox → Backend callback client.

Fire-and-forget HTTP client for reporting sandbox events, progress, and
resource requests back to the backend.  No-op when RUNTIME_API_HOST is unset.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class CallbackClient:
    """Lightweight HTTP client for sandbox → backend callbacks."""

    def __init__(self) -> None:
        self.enabled = bool(settings.RUNTIME_API_HOST and settings.RUNTIME_API_TOKEN)
        self._client: Optional[httpx.AsyncClient] = None
        if self.enabled:
            self._client = httpx.AsyncClient(
                base_url=settings.RUNTIME_API_HOST or "",
                timeout=_TIMEOUT,
                headers={
                    "X-Sandbox-Callback-Token": settings.RUNTIME_API_TOKEN or "",
                    "Content-Type": "application/json",
                },
            )

    async def report_event(
        self, event_type: str, details: dict[str, Any], session_id: str | None = None
    ) -> None:
        """Report a sandbox event (crash, OOM, timeout, ready)."""
        if not self.enabled:
            return
        await self._post(
            "/api/v1/sandbox/callback/event",
            {
                "type": event_type,
                "details": details,
                "session_id": session_id,
            },
        )

    async def report_progress(
        self,
        session_id: str,
        step: str,
        percent: int,
        message: str = "",
    ) -> None:
        """Report progress on an ongoing operation."""
        if not self.enabled:
            return
        await self._post(
            "/api/v1/sandbox/callback/progress",
            {
                "session_id": session_id,
                "step": step,
                "percent": percent,
                "message": message,
            },
        )

    async def request_resource(
        self, resource_type: str, params: dict[str, Any] | None = None
    ) -> Optional[dict[str, Any]]:
        """Request a resource from the backend (upload URL, secret, etc.)."""
        if not self.enabled:
            return None
        return await self._post(
            "/api/v1/sandbox/callback/request",
            {
                "type": resource_type,
                "params": params or {},
            },
        )

    async def _post(
        self, path: str, payload: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Fire-and-forget POST. Swallows all errors."""
        if not self._client:
            return None
        try:
            response = await self._client.post(path, json=payload)
            if response.status_code >= 400:
                logger.warning("Callback %s returned %d", path, response.status_code)
                return None
            return response.json()
        except Exception:
            logger.debug("Callback to %s failed (fire-and-forget)", path, exc_info=True)
            return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client:
            await self._client.aclose()


# Singleton — initialized once at import time
callback_client = CallbackClient()
