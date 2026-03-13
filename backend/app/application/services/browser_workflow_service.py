"""Application service for browser fetch workflow orchestration."""

from __future__ import annotations

import time
from itertools import count
from typing import TYPE_CHECKING, Any, AsyncGenerator

from app.domain.external.scraper import ScrapedContent
from app.domain.external.stealth_types import FetchOptions, FetchResult, ProxyHealth, StealthMode

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.infrastructure.external.scraper.scrapling_adapter import ScraplingAdapter


class BrowserWorkflowService:
    """Coordinate fetch-mode selection, escalation, and progress events."""

    _EVENT_COUNTER = count()

    def __init__(self, scraper: ScraplingAdapter, settings: Settings) -> None:
        self._scraper = scraper
        self._settings = settings

    async def get_capabilities(self) -> dict[str, Any]:
        """Return available modes and current cache/proxy capabilities."""
        available_modes = ["http", "dynamic", "stealth"]
        if getattr(self._settings, "stealth_cloudflare_enabled", False):
            available_modes.append("cloudflare")

        proxy_health = self._scraper.get_proxy_health() or {}
        cache_stats = await self._scraper.get_cache_stats()

        return {
            "available_modes": available_modes,
            "cache_enabled": bool(getattr(self._settings, "scraping_cache_enabled", False)),
            "batch_max_concurrency": getattr(self._settings, "scraping_batch_max_concurrency", 3),
            "proxy_health": {
                proxy: self._serialize_proxy_health(health)
                for proxy, health in proxy_health.items()
            },
            "cache": cache_stats,
        }

    async def fetch_with_progress(
        self,
        url: str,
        mode: str | StealthMode = StealthMode.DYNAMIC,
        options: FetchOptions | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield progress events while fetching a URL."""
        resolved_mode = self._coerce_mode(mode)
        merged_options = dict(options or {})
        merged_options["mode"] = resolved_mode

        yield self._build_event("started", url=url, mode=resolved_mode.value, status="running")
        started = time.monotonic()
        yield self._build_event("fetching", url=url, mode=resolved_mode.value, status="running")

        result = await self._fetch_once(url, resolved_mode, merged_options)
        elapsed_ms = (time.monotonic() - started) * 1000
        suggested_mode = self._suggest_next_mode(resolved_mode)

        payload = {
            "url": url,
            "mode": resolved_mode.value,
            "status": "success" if result["error"] is None else "error",
            "final_url": result["final_url"],
            "tier_used": self._tier_from_mode(result),
            "from_cache": result.get("from_cache", False),
            "response_time_ms": round(elapsed_ms, 2),
            "content_length": len(result["content"]),
            "error": result["error"],
            "suggested_mode": None if result["error"] is None or suggested_mode is None else suggested_mode.value,
        }
        phase = "completed" if result["error"] is None else "failed"
        yield self._build_event(phase, **payload)

    async def fetch_with_escalation(self, url: str, options: FetchOptions | None = None) -> FetchResult:
        """Fetch using the requested mode and escalate when needed."""
        merged_options = dict(options or {})
        current_mode = self._coerce_mode(merged_options.get("mode", StealthMode.HTTP))
        attempted: set[StealthMode] = set()
        last_result: FetchResult | None = None

        while current_mode not in attempted:
            attempted.add(current_mode)
            merged_options["mode"] = current_mode
            result = await self._fetch_once(url, current_mode, merged_options)
            last_result = result
            if result["error"] is None and result["content"]:
                return result

            next_mode = self._suggest_next_mode(current_mode)
            if next_mode is None:
                break
            current_mode = next_mode

        if last_result is None:
            return FetchResult(
                content="",
                url=url,
                final_url=url,
                mode_used=current_mode,
                proxy_used=None,
                response_time_ms=0.0,
                from_cache=False,
                cloudflare_solved=False,
                error="No fetch modes available",
            )
        return last_result

    async def invalidate_cache(self, url: str | None = None) -> int:
        """Invalidate cache entries through the scraper adapter."""
        return await self._scraper.invalidate_cache(url)

    async def _fetch_once(self, url: str, mode: StealthMode, options: dict[str, Any]) -> FetchResult:
        call_kwargs = {key: value for key, value in options.items() if key != "mode"}

        if mode == StealthMode.HTTP:
            fetched = await self._scraper.fetch_cached(url, mode=mode, **call_kwargs)
        else:
            fetched = await self._scraper.fetch_with_mode(url, mode, **call_kwargs)

        return self._normalize_result(url, mode, fetched)

    @staticmethod
    def _normalize_result(url: str, mode: StealthMode, fetched: ScrapedContent) -> FetchResult:
        content = fetched.html or fetched.text
        return FetchResult(
            content=content or "",
            url=url,
            final_url=fetched.url or url,
            mode_used=mode,
            proxy_used=None,
            response_time_ms=0.0,
            from_cache=fetched.tier_used == "cache",
            cloudflare_solved=mode == StealthMode.CLOUDFLARE,
            error=fetched.error,
        )

    @staticmethod
    def _coerce_mode(mode: str | StealthMode) -> StealthMode:
        if isinstance(mode, StealthMode):
            return mode
        normalized = mode.strip().lower()
        if normalized == "stealthy":
            return StealthMode.STEALTH
        return StealthMode(normalized)

    def _suggest_next_mode(self, current_mode: StealthMode) -> StealthMode | None:
        if current_mode in {StealthMode.HTTP, StealthMode.DYNAMIC}:
            return StealthMode.STEALTH
        if current_mode == StealthMode.STEALTH and getattr(self._settings, "stealth_cloudflare_enabled", False):
            return StealthMode.CLOUDFLARE
        return None

    @staticmethod
    def _serialize_proxy_health(health: ProxyHealth | Any) -> dict[str, Any]:
        if isinstance(health, ProxyHealth):
            return health.model_dump(mode="json")
        if isinstance(health, dict):
            return health
        return {"value": health}

    @staticmethod
    def _tier_from_mode(result: FetchResult) -> str:
        if result.get("from_cache", False):
            return "cache"
        if result["mode_used"] == StealthMode.STEALTH:
            return "stealthy"
        return result["mode_used"].value

    @classmethod
    def _next_event_id(cls) -> str:
        return f"{int(time.time() * 1000)}-{next(cls._EVENT_COUNTER)}"

    @classmethod
    def _build_event(cls, phase: str, **payload: Any) -> dict[str, Any]:
        return {
            "event_id": cls._next_event_id(),
            "phase": phase,
            **payload,
        }
