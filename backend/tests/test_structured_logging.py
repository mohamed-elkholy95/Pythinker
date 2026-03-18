from app.core.config import get_settings
from app.infrastructure.structured_logging import REDACTED_VALUE, redact_event_dict


def _reset_settings(monkeypatch, **env_overrides):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    for key, value in env_overrides.items():
        monkeypatch.setenv(key, value)
    # Pre-warm the cache so redact_event_dict doesn't skip due to currsize==0 guard.
    # The guard in redact_event_dict skips redaction when currsize==0 to prevent
    # deadlock during get_settings() initialization (lock is non-reentrant).
    get_settings()


def test_redact_event_dict_redacts_sensitive_keys(monkeypatch):
    _reset_settings(
        monkeypatch,
        LOG_REDACTION_ENABLED="true",
        LOG_REDACTION_KEYS="api_key,password",
    )

    event = {"api_key": "sk-1234567890abcdef", "nested": {"password": "secret", "ok": "value"}}
    redacted = redact_event_dict(None, "info", event)

    assert redacted["api_key"] == REDACTED_VALUE
    assert redacted["nested"]["password"] == REDACTED_VALUE
    assert redacted["nested"]["ok"] == "value"


def test_redact_event_dict_redacts_sensitive_values(monkeypatch):
    _reset_settings(
        monkeypatch,
        LOG_REDACTION_ENABLED="true",
        LOG_REDACTION_KEYS="token",
    )

    event = {"note": "Bearer abcdefghijklmnopqrstuvwxyz123456"}
    redacted = redact_event_dict(None, "info", event)

    assert redacted["note"] == REDACTED_VALUE


def test_redact_event_dict_disabled(monkeypatch):
    _reset_settings(
        monkeypatch,
        LOG_REDACTION_ENABLED="false",
    )

    event = {"api_key": "sk-1234567890abcdef"}
    redacted = redact_event_dict(None, "info", event)

    assert redacted["api_key"] == "sk-1234567890abcdef"
