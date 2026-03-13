"""Integration tests for BrowserChoreographer injection into PlaywrightBrowser.

Validates that PlaywrightBrowser accepts an explicit choreographer or creates
a default one from settings, and that connection_pool.py wires choreographer
through when creating browser instances.
"""

from unittest.mock import MagicMock, patch

from app.infrastructure.external.browser.choreography import BrowserChoreographer


def _make_fake_settings(**overrides):
    """Create a fake settings object with choreography defaults."""
    defaults = {
        "browser_cdp_url": None,
        "browser_blocked_types_set": None,
        "browser_crash_window_seconds": 300.0,
        "browser_crash_threshold": 3,
        "browser_crash_cooldown_seconds": 60.0,
        "browser_crash_circuit_breaker_enabled": True,
        "browser_quick_health_check_enabled": True,
        "browser_quick_health_check_timeout": 5.0,
        "browser_cdp_keepalive_enabled": False,
        "browser_cdp_keepalive_interval": 45.0,
        "browser_choreography_profile": "professional",
        "browser_choreography_enabled": True,
        "feature_dom_cursor_injection": False,
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


@patch("app.infrastructure.external.browser.playwright_browser.get_settings")
@patch("app.infrastructure.external.browser.playwright_browser.get_llm")
def test_playwright_browser_accepts_choreographer(mock_llm, mock_settings):
    """PlaywrightBrowser.__init__ accepts optional choreographer param."""
    mock_settings.return_value = _make_fake_settings()
    mock_llm.return_value = MagicMock()

    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    choreographer = BrowserChoreographer(profile_name="fast")
    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222", choreographer=choreographer)
    assert browser._choreographer is choreographer
    assert browser._choreographer.profile.name == "fast"


@patch("app.infrastructure.external.browser.playwright_browser.get_settings")
@patch("app.infrastructure.external.browser.playwright_browser.get_llm")
def test_playwright_browser_creates_default_choreographer(mock_llm, mock_settings):
    """Without explicit choreographer, one is created from settings."""
    mock_settings.return_value = _make_fake_settings(
        browser_choreography_profile="professional",
        browser_choreography_enabled=True,
    )
    mock_llm.return_value = MagicMock()

    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
    assert browser._choreographer is not None
    assert isinstance(browser._choreographer, BrowserChoreographer)
    assert browser._choreographer.enabled is True
    assert browser._choreographer.profile.name == "professional"


@patch("app.infrastructure.external.browser.playwright_browser.get_settings")
@patch("app.infrastructure.external.browser.playwright_browser.get_llm")
def test_playwright_browser_default_choreographer_respects_disabled_flag(mock_llm, mock_settings):
    """When browser_choreography_enabled=False, default choreographer is disabled."""
    mock_settings.return_value = _make_fake_settings(
        browser_choreography_enabled=False,
    )
    mock_llm.return_value = MagicMock()

    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
    assert browser._choreographer.enabled is False
    assert browser._choreographer.get_navigate_dwell() == 0.0


@patch("app.infrastructure.external.browser.playwright_browser.get_settings")
@patch("app.infrastructure.external.browser.playwright_browser.get_llm")
def test_playwright_browser_default_choreographer_uses_fast_profile(mock_llm, mock_settings):
    """Settings profile propagates to default choreographer."""
    mock_settings.return_value = _make_fake_settings(
        browser_choreography_profile="fast",
    )
    mock_llm.return_value = MagicMock()

    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    browser = PlaywrightBrowser(cdp_url="ws://localhost:9222")
    assert browser._choreographer.profile.name == "fast"
    assert browser._choreographer.profile.dwell_after_navigate <= 1.5


@patch("app.infrastructure.external.browser.playwright_browser.get_settings")
@patch("app.infrastructure.external.browser.playwright_browser.get_llm")
def test_connection_pool_choreographer_wiring(mock_llm, mock_settings):
    """connection_pool creates BrowserChoreographer from settings and passes to PlaywrightBrowser.

    Validates the same construction pattern used in connection_pool._create_connection_with_retry.
    """
    fake_settings = _make_fake_settings(
        browser_choreography_profile="cinematic",
        browser_choreography_enabled=True,
    )
    mock_settings.return_value = fake_settings
    mock_llm.return_value = MagicMock()

    # Replicate the exact construction from connection_pool._create_connection_with_retry
    choreographer = BrowserChoreographer(
        profile_name=fake_settings.browser_choreography_profile,
        enabled=fake_settings.browser_choreography_enabled,
    )

    from app.infrastructure.external.browser.playwright_browser import PlaywrightBrowser

    browser = PlaywrightBrowser(
        cdp_url="ws://localhost:9222",
        block_resources=False,
        randomize_fingerprint=True,
        choreographer=choreographer,
    )
    assert browser._choreographer is choreographer
    assert browser._choreographer.profile.name == "cinematic"
    assert browser._choreographer.enabled is True


def test_connection_pool_imports_choreographer():
    """connection_pool.py imports BrowserChoreographer at module level."""
    from app.infrastructure.external.browser import connection_pool

    assert hasattr(connection_pool, "BrowserChoreographer")
    assert connection_pool.BrowserChoreographer is BrowserChoreographer
