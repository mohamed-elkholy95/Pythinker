"""Manage Scrapling AsyncStealthySession instances for stealth fetches."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Literal, cast

from app.domain.external.stealth_types import FetchOptions, FetchResult, StealthMode

if TYPE_CHECKING:
    from scrapling.fetchers import AsyncStealthySession, ProxyRotator

    from .proxy_health_tracker import ProxyHealthTracker

logger = logging.getLogger(__name__)

_WAIT_SELECTOR_STATES = {"attached", "detached", "hidden", "visible"}


class StealthSessionManager:
    """Pool AsyncStealthySession instances keyed by proxy affinity."""

    def __init__(
        self,
        *,
        session_timeout: int = 30000,
        network_idle: bool = True,
        canvas_noise: bool = True,
        webrtc_block: bool = True,
        webgl_enabled: bool = True,
        google_referer: bool = True,
        max_pages: int = 3,
        cloudflare_timeout: int = 60,
        disable_resources: bool = False,
        shared_cdp_url: str | None = None,
        health_tracker: ProxyHealthTracker | None = None,
        idle_cleanup_interval: int = 60,
        idle_threshold_seconds: int = 300,
    ) -> None:
        self._session_timeout = session_timeout
        self._network_idle = network_idle
        self._canvas_noise = canvas_noise
        self._webrtc_block = webrtc_block
        self._webgl_enabled = webgl_enabled
        self._google_referer = google_referer
        self._max_pages = max(1, max_pages)
        self._cloudflare_timeout = max(30, cloudflare_timeout)
        self._disable_resources = disable_resources
        self._shared_cdp_url = shared_cdp_url
        self._health_tracker = health_tracker
        self._idle_cleanup_interval = max(0, idle_cleanup_interval)
        self._idle_threshold = max(1, idle_threshold_seconds)

        self._sessions: dict[str, AsyncStealthySession] = {}
        self._session_cms: dict[str, object] = {}
        self._session_last_used: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start background cleanup when configured."""
        if self._idle_cleanup_interval <= 0 or self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("stealth_session_manager_started")

    async def stop(self) -> None:
        """Stop cleanup and close all tracked sessions."""
        cleanup_task = self._cleanup_task
        self._cleanup_task = None
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task

        async with self._lock:
            session_items = list(self._session_cms.items())
            self._sessions.clear()
            self._session_cms.clear()
            self._session_last_used.clear()

        for key, context_manager in session_items:
            await self._exit_context_manager(key, context_manager)

        logger.info("stealth_session_manager_stopped")

    async def fetch(
        self,
        url: str,
        options: FetchOptions,
        proxy_rotator: ProxyRotator | None = None,
    ) -> FetchResult:
        """Fetch a URL through a pooled stealth session."""
        started = time.monotonic()
        proxy_url = options.get("proxy_id")
        session = await self._get_or_create_session(proxy_url=proxy_url, proxy_rotator=proxy_rotator)
        session_key = self._session_key(proxy_url, proxy_rotator)

        try:
            page = await session.fetch(url, **self._build_fetch_params(options))
        except Exception as exc:
            elapsed_ms = (time.monotonic() - started) * 1000
            if proxy_url and self._health_tracker is not None:
                self._health_tracker.mark_failure(proxy_url, str(exc))

            logger.warning("stealth_fetch_failed for %s: %s", url, exc)
            return FetchResult(
                content="",
                url=url,
                final_url=url,
                mode_used=options.get("mode", StealthMode.STEALTH),
                proxy_used=proxy_url,
                response_time_ms=elapsed_ms,
                from_cache=False,
                cloudflare_solved=False,
                error=str(exc),
            )

        async with self._lock:
            self._session_last_used[session_key] = time.monotonic()
        elapsed_ms = (time.monotonic() - started) * 1000
        response_meta = getattr(page, "meta", {}) or {}
        used_proxy = response_meta.get("proxy")
        if used_proxy is not None and self._health_tracker is not None:
            self._health_tracker.mark_success(str(used_proxy), response_time_ms=elapsed_ms)

        mode = options.get("mode", StealthMode.STEALTH)
        return FetchResult(
            content=str(getattr(page, "html_content", "")),
            url=url,
            final_url=str(getattr(page, "url", url)),
            mode_used=mode,
            proxy_used=str(used_proxy) if used_proxy is not None else proxy_url,
            response_time_ms=elapsed_ms,
            from_cache=False,
            cloudflare_solved=mode == StealthMode.CLOUDFLARE,
            error=None,
        )

    def _build_fetch_params(self, options: FetchOptions) -> dict[str, object]:
        """Build the per-request Scrapling fetch parameters."""
        session_timeout = getattr(self, "_session_timeout", 30000)
        network_idle = getattr(self, "_network_idle", True)
        params: dict[str, object] = {
            "timeout": options.get("timeout_ms", session_timeout),
            "network_idle": options.get("network_idle", network_idle),
        }

        mode = options.get("mode", StealthMode.STEALTH)
        if mode == StealthMode.CLOUDFLARE:
            params["solve_cloudflare"] = True
            params["timeout"] = max(int(params["timeout"]), getattr(self, "_cloudflare_timeout", 60) * 1000)

        wait_selector = options.get("wait_selector")
        if wait_selector:
            params["wait_selector"] = wait_selector
            state = options.get("wait_selector_state", "attached")
            if state not in _WAIT_SELECTOR_STATES:
                state = "attached"
            params["wait_selector_state"] = cast(Literal["attached", "detached", "hidden", "visible"], state)

        extra_headers = options.get("extra_headers")
        if extra_headers:
            params["extra_headers"] = extra_headers

        if "disable_resources" in options:
            params["disable_resources"] = options["disable_resources"]

        return params

    def _build_session_params(
        self,
        proxy_url: str | None,
        proxy_rotator: ProxyRotator | None,
    ) -> dict[str, object]:
        """Build Scrapling session construction parameters."""
        params: dict[str, object] = {
            "headless": True,
            "timeout": self._session_timeout,
            "network_idle": self._network_idle,
            "hide_canvas": self._canvas_noise,
            "block_webrtc": self._webrtc_block,
            "allow_webgl": self._webgl_enabled,
            "google_search": self._google_referer,
            "disable_resources": self._disable_resources,
            "max_pages": self._max_pages,
        }

        if proxy_rotator is not None:
            params["proxy_rotator"] = proxy_rotator
        elif proxy_url:
            params["proxy"] = proxy_url

        if self._shared_cdp_url:
            params["cdp_url"] = self._shared_cdp_url

        return params

    async def _get_or_create_session(
        self,
        proxy_url: str | None,
        proxy_rotator: ProxyRotator | None = None,
    ) -> AsyncStealthySession:
        """Reuse or create a session keyed by proxy affinity."""
        from scrapling.fetchers import AsyncStealthySession

        session_key = self._session_key(proxy_url, proxy_rotator)
        async with self._lock:
            existing = self._sessions.get(session_key)
            if existing is not None:
                return existing

            context_manager = AsyncStealthySession(**self._build_session_params(proxy_url, proxy_rotator))
            session = await context_manager.__aenter__()
            self._sessions[session_key] = session
            self._session_cms[session_key] = context_manager
            self._session_last_used[session_key] = time.monotonic()
            logger.info("stealth_session_created for %s", session_key)
            return session

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._idle_cleanup_interval)
                await self._cleanup_idle_sessions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("stealth_session_cleanup_loop_failed")

    async def _cleanup_idle_sessions(self) -> int:
        """Close sessions that have exceeded the idle threshold."""
        now = time.monotonic()
        stale_items: list[tuple[str, object]] = []

        async with self._lock:
            for session_key, last_used in list(self._session_last_used.items()):
                if now - last_used <= self._idle_threshold:
                    continue
                context_manager = self._session_cms.pop(session_key, None)
                self._sessions.pop(session_key, None)
                self._session_last_used.pop(session_key, None)
                if context_manager is not None:
                    stale_items.append((session_key, context_manager))

        for session_key, context_manager in stale_items:
            await self._exit_context_manager(session_key, context_manager)

        if stale_items:
            logger.info("stealth_session_cleanup_removed %d idle sessions", len(stale_items))
        return len(stale_items)

    async def get_active_session_count(self) -> int:
        """Return the number of tracked active sessions."""
        async with self._lock:
            return len(self._sessions)

    async def _exit_context_manager(self, session_key: str, context_manager: object) -> None:
        exit_method = getattr(context_manager, "__aexit__", None)
        if exit_method is None:
            return
        try:
            await exit_method(None, None, None)
        except Exception:
            logger.exception("failed to close stealth session %s", session_key)

    @staticmethod
    def _session_key(proxy_url: str | None, proxy_rotator: ProxyRotator | None) -> str:
        if proxy_url:
            return proxy_url
        if proxy_rotator is not None:
            return "rotator"
        return "direct"
