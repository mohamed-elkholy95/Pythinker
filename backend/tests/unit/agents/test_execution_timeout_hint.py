"""Tests for timeout hint propagation from execution to LLM (Fix 1)."""


def test_timeout_profiles_exist_in_config():
    """Config must expose llm_timeout_profiles with default, code_gen, summarize."""
    from app.core.config_llm import LLMTimeoutSettingsMixin

    mixin = type("M", (LLMTimeoutSettingsMixin,), {})()
    profiles = mixin.llm_timeout_profiles
    assert "default" in profiles
    assert "code_gen" in profiles
    assert "summarize" in profiles
    assert profiles["default"] == 90.0
    assert profiles["code_gen"] == 180.0
    assert profiles["summarize"] == 150.0
