"""Tests for config warning dedup behavior."""

import logging

from app.core.config import Settings


def test_auth_provider_none_warning_emitted_once_per_process(monkeypatch, caplog):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AUTH_PROVIDER", "none")
    monkeypatch.setenv("ENVIRONMENT", "development")

    original_warnings = set(Settings._emitted_security_warnings)
    original_banner = Settings._startup_banner_emitted
    Settings._emitted_security_warnings.clear()
    Settings._startup_banner_emitted = False

    try:
        with caplog.at_level(logging.WARNING):
            caplog.clear()
            Settings().validate()
            Settings().validate()

        auth_none_warnings = [
            r for r in caplog.records if "AUTH_PROVIDER is set to 'none'" in r.message and r.levelno == logging.WARNING
        ]
        # Dedup: should appear exactly once despite two validate() calls
        assert len(auth_none_warnings) == 1
    finally:
        Settings._emitted_security_warnings.clear()
        Settings._emitted_security_warnings.update(original_warnings)
        Settings._startup_banner_emitted = original_banner
