"""Tests for MongoDB slow query profiler (Phase 4B)."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.middleware.mongo_profiler import (
    _enable_profiling,
    start_mongo_profiler,
    stop_mongo_profiler,
)


class TestMongoProfiler:
    """Tests for the MongoDB slow query profiler."""

    @pytest.mark.asyncio
    async def test_enable_profiling_calls_profile_command(self):
        """Enabling profiling sends the profile command with threshold."""
        mock_db = AsyncMock()
        mock_db.command = AsyncMock()

        await _enable_profiling(mock_db, threshold_ms=200)

        mock_db.command.assert_called_once_with("profile", 1, slowms=200)

    @pytest.mark.asyncio
    async def test_enable_profiling_handles_failure_gracefully(self):
        """Profile command failure is logged but doesn't raise."""
        mock_db = AsyncMock()
        mock_db.command = AsyncMock(side_effect=Exception("auth error"))

        # Should not raise
        await _enable_profiling(mock_db, threshold_ms=100)

    @pytest.mark.asyncio
    async def test_start_and_stop_profiler(self):
        """Profiler starts a background task that can be cancelled."""
        mock_db = AsyncMock()
        mock_db.command = AsyncMock()

        task = await start_mongo_profiler(mock_db, threshold_ms=100)
        assert not task.done()

        await stop_mongo_profiler()
        # Give cancellation a moment to propagate
        await asyncio.sleep(0.1)
        assert task.done()
