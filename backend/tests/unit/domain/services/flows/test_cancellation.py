"""Tests for CancellationSignal cooperative cancellation."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.services.flows.cancellation import CancellationSignal


class TestCancellationSignal:
    """Tests for CancellationSignal."""

    def test_initial_state_not_cancelled(self) -> None:
        signal = CancellationSignal()
        assert signal.is_cancelled is False

    def test_cancel_sets_flag(self) -> None:
        signal = CancellationSignal()
        signal.cancel()
        assert signal.is_cancelled is True

    def test_cancel_idempotent(self) -> None:
        signal = CancellationSignal()
        signal.cancel()
        signal.cancel()
        signal.cancel()
        assert signal.is_cancelled is True

    def test_reset_clears_flag(self) -> None:
        signal = CancellationSignal()
        signal.cancel()
        assert signal.is_cancelled is True
        signal.reset()
        assert signal.is_cancelled is False

    def test_reset_on_not_cancelled(self) -> None:
        signal = CancellationSignal()
        signal.reset()
        assert signal.is_cancelled is False

    def test_cancel_after_reset(self) -> None:
        signal = CancellationSignal()
        signal.cancel()
        signal.reset()
        signal.cancel()
        assert signal.is_cancelled is True

    @pytest.mark.asyncio
    async def test_wait_returns_true_when_cancelled(self) -> None:
        signal = CancellationSignal()

        async def cancel_after_delay() -> None:
            await asyncio.sleep(0.01)
            signal.cancel()

        task = asyncio.create_task(cancel_after_delay())
        result = await signal.wait(deadline=1.0)
        assert result is True
        await task

    @pytest.mark.asyncio
    async def test_wait_returns_false_on_timeout(self) -> None:
        signal = CancellationSignal()
        result = await signal.wait(deadline=0.01)
        assert result is False
        assert signal.is_cancelled is False

    @pytest.mark.asyncio
    async def test_wait_immediate_if_already_cancelled(self) -> None:
        signal = CancellationSignal()
        signal.cancel()
        result = await signal.wait(deadline=0.01)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_none_deadline_with_cancel(self) -> None:
        signal = CancellationSignal()

        async def cancel_soon() -> None:
            await asyncio.sleep(0.01)
            signal.cancel()

        task = asyncio.create_task(cancel_soon())
        result = await signal.wait(deadline=None)
        assert result is True
        await task
