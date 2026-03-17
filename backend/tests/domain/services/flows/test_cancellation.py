"""Tests for cooperative CancellationSignal."""

import asyncio

import pytest

from app.domain.services.flows.cancellation import CancellationSignal


def test_initial_state_not_cancelled():
    signal = CancellationSignal()
    assert not signal.is_cancelled


def test_cancel_sets_flag():
    signal = CancellationSignal()
    signal.cancel()
    assert signal.is_cancelled


def test_cancel_is_idempotent():
    signal = CancellationSignal()
    signal.cancel()
    signal.cancel()
    assert signal.is_cancelled


def test_reset_clears_flag():
    signal = CancellationSignal()
    signal.cancel()
    assert signal.is_cancelled
    signal.reset()
    assert not signal.is_cancelled


@pytest.mark.asyncio
async def test_wait_returns_true_when_cancelled():
    signal = CancellationSignal()

    async def cancel_later():
        await asyncio.sleep(0.05)
        signal.cancel()

    bg_task = asyncio.create_task(cancel_later())  # noqa: RUF006, F841
    result = await signal.wait(deadline=1.0)
    assert result is True


@pytest.mark.asyncio
async def test_wait_returns_false_on_timeout():
    signal = CancellationSignal()
    result = await signal.wait(deadline=0.05)
    assert result is False
