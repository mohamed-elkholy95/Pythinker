"""Tests for cancellation token utilities"""

import asyncio

import pytest

from app.domain.utils.cancellation import CancellationToken


class TestCancellationToken:
    """Test CancellationToken functionality"""

    def test_null_token_never_cancels(self):
        """Null token always returns False for is_cancelled"""
        token = CancellationToken.null()
        assert not token.is_cancelled()
        assert bool(token)  # Not cancelled = truthy

    def test_token_without_event_never_cancels(self):
        """Token without event never cancels"""
        token = CancellationToken(event=None, session_id="test")
        assert not token.is_cancelled()
        assert bool(token)

    def test_token_cancels_when_event_set(self):
        """Token detects cancellation when event is set"""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test-123")

        # Not cancelled initially
        assert not token.is_cancelled()
        assert bool(token)

        # Set event
        event.set()

        # Now cancelled
        assert token.is_cancelled()
        assert not bool(token)  # Cancelled = falsy

    @pytest.mark.asyncio
    async def test_check_cancelled_raises_when_cancelled(self):
        """check_cancelled raises CancelledError when event is set"""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test-456")

        # Doesn't raise when not cancelled
        await token.check_cancelled()

        # Set event
        event.set()

        # Now raises
        with pytest.raises(asyncio.CancelledError, match="test-456"):
            await token.check_cancelled()

    @pytest.mark.asyncio
    async def test_check_cancelled_doesnt_raise_when_not_cancelled(self):
        """check_cancelled doesn't raise when event is not set"""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        # Should not raise
        await token.check_cancelled()
        assert not token.is_cancelled()

    def test_boolean_context_usage(self):
        """Token can be used in boolean context (if token: ...)"""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        # Not cancelled - should be truthy
        if token:
            passed = True
        else:
            passed = False
        assert passed

        # Set event (cancelled)
        event.set()

        # Cancelled - should be falsy
        if token:
            passed = True
        else:
            passed = False
        assert not passed

    def test_multiple_checks_log_once(self):
        """Multiple is_cancelled() calls only log once"""
        event = asyncio.Event()
        token = CancellationToken(event=event, session_id="test")

        event.set()

        # First check
        assert token.is_cancelled()
        assert token._checked_count == 1

        # Second check
        assert token.is_cancelled()
        assert token._checked_count == 2

        # Third check
        assert token.is_cancelled()
        assert token._checked_count == 3
