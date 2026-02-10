"""Tests for config warning dedup behavior."""

import warnings

from app.core.config import Settings


def test_auth_provider_none_warning_emitted_once_per_process(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AUTH_PROVIDER", "none")
    monkeypatch.setenv("ENVIRONMENT", "development")

    original_warnings = set(Settings._emitted_security_warnings)
    original_banner = Settings._startup_banner_emitted
    Settings._emitted_security_warnings.clear()
    Settings._startup_banner_emitted = False

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Settings().validate()
            Settings().validate()

        auth_none_warnings = [w for w in caught if "AUTH_PROVIDER is set to 'none'" in str(w.message)]
        assert len(auth_none_warnings) == 1
    finally:
        Settings._emitted_security_warnings.clear()
        Settings._emitted_security_warnings.update(original_warnings)
        Settings._startup_banner_emitted = original_banner
