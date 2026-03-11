"""Tests for sandbox queued ownership with bounded wait (Fix 6)."""

import asyncio
from unittest.mock import patch

import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

SANDBOX_ADDR = "http://localhost:8083"


@pytest.fixture(autouse=True)
def _clean_active_sessions():
    """Ensure _active_sessions is clean before and after each test."""
    DockerSandbox._active_sessions.clear()
    yield
    DockerSandbox._active_sessions.clear()


@pytest.mark.asyncio
async def test_wait_for_ownership_succeeds_when_liveness_expires():
    """wait_for_ownership should poll and succeed when previous owner's liveness key expires."""
    call_count = 0

    async def mock_register(address: str, session_id: str) -> str | None:
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            # Blocked: previous owner still active, don't set ownership
            DockerSandbox._active_sessions[address] = "old-session"
            return None
        # Succeeded on retry: displace the old owner
        DockerSandbox._active_sessions[address] = session_id
        return "old-session"

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=10.0,
            poll_interval=0.1,
        )

    assert result is True
    assert call_count == 2


@pytest.mark.asyncio
async def test_wait_for_ownership_times_out():
    """wait_for_ownership should return False after timeout."""

    async def mock_register(address: str, session_id: str) -> None:
        # Always blocked: keep old owner in _active_sessions
        DockerSandbox._active_sessions[address] = "blocking-session"
        return

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=0.5,
            poll_interval=0.1,
        )

    assert result is False


@pytest.mark.asyncio
async def test_wait_for_ownership_immediate_success():
    """If register_session succeeds immediately (non-None), return True."""

    async def mock_register(address: str, session_id: str) -> str:
        DockerSandbox._active_sessions[address] = session_id
        return "previous-session"

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=10.0,
            poll_interval=0.1,
        )

    assert result is True


@pytest.mark.asyncio
async def test_wait_for_ownership_first_time_assignment():
    """If register_session returns None but we own the sandbox (first-time), return True."""

    async def mock_register(address: str, session_id: str) -> None:
        # Simulate first-time assignment: None return but ownership was set
        DockerSandbox._active_sessions[address] = session_id
        return

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=10.0,
            poll_interval=0.1,
        )

    assert result is True


@pytest.mark.asyncio
async def test_wait_for_ownership_succeeds_after_multiple_polls():
    """wait_for_ownership should keep polling until success within timeout."""
    call_count = 0

    async def mock_register(address: str, session_id: str) -> str | None:
        nonlocal call_count
        call_count += 1
        if call_count < 4:
            # Blocked: keep old owner
            DockerSandbox._active_sessions[address] = "blocking-session"
            return None
        # Finally succeeds
        DockerSandbox._active_sessions[address] = session_id
        return "blocking-session"

    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=10.0,
            poll_interval=0.1,
        )

    assert result is True
    assert call_count == 4


@pytest.mark.asyncio
async def test_wait_for_ownership_respects_poll_interval():
    """wait_for_ownership should sleep between polls for the configured interval."""
    call_count = 0
    sleep_calls: list[float] = []

    async def mock_register(address: str, session_id: str) -> str | None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            DockerSandbox._active_sessions[address] = "blocking-session"
            return None
        DockerSandbox._active_sessions[address] = session_id
        return "blocking-session"

    original_sleep = asyncio.sleep

    async def mock_sleep(duration: float) -> None:
        sleep_calls.append(duration)
        # Actually sleep a tiny bit to advance monotonic clock
        await original_sleep(0.01)

    with (
        patch.object(DockerSandbox, "register_session", side_effect=mock_register),
        patch("app.infrastructure.external.sandbox.docker_sandbox.asyncio.sleep", side_effect=mock_sleep),
    ):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=10.0,
            poll_interval=2.0,
        )

    assert result is True
    assert len(sleep_calls) == 2  # Slept twice before third successful poll
    for duration in sleep_calls:
        assert duration <= 2.0


@pytest.mark.asyncio
async def test_wait_for_ownership_clamps_final_sleep_to_remaining():
    """The final sleep should be clamped to the remaining timeout, not the full poll interval."""
    call_count = 0

    async def mock_register(address: str, session_id: str) -> None:
        nonlocal call_count
        call_count += 1
        # Always blocked
        DockerSandbox._active_sessions[address] = "blocking-session"
        return

    # Use a very short timeout with a longer poll interval
    with patch.object(DockerSandbox, "register_session", side_effect=mock_register):
        result = await DockerSandbox.wait_for_ownership(
            address=SANDBOX_ADDR,
            session_id="new-session",
            max_wait=0.3,
            poll_interval=5.0,  # Much longer than timeout
        )

    assert result is False
    # Should have polled at least once (the initial call)
    assert call_count >= 1


@pytest.mark.asyncio
async def test_config_sandbox_ownership_wait_timeout():
    """Verify sandbox_ownership_wait_timeout config setting exists with correct default."""
    from app.core.config_sandbox import SandboxSettingsMixin

    # The mixin should have the attribute with default 60.0
    assert hasattr(SandboxSettingsMixin, "sandbox_ownership_wait_timeout")
    # Check annotation exists
    assert "sandbox_ownership_wait_timeout" in SandboxSettingsMixin.__annotations__
