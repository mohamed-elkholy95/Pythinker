"""Tests for StealthSessionManager."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.external.stealth_types import FetchOptions, StealthMode
from app.infrastructure.external.scraper.stealth_session_manager import StealthSessionManager


class TestStealthSessionManager:
    """Test suite for StealthSessionManager."""

    def test_build_fetch_params_cloudflare(self) -> None:
        """Cloudflare mode should enable the solver and selector waits."""
        manager = StealthSessionManager.__new__(StealthSessionManager)
        manager._cloudflare_timeout = 60
        manager._network_idle = True

        options = FetchOptions(
            mode=StealthMode.CLOUDFLARE,
            timeout_ms=30000,
            wait_selector=".content",
            wait_selector_state="visible",
            network_idle=True,
        )

        params = manager._build_fetch_params(options)

        assert params["solve_cloudflare"] is True
        assert params["wait_selector"] == ".content"
        assert params["wait_selector_state"] == "visible"
        assert params["timeout"] == 60000

    def test_build_fetch_params_standard(self) -> None:
        """Standard mode should keep the requested timeout unchanged."""
        manager = StealthSessionManager.__new__(StealthSessionManager)
        manager._cloudflare_timeout = 60
        manager._network_idle = True

        options = FetchOptions(
            mode=StealthMode.STEALTH,
            timeout_ms=30000,
            network_idle=False,
        )

        params = manager._build_fetch_params(options)

        assert "solve_cloudflare" not in params
        assert params["timeout"] == 30000
        assert params["network_idle"] is False

    def test_build_session_params(self) -> None:
        """Session parameters should map to Scrapling's supported names."""
        manager = StealthSessionManager.__new__(StealthSessionManager)
        manager._session_timeout = 30000
        manager._network_idle = True
        manager._canvas_noise = True
        manager._webrtc_block = True
        manager._webgl_enabled = True
        manager._google_referer = True
        manager._max_pages = 3
        manager._disable_resources = False
        manager._shared_cdp_url = None

        params = manager._build_session_params(proxy_url=None, proxy_rotator=None)

        assert params["headless"] is True
        assert params["timeout"] == 30000
        assert params["hide_canvas"] is True
        assert params["block_webrtc"] is True
        assert params["allow_webgl"] is True
        assert params["google_search"] is True
        assert params["max_pages"] == 3

    @pytest.mark.asyncio
    async def test_fetch_success_tracks_proxy(self) -> None:
        """Fetch should return normalized results and mark proxy success."""
        health_tracker = MagicMock()
        manager = StealthSessionManager(
            session_timeout=30000,
            network_idle=True,
            canvas_noise=True,
            webrtc_block=True,
            webgl_enabled=True,
            google_referer=True,
            max_pages=3,
            cloudflare_timeout=60,
            disable_resources=False,
            health_tracker=health_tracker,
            idle_cleanup_interval=0,
        )
        manager._get_or_create_session = AsyncMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(
                fetch=AsyncMock(
                    return_value=SimpleNamespace(
                        html_content="<html>ok</html>",
                        url="https://example.com/final",
                        meta={"proxy": "http://proxy1:8080"},
                    )
                )
            )
        )

        result = await manager.fetch(
            "https://example.com",
            FetchOptions(mode=StealthMode.STEALTH, timeout_ms=1000, network_idle=True),
        )

        assert result["content"] == "<html>ok</html>"
        assert result["final_url"] == "https://example.com/final"
        assert result["proxy_used"] == "http://proxy1:8080"
        health_tracker.mark_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_failure_tracks_proxy_error(self) -> None:
        """Fetch failures should return an error result and mark proxy failure."""
        health_tracker = MagicMock()
        manager = StealthSessionManager(
            session_timeout=30000,
            network_idle=True,
            canvas_noise=True,
            webrtc_block=True,
            webgl_enabled=True,
            google_referer=True,
            max_pages=3,
            cloudflare_timeout=60,
            disable_resources=False,
            health_tracker=health_tracker,
            idle_cleanup_interval=0,
        )
        manager._get_or_create_session = AsyncMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(fetch=AsyncMock(side_effect=RuntimeError("boom")))
        )

        result = await manager.fetch(
            "https://example.com",
            FetchOptions(
                mode=StealthMode.STEALTH,
                timeout_ms=1000,
                network_idle=True,
                proxy_id="http://proxy1:8080",
            ),
        )

        assert result["error"] == "boom"
        assert result["proxy_used"] == "http://proxy1:8080"
        health_tracker.mark_failure.assert_called_once_with("http://proxy1:8080", "boom")
