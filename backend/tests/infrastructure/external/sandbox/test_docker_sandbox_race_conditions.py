"""Tests for DockerSandbox race-condition fixes.

Covers:
1. Round-robin index atomicity under concurrent create() calls
2. Active-sessions dict atomicity under concurrent register/unregister
3. Even distribution across sandbox addresses under load
4. No duplicate assignments from the round-robin counter
"""

from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SETTINGS_PATCH_TARGET = "app.infrastructure.external.sandbox.docker_sandbox.get_settings"


def _make_settings(**overrides: object) -> SimpleNamespace:
    """Build a minimal settings object that satisfies both create() and __init__."""
    defaults = {
        "uses_static_sandbox_addresses": True,
        "sandbox_address": "sandbox",
        "sandbox_framework_port": 8083,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _reset_class_state() -> None:
    """Reset DockerSandbox class-level shared state between tests."""
    DockerSandbox._sandbox_rr_index = 0
    DockerSandbox._active_sessions.clear()


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Ensure each test starts with a clean slate."""
    _reset_class_state()
    yield  # type: ignore[misc]
    _reset_class_state()


# ---------------------------------------------------------------------------
# 1. Round-Robin Atomicity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_create_returns_different_addresses() -> None:
    """Two concurrent create() calls MUST get different sandbox addresses."""
    addresses = ["sandbox-a", "sandbox-b"]
    settings = _make_settings(sandbox_address=",".join(addresses))

    with (
        patch(_SETTINGS_PATCH_TARGET, return_value=settings),
        patch.object(
            DockerSandbox,
            "_resolve_hostname_to_ip",
            new_callable=AsyncMock,
            side_effect=lambda addr: f"10.0.0.{ord(addr[-1])}",
        ),
        patch.object(
            DockerSandbox,
            "_resolve_to_ip",
            side_effect=lambda addr: addr,
        ),
    ):
        results = await asyncio.gather(
            DockerSandbox.create(),
            DockerSandbox.create(),
        )

    container_names = [r.id for r in results]
    assert len(set(container_names)) == 2, f"Expected 2 unique sandbox assignments, got duplicates: {container_names}"


@pytest.mark.asyncio
async def test_round_robin_no_address_skipped_under_load() -> None:
    """100 concurrent create() calls across 4 addresses must produce even distribution.

    With 100 calls and 4 addresses, each address should appear exactly 25 times.
    """
    num_addresses = 4
    num_calls = 100
    addresses = [f"sandbox-{i}" for i in range(num_addresses)]
    settings = _make_settings(sandbox_address=",".join(addresses))

    with (
        patch(_SETTINGS_PATCH_TARGET, return_value=settings),
        patch.object(
            DockerSandbox,
            "_resolve_hostname_to_ip",
            new_callable=AsyncMock,
            side_effect=lambda addr: f"10.0.0.{addr.split('-')[-1]}",
        ),
        patch.object(
            DockerSandbox,
            "_resolve_to_ip",
            side_effect=lambda addr: addr,
        ),
    ):
        results = await asyncio.gather(*(DockerSandbox.create() for _ in range(num_calls)))

    container_names = [r.id for r in results]
    counts = Counter(container_names)

    assert len(counts) == num_addresses, f"Expected {num_addresses} distinct addresses, got {len(counts)}: {counts}"
    for name, count in counts.items():
        assert count == num_calls // num_addresses, (
            f"Address {name} appeared {count} times, expected {num_calls // num_addresses}. Full distribution: {counts}"
        )


@pytest.mark.asyncio
async def test_round_robin_index_increments_atomically() -> None:
    """After N concurrent create() calls, the index must equal N."""
    num_calls = 50
    settings = _make_settings(sandbox_address="sandbox-a,sandbox-b,sandbox-c")

    with (
        patch(_SETTINGS_PATCH_TARGET, return_value=settings),
        patch.object(
            DockerSandbox,
            "_resolve_hostname_to_ip",
            new_callable=AsyncMock,
            return_value="10.0.0.1",
        ),
        patch.object(
            DockerSandbox,
            "_resolve_to_ip",
            side_effect=lambda addr: addr,
        ),
    ):
        await asyncio.gather(*(DockerSandbox.create() for _ in range(num_calls)))

    assert DockerSandbox._sandbox_rr_index == num_calls, (
        f"Expected index={num_calls}, got {DockerSandbox._sandbox_rr_index}"
    )


@pytest.mark.asyncio
async def test_sequential_create_cycles_through_addresses() -> None:
    """Sequential create() calls must cycle through addresses in order."""
    addresses = ["alpha", "beta", "gamma"]
    settings = _make_settings(sandbox_address=",".join(addresses))

    with (
        patch(_SETTINGS_PATCH_TARGET, return_value=settings),
        patch.object(
            DockerSandbox,
            "_resolve_hostname_to_ip",
            new_callable=AsyncMock,
            return_value="10.0.0.1",
        ),
        patch.object(
            DockerSandbox,
            "_resolve_to_ip",
            side_effect=lambda addr: addr,
        ),
    ):
        results = []
        for _ in range(6):
            sandbox = await DockerSandbox.create()
            results.append(sandbox.id)

    expected = [
        "dev-sandbox-alpha",
        "dev-sandbox-beta",
        "dev-sandbox-gamma",
        "dev-sandbox-alpha",
        "dev-sandbox-beta",
        "dev-sandbox-gamma",
    ]
    assert results == expected


# ---------------------------------------------------------------------------
# 2. Active Sessions Dict Atomicity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_register_detects_conflict() -> None:
    """When two sessions concurrently register for the same sandbox,
    exactly one must see the other as the previous owner."""
    results = await asyncio.gather(
        DockerSandbox.register_session("sandbox-1", "session-A"),
        DockerSandbox.register_session("sandbox-1", "session-B"),
    )

    # One must return None (first writer), the other must return the displaced session_id
    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1, f"Expected exactly one conflict detection, got: {results}"
    assert non_none[0] in ("session-A", "session-B"), f"Conflict detection returned unexpected value: {non_none[0]}"


@pytest.mark.asyncio
async def test_register_returns_none_when_same_session_reregisters() -> None:
    """Re-registering the same session for the same sandbox returns None."""
    first = await DockerSandbox.register_session("sandbox-1", "session-A")
    assert first is None

    second = await DockerSandbox.register_session("sandbox-1", "session-A")
    assert second is None


@pytest.mark.asyncio
async def test_register_returns_previous_on_reassignment() -> None:
    """Registering a different session returns the previous session_id."""
    await DockerSandbox.register_session("sandbox-1", "session-A")
    previous = await DockerSandbox.register_session("sandbox-1", "session-B")
    assert previous == "session-A"


@pytest.mark.asyncio
async def test_concurrent_unregister_does_not_lose_entries() -> None:
    """Concurrent unregister calls for different addresses must not interfere."""
    # Register 10 sandboxes
    for i in range(10):
        await DockerSandbox.register_session(f"sandbox-{i}", f"session-{i}")

    # Unregister even-numbered sandboxes concurrently
    await asyncio.gather(*(DockerSandbox.unregister_session(f"sandbox-{i}") for i in range(0, 10, 2)))

    # Odd-numbered sandboxes must still be registered
    for i in range(1, 10, 2):
        session = await DockerSandbox.get_session_for_sandbox(f"sandbox-{i}")
        assert session == f"session-{i}", f"sandbox-{i} lost its session after concurrent unregister of others"

    # Even-numbered sandboxes must be gone
    for i in range(0, 10, 2):
        session = await DockerSandbox.get_session_for_sandbox(f"sandbox-{i}")
        assert session is None, f"sandbox-{i} should have been unregistered but found: {session}"


@pytest.mark.asyncio
async def test_unregister_with_session_id_guard() -> None:
    """unregister_session with a session_id only removes if it matches the current owner."""
    await DockerSandbox.register_session("sandbox-1", "session-A")

    # Try to unregister with wrong session_id -- should NOT remove
    await DockerSandbox.unregister_session("sandbox-1", session_id="session-B")
    session = await DockerSandbox.get_session_for_sandbox("sandbox-1")
    assert session == "session-A", "Unregister with wrong session_id should be a no-op"

    # Unregister with correct session_id -- should remove
    await DockerSandbox.unregister_session("sandbox-1", session_id="session-A")
    session = await DockerSandbox.get_session_for_sandbox("sandbox-1")
    assert session is None, "Unregister with correct session_id should remove entry"


@pytest.mark.asyncio
async def test_unregister_without_session_id_always_removes() -> None:
    """unregister_session without a session_id always removes the entry."""
    await DockerSandbox.register_session("sandbox-1", "session-A")
    await DockerSandbox.unregister_session("sandbox-1")
    session = await DockerSandbox.get_session_for_sandbox("sandbox-1")
    assert session is None


@pytest.mark.asyncio
async def test_get_session_returns_none_for_unknown_sandbox() -> None:
    """get_session_for_sandbox returns None when nothing is registered."""
    result = await DockerSandbox.get_session_for_sandbox("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# 3. Load Test: 100+ concurrent session operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_high_concurrency_register_unregister() -> None:
    """100 concurrent register + 100 concurrent unregister must leave consistent state."""
    num_sandboxes = 100

    # Phase 1: Register all concurrently
    await asyncio.gather(
        *(DockerSandbox.register_session(f"sandbox-{i}", f"session-{i}") for i in range(num_sandboxes))
    )

    # Verify all registered
    for i in range(num_sandboxes):
        session = await DockerSandbox.get_session_for_sandbox(f"sandbox-{i}")
        assert session == f"session-{i}"

    # Phase 2: Unregister all concurrently
    await asyncio.gather(
        *(DockerSandbox.unregister_session(f"sandbox-{i}", session_id=f"session-{i}") for i in range(num_sandboxes))
    )

    # Verify all gone
    for i in range(num_sandboxes):
        session = await DockerSandbox.get_session_for_sandbox(f"sandbox-{i}")
        assert session is None, f"sandbox-{i} still registered after mass unregister"


@pytest.mark.asyncio
async def test_interleaved_register_and_unregister() -> None:
    """Interleaved register/unregister on the same sandbox must not corrupt state."""
    sandbox = "sandbox-contended"

    async def register_then_unregister(session_id: str) -> None:
        await DockerSandbox.register_session(sandbox, session_id)
        await asyncio.sleep(0)  # Yield to event loop
        await DockerSandbox.unregister_session(sandbox, session_id=session_id)

    # 50 tasks all contending on the same sandbox
    await asyncio.gather(*(register_then_unregister(f"session-{i}") for i in range(50)))

    # After all register+unregister pairs, the sandbox MAY have a session
    # (if a later register happened after an earlier unregister) or may be empty.
    # The key invariant is: no crash and the dict is internally consistent.
    session = await DockerSandbox.get_session_for_sandbox(sandbox)
    assert session is None or session.startswith("session-"), f"Unexpected session value: {session}"


@pytest.mark.asyncio
async def test_concurrent_reassignment_chain() -> None:
    """Rapidly reassigning a single sandbox across many sessions must not lose data."""
    sandbox = "sandbox-hot"
    num_sessions = 200

    # All 200 sessions try to claim the same sandbox concurrently
    results = await asyncio.gather(
        *(DockerSandbox.register_session(sandbox, f"session-{i}") for i in range(num_sessions))
    )

    # Exactly one session should be the final winner
    final = await DockerSandbox.get_session_for_sandbox(sandbox)
    assert final is not None, "Sandbox should have an owner after 200 registrations"
    assert final.startswith("session-"), f"Unexpected final session: {final}"

    # The first caller returns None, all subsequent return a previous session
    none_count = results.count(None)
    assert none_count == 1, f"Expected exactly 1 None (first writer), got {none_count}"


# ---------------------------------------------------------------------------
# 4. Lock existence and type checks
# ---------------------------------------------------------------------------


def test_rr_lock_is_threading_lock() -> None:
    """Round-robin lock must be a threading.Lock (not asyncio.Lock)."""
    import threading

    assert isinstance(DockerSandbox._sandbox_rr_lock, type(threading.Lock()))


def test_sessions_lock_is_asyncio_lock() -> None:
    """Sessions lock must be an asyncio.Lock."""
    assert isinstance(DockerSandbox._active_sessions_lock, asyncio.Lock)
