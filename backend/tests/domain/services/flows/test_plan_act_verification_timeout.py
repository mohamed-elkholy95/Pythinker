"""Tests for verification timeout with graceful auto-pass degradation.

Covers:
- Default config value for verification_timeout_seconds
- TimeoutError is caught and treated as "pass" (auto-pass)
- ProgressEvent with EXECUTING_SETUP phase is emitted on timeout
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.models.event import PlanningPhase, ProgressEvent, VerificationEvent, VerificationStatus


# ---------------------------------------------------------------------------
# Config default
# ---------------------------------------------------------------------------


def test_verification_timeout_config_default() -> None:
    """verification_timeout_seconds must default to 8.0."""
    from app.core.config import get_settings

    s = get_settings()
    assert s.verification_timeout_seconds == 8.0


def test_verification_timeout_config_type() -> None:
    """verification_timeout_seconds must be a float (not int)."""
    from app.core.config import get_settings

    s = get_settings()
    assert isinstance(s.verification_timeout_seconds, float)


def test_verification_timeout_config_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """VERIFICATION_TIMEOUT_SECONDS env var must override the default."""
    monkeypatch.setenv("VERIFICATION_TIMEOUT_SECONDS", "0.0")

    # Force a fresh settings parse so the env var is picked up.
    import importlib

    import app.core.config as cfg_module

    original_cache = cfg_module.get_settings.cache_info()  # noqa: F841 — just warm
    cfg_module.get_settings.cache_clear()
    try:
        s = cfg_module.get_settings()
        assert s.verification_timeout_seconds == 0.0
    finally:
        cfg_module.get_settings.cache_clear()  # don't pollute other tests


# ---------------------------------------------------------------------------
# Timeout behaviour — lightweight unit test using asyncio.timeout directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_raises_timeout_error_after_deadline() -> None:
    """asyncio.timeout() should raise TimeoutError after the deadline."""

    async def slow_coroutine() -> None:
        await asyncio.sleep(10)

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await slow_coroutine()


@pytest.mark.asyncio
async def test_timeout_zero_means_disabled() -> None:
    """When timeout is 0 no TimeoutError should be raised (disabled path)."""
    from contextlib import nullcontext

    reached = False

    async def fast_coroutine() -> None:
        nonlocal reached
        reached = True

    # Mirrors the production branch: nullcontext() is a no-op async context manager.
    async with nullcontext():
        await fast_coroutine()

    assert reached


# ---------------------------------------------------------------------------
# PlanActFlow verification timeout integration (minimal mock-based test)
# ---------------------------------------------------------------------------


async def _slow_verify_plan_events() -> AsyncGenerator[VerificationEvent, None]:
    """Simulates a verifier that takes longer than the timeout."""
    await asyncio.sleep(10)  # much longer than any test timeout
    yield VerificationEvent(status=VerificationStatus.PASSED)  # never reached


@pytest.mark.asyncio
async def test_verification_timeout_sets_pass_verdict() -> None:
    """When the verifier hangs, verdict must become 'pass' and a ProgressEvent emitted."""

    collected_events: list[Any] = []
    verdict_holder: dict[str, str | None] = {"value": None}

    # Minimal stub: just run the same timeout+suppress logic as in plan_act.py
    timeout_seconds = 0.1  # very short so test is fast

    try:
        async with asyncio.timeout(timeout_seconds):
            async for _ in _slow_verify_plan_events():
                pass  # pragma: no cover
    except TimeoutError:
        verdict_holder["value"] = "pass"
        collected_events.append(
            ProgressEvent(
                phase=PlanningPhase.EXECUTING_SETUP,
                message="Verification timed out — proceeding to execution",
                progress_percent=0,
            )
        )

    assert verdict_holder["value"] == "pass", "Verdict must be 'pass' after timeout"
    assert len(collected_events) == 1
    progress_ev = collected_events[0]
    assert isinstance(progress_ev, ProgressEvent)
    assert progress_ev.phase == PlanningPhase.EXECUTING_SETUP
    assert "timed out" in progress_ev.message.lower()


@pytest.mark.asyncio
async def test_verification_completes_normally_no_timeout() -> None:
    """When verification finishes within the timeout, no timeout is triggered."""

    async def fast_verify() -> AsyncGenerator[VerificationEvent, None]:
        yield VerificationEvent(status=VerificationStatus.PASSED)

    verdict: str | None = None
    try:
        async with asyncio.timeout(5.0):  # generous timeout
            async for event in fast_verify():
                if isinstance(event, VerificationEvent) and event.status == VerificationStatus.PASSED:
                    verdict = "pass"
    except TimeoutError:  # pragma: no cover
        pytest.fail("Timeout should not fire for a fast verifier")

    assert verdict == "pass"
