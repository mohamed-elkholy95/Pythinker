import time

import app.domain.services.agents.lettuce_verifier as lettuce_verifier


class _FakeVerifier:
    def __init__(self) -> None:
        self._detector = object()
        self._load_error = "initial"


def test_holder_evicts_instance_after_ttl(monkeypatch) -> None:
    holder = lettuce_verifier._VerifierHolder()
    fake = _FakeVerifier()

    monkeypatch.setattr(holder, "_create", lambda: fake)
    monkeypatch.setattr(holder, "_schedule_eviction", lambda: None)

    instance = holder.get()
    assert instance is fake
    assert holder._instance is fake

    # Simulate idle period beyond TTL and force eviction check.
    holder._last_used = time.monotonic() - (lettuce_verifier._TTL_SECONDS + 1)
    holder._try_evict()

    assert holder._instance is None
    assert fake._detector is None
    assert fake._load_error is None


def test_holder_does_not_evict_when_recently_used(monkeypatch) -> None:
    holder = lettuce_verifier._VerifierHolder()
    fake = _FakeVerifier()

    monkeypatch.setattr(holder, "_create", lambda: fake)
    monkeypatch.setattr(holder, "_schedule_eviction", lambda: None)

    instance = holder.get()
    assert instance is fake

    # Keep within idle window.
    holder._last_used = time.monotonic()
    holder._try_evict()

    assert holder._instance is fake


def test_get_lettuce_verifier_uses_shared_holder(monkeypatch) -> None:
    holder = lettuce_verifier._VerifierHolder()
    fake = _FakeVerifier()

    monkeypatch.setattr(holder, "_create", lambda: fake)
    monkeypatch.setattr(holder, "_schedule_eviction", lambda: None)
    monkeypatch.setattr(lettuce_verifier, "_holder", holder)

    first = lettuce_verifier.get_lettuce_verifier()
    second = lettuce_verifier.get_lettuce_verifier()

    assert first is second
