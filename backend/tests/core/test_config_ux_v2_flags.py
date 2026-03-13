# backend/tests/core/test_config_ux_v2_flags.py
"""Tests for Agent UX v2 feature flag defaults."""

from app.core.config import get_settings


def test_browser_choreography_defaults():
    settings = get_settings()
    assert settings.browser_choreography_enabled is True
    assert settings.browser_choreography_profile == "professional"
    assert settings.browser_screencast_include_chrome_ui is True


def test_terminal_enhancement_defaults():
    settings = get_settings()
    assert settings.terminal_live_streaming_enabled is True
    assert settings.terminal_mastery_prompt_enabled is True
    assert settings.terminal_proactive_preference_enabled is True


def test_skill_architecture_defaults():
    settings = get_settings()
    assert settings.skill_auto_detection_enabled is True
    assert settings.skill_auto_detection_threshold == 0.6
    assert settings.skill_ui_events_enabled is True
