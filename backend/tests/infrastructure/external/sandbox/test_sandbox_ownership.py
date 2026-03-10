"""Tests for sandbox ownership protection during active sessions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


class TestSandboxOwnershipProtection:
    """Verify sandbox cannot be reassigned while actively serving a running task."""

    @pytest.fixture(autouse=True)
    def reset_class_state(self):
        """Reset class-level state between tests."""
        original = DockerSandbox._active_sessions.copy()
        yield
        DockerSandbox._active_sessions.clear()
        DockerSandbox._active_sessions.update(original)

    @pytest.mark.asyncio
    async def test_reassignment_blocked_when_task_active(self):
        """Sandbox should NOT be reassigned when current owner has an active task."""
        DockerSandbox._active_sessions["sandbox-1"] = "session-A"

        mock_raw_redis = AsyncMock()
        mock_raw_redis.exists = AsyncMock(return_value=True)

        mock_redis_client = MagicMock()
        mock_redis_client.client = mock_raw_redis

        with patch(
            "app.infrastructure.storage.redis.get_redis",
            return_value=mock_redis_client,
        ):
            result = await DockerSandbox.register_session("sandbox-1", "session-B")

        # Should return None (blocked) and NOT reassign
        assert result is None
        assert DockerSandbox._active_sessions["sandbox-1"] == "session-A"

    @pytest.mark.asyncio
    async def test_reassignment_allowed_when_no_active_task(self):
        """Sandbox CAN be reassigned when current owner has no active task."""
        DockerSandbox._active_sessions["sandbox-1"] = "session-A"

        mock_raw_redis = AsyncMock()
        mock_raw_redis.exists = AsyncMock(return_value=False)

        mock_redis_client = MagicMock()
        mock_redis_client.client = mock_raw_redis

        with patch(
            "app.infrastructure.storage.redis.get_redis",
            return_value=mock_redis_client,
        ):
            result = await DockerSandbox.register_session("sandbox-1", "session-B")

        assert result == "session-A"
        assert DockerSandbox._active_sessions["sandbox-1"] == "session-B"

    @pytest.mark.asyncio
    async def test_reassignment_allowed_when_no_previous_owner(self):
        """Sandbox CAN be assigned when there is no previous owner."""
        result = await DockerSandbox.register_session("sandbox-1", "session-A")
        assert result is None
        assert DockerSandbox._active_sessions["sandbox-1"] == "session-A"

    @pytest.mark.asyncio
    async def test_redis_failure_allows_reassignment(self):
        """If Redis liveness check fails, allow reassignment (graceful degradation)."""
        DockerSandbox._active_sessions["sandbox-1"] = "session-A"

        mock_redis_client = MagicMock()
        mock_redis_client.client = property(lambda self: (_ for _ in ()).throw(Exception("Redis down")))

        with patch(
            "app.infrastructure.storage.redis.get_redis",
            side_effect=Exception("Redis down"),
        ):
            result = await DockerSandbox.register_session("sandbox-1", "session-B")

        assert result == "session-A"
        assert DockerSandbox._active_sessions["sandbox-1"] == "session-B"

    @pytest.mark.asyncio
    async def test_same_session_re_registration_allowed(self):
        """Re-registering the same session should succeed without Redis check."""
        DockerSandbox._active_sessions["sandbox-1"] = "session-A"

        result = await DockerSandbox.register_session("sandbox-1", "session-A")
        assert result is None  # No displacement
        assert DockerSandbox._active_sessions["sandbox-1"] == "session-A"
