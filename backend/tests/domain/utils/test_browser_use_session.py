"""Tests for CDP browser-use session kwargs helper."""

from app.domain.utils.browser_use_session import cdp_browser_session_extra_kwargs


def test_cdp_browser_session_extra_kwargs_shape() -> None:
    kwargs = cdp_browser_session_extra_kwargs(
        min_page_load_wait=2.5,
        network_idle_wait=4.0,
        max_iframes=12,
        max_iframe_depth=3,
    )
    assert kwargs["headless"] is False
    assert kwargs["disable_security"] is True
    assert kwargs["viewport"] == {"width": 1280, "height": 900}
    assert kwargs["minimum_wait_page_load_time"] == 2.5
    assert kwargs["wait_for_network_idle_page_load_time"] == 4.0
    assert kwargs["max_iframes"] == 12
    assert kwargs["max_iframe_depth"] == 3
    assert kwargs["cross_origin_iframes"] is True
    assert "timeout" not in kwargs
