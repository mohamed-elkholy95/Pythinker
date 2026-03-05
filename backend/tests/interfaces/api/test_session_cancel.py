"""Tests for the session cancellation registry and cancel endpoint."""
import pytest

from app.domain.services.flows.cancellation import CancellationSignal


def test_cancel_registry_lifecycle() -> None:
    """register → get → unregister round-trip works correctly."""
    from app.interfaces.api.session_routes import (
        get_cancellation_signal,
        register_cancellation_signal,
        unregister_cancellation_signal,
    )

    session_id = "lifecycle-test-session"
    signal = CancellationSignal()

    register_cancellation_signal(session_id, signal)
    assert get_cancellation_signal(session_id) is signal

    unregister_cancellation_signal(session_id)
    assert get_cancellation_signal(session_id) is None


def test_cancel_nonexistent_returns_none() -> None:
    """get_cancellation_signal returns None for unknown session_id."""
    from app.interfaces.api.session_routes import get_cancellation_signal

    assert get_cancellation_signal("nonexistent-session-xyz") is None


def test_unregister_nonexistent_is_safe() -> None:
    """unregister_cancellation_signal does not raise for unknown session_id."""
    from app.interfaces.api.session_routes import unregister_cancellation_signal

    # Should not raise KeyError or any other exception.
    unregister_cancellation_signal("does-not-exist")


def test_register_overwrites_existing_signal() -> None:
    """Registering a new signal for an active session replaces the old one."""
    from app.interfaces.api.session_routes import (
        get_cancellation_signal,
        register_cancellation_signal,
        unregister_cancellation_signal,
    )

    session_id = "overwrite-test-session"
    signal_a = CancellationSignal()
    signal_b = CancellationSignal()

    register_cancellation_signal(session_id, signal_a)
    register_cancellation_signal(session_id, signal_b)

    assert get_cancellation_signal(session_id) is signal_b
    assert get_cancellation_signal(session_id) is not signal_a

    # Cleanup
    unregister_cancellation_signal(session_id)


def test_cancellation_signal_is_set_after_cancel() -> None:
    """Calling signal.cancel() sets is_cancelled to True."""
    signal = CancellationSignal()
    assert not signal.is_cancelled

    signal.cancel()
    assert signal.is_cancelled


def test_multiple_sessions_are_independent() -> None:
    """Registry entries for different sessions do not interfere."""
    from app.interfaces.api.session_routes import (
        get_cancellation_signal,
        register_cancellation_signal,
        unregister_cancellation_signal,
    )

    id_a = "multi-session-a"
    id_b = "multi-session-b"
    signal_a = CancellationSignal()
    signal_b = CancellationSignal()

    register_cancellation_signal(id_a, signal_a)
    register_cancellation_signal(id_b, signal_b)

    assert get_cancellation_signal(id_a) is signal_a
    assert get_cancellation_signal(id_b) is signal_b

    unregister_cancellation_signal(id_a)
    assert get_cancellation_signal(id_a) is None
    # id_b should still be registered
    assert get_cancellation_signal(id_b) is signal_b

    unregister_cancellation_signal(id_b)
