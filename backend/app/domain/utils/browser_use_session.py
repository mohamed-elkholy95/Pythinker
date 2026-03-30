"""Shared kwargs for browser-use ``BrowserSession`` / ``Browser`` when connecting via CDP."""

from __future__ import annotations

from typing import Any


def cdp_browser_session_extra_kwargs(
    *,
    min_page_load_wait: float,
    network_idle_wait: float,
    max_iframes: int,
    max_iframe_depth: int,
    viewport_width: int = 1280,
    viewport_height: int = 900,
) -> dict[str, Any]:
    """Return kwargs for ``BrowserSession(cdp_url=..., **kwargs)`` shared by tool and service.

    Tuning reduces premature page-readiness failures and caps AX-tree work on iframe-heavy pages.

    Note: Do not pass ``timeout`` here — in browser-use 0.12.x it is merged into cloud browser
    settings (``cloud_timeout`` max 240) and breaks local CDP connections.
    """
    return {
        "headless": False,
        "disable_security": True,
        "viewport": {"width": viewport_width, "height": viewport_height},
        "minimum_wait_page_load_time": min_page_load_wait,
        "wait_for_network_idle_page_load_time": network_idle_wait,
        "max_iframes": max_iframes,
        "max_iframe_depth": max_iframe_depth,
        "cross_origin_iframes": True,
    }
