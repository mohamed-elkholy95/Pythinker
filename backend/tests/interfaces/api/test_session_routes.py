"""Tests for session route utilities."""

from app.interfaces.api.session_routes import _safe_exc_text


class _UnprintableError(Exception):
    def __str__(self) -> str:  # pragma: no cover - exercised via _safe_exc_text
        raise RuntimeError("stringification failed")


def test_safe_exc_text_returns_message():
    error = RuntimeError("connection dropped")
    assert _safe_exc_text(error) == "connection dropped"


def test_safe_exc_text_handles_unprintable_exception():
    message = _safe_exc_text(_UnprintableError())
    assert "_UnprintableError" in message


def test_safe_exc_text_truncates_long_messages():
    error = RuntimeError("x" * 400)
    assert len(_safe_exc_text(error)) == 240
