import pytest

from app.infrastructure.external.browser.choreography import (
    BrowserChoreographer,
    ChoreographyProfile,
    PROFILES,
)


def test_profiles_exist():
    assert "fast" in PROFILES
    assert "professional" in PROFILES
    assert "cinematic" in PROFILES


def test_professional_profile_dwell():
    p = PROFILES["professional"]
    assert 5.0 <= p.dwell_after_navigate <= 10.0


def test_fast_profile_minimal_delays():
    p = PROFILES["fast"]
    assert p.dwell_after_navigate <= 1.5
    assert p.typing_delay_ms <= 15


def test_cinematic_profile_slow_cursor():
    p = PROFILES["cinematic"]
    assert p.cursor_move_steps >= 30
    assert p.cursor_move_duration >= 1.0


def test_choreographer_init_with_profile_name():
    c = BrowserChoreographer(profile_name="professional")
    assert c.profile.name == "professional"
    assert c.enabled is True


def test_choreographer_disabled():
    c = BrowserChoreographer(profile_name="professional", enabled=False)
    assert c.enabled is False


def test_choreographer_unknown_profile_falls_back():
    c = BrowserChoreographer(profile_name="nonexistent")
    assert c.profile.name == "professional"  # fallback to professional


@pytest.mark.asyncio
async def test_choreographer_navigate_delay():
    """When enabled, navigate_pre_extract_delay returns the dwell time."""
    c = BrowserChoreographer(profile_name="fast")
    delay = c.get_navigate_dwell()
    assert delay == PROFILES["fast"].dwell_after_navigate


@pytest.mark.asyncio
async def test_choreographer_disabled_returns_zero_dwell():
    c = BrowserChoreographer(profile_name="professional", enabled=False)
    assert c.get_navigate_dwell() == 0.0


def test_choreographer_get_click_params():
    c = BrowserChoreographer(profile_name="professional")
    params = c.get_click_params()
    assert params["hover_pause"] == PROFILES["professional"].hover_before_click
    assert params["cursor_steps"] == PROFILES["professional"].cursor_move_steps
    assert params["settle_pause"] == PROFILES["professional"].post_click_settle


def test_choreographer_get_type_delay_ms():
    c = BrowserChoreographer(profile_name="cinematic")
    assert c.get_type_delay_ms() == PROFILES["cinematic"].typing_delay_ms


def test_choreographer_get_scroll_pause():
    c = BrowserChoreographer(profile_name="professional")
    assert c.get_scroll_pause() == PROFILES["professional"].scroll_step_pause
