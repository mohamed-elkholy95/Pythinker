"""
Plotly runtime capability check for sandbox environments.

Probes the sandbox to determine whether Plotly and Kaleido are importable.
Results are cached per-session with a configurable TTL to avoid repeated
probes on every chart generation request.

Usage::

    from app.domain.services.plotly_capability_check import (
        PlotlyCapabilityCheck,
        PlotlyCapabilityStatus,
    )

    checker = PlotlyCapabilityCheck()
    result = await checker.check(sandbox, session_id)
    if result.status == PlotlyCapabilityStatus.AVAILABLE:
        ...
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.models.tool_result import ToolResult

if TYPE_CHECKING:
    from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)

# Sandbox venv python path — must match the orchestrator's _VENV_PYTHON.
_VENV_PYTHON = "/opt/base-python-venv/bin/python3"

# Sentinel version string used when the sandbox image declares Plotly as
# pre-installed via the ``PLOTLY_RUNTIME_AVAILABLE=1`` environment variable
# (e.g. built from Dockerfile.plotly).  Skips the ~2 s Python import probe.
_ENV_PRESET_VERSION = "env-preset"

# Probe command (single exec_command call).
# Fast path: if PLOTLY_RUNTIME_AVAILABLE=1 is set in the sandbox environment
# (Dockerfile.plotly bakes it in), print the env-preset sentinel and exit —
# no Python import overhead.  Otherwise fall through to the full import check.
# Note: single-quoted bash argument prevents outer-shell variable expansion so
# $PLOTLY_RUNTIME_AVAILABLE is evaluated inside the sandbox environment.
_PYTHON_PROBE_SNIPPET = "import plotly; import kaleido; print(plotly.__version__ + chr(44) + kaleido.__version__)"
_CAPABILITY_PROBE_CMD = (
    f'bash -c \'if [ "$PLOTLY_RUNTIME_AVAILABLE" = "1" ]; '
    f"then echo {_ENV_PRESET_VERSION},{_ENV_PRESET_VERSION}; "
    f'else {_VENV_PYTHON} -c "{_PYTHON_PROBE_SNIPPET}"; fi\''
)

# Default cache TTL in seconds (5 minutes).
DEFAULT_CACHE_TTL = 300.0


class PlotlyCapabilityStatus(StrEnum):
    """Result of a Plotly capability probe."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class PlotlyCapabilityResult:
    """Outcome of a single Plotly capability check.

    Attributes:
        status: Whether Plotly + Kaleido are importable.
        plotly_version: Detected Plotly version string, or None.
        kaleido_version: Detected Kaleido version string, or None.
        checked_at: ``time.monotonic()`` when the probe completed.
        error_message: Non-empty when the probe failed with an error.
    """

    status: PlotlyCapabilityStatus
    plotly_version: str | None = None
    kaleido_version: str | None = None
    checked_at: float = 0.0
    error_message: str | None = None

    @property
    def is_available(self) -> bool:
        return self.status == PlotlyCapabilityStatus.AVAILABLE


@dataclass
class PlotlyCapabilityCheck:
    """Stateful capability checker with per-session caching.

    Usage::

        checker = PlotlyCapabilityCheck()
        result = await checker.check(sandbox, session_id)
        if result.is_available:
            # safe to generate charts
    """

    cache_ttl: float = DEFAULT_CACHE_TTL
    _cache: dict[str, PlotlyCapabilityResult] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, sandbox: Sandbox, session_id: str) -> PlotlyCapabilityResult:
        """Probe the sandbox for Plotly + Kaleido availability.

        Returns a cached result if the session was probed within
        ``cache_ttl`` seconds.  Otherwise runs a new probe and caches it.
        """
        cached = self._cache.get(session_id)
        if cached is not None:
            age = time.monotonic() - cached.checked_at
            if age < self.cache_ttl:
                logger.debug(
                    "Plotly capability cache hit: session=%s, status=%s, age=%.1fs",
                    session_id,
                    cached.status,
                    age,
                )
                return cached

        result = await self._probe(sandbox, session_id)
        self._cache[session_id] = result
        return result

    def invalidate(self, session_id: str) -> None:
        """Remove cached result for a session (e.g. on sandbox rebuild)."""
        self._cache.pop(session_id, None)

    def invalidate_all(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    @property
    def cached_sessions(self) -> list[str]:
        """Return session IDs with cached results (for diagnostics)."""
        return list(self._cache.keys())

    # ------------------------------------------------------------------
    # Probe implementation
    # ------------------------------------------------------------------

    async def _probe(self, sandbox: Sandbox, session_id: str) -> PlotlyCapabilityResult:
        """Execute the import probe in the sandbox.

        Uses a single bash command that first checks ``PLOTLY_RUNTIME_AVAILABLE``
        (fast path, ~0 ms for pre-built images like Dockerfile.plotly) and falls
        back to the full Python import check when the env var is absent.
        """
        now = time.monotonic()

        try:
            result: ToolResult = await sandbox.exec_command(
                session_id=session_id,
                exec_dir="/home/ubuntu",
                command=_CAPABILITY_PROBE_CMD,
            )
        except Exception as exc:
            logger.warning("Plotly capability probe raised exception: %s", exc, exc_info=True)
            return PlotlyCapabilityResult(
                status=PlotlyCapabilityStatus.UNKNOWN,
                checked_at=now,
                error_message=f"Probe exception: {exc}",
            )

        if not result.success:
            logger.info(
                "Plotly capability probe failed (sandbox returned failure): %s",
                result.message,
            )
            return PlotlyCapabilityResult(
                status=PlotlyCapabilityStatus.UNAVAILABLE,
                checked_at=now,
                error_message=result.message,
            )

        # Extract output
        output = self._extract_output(result)
        if not output or not output.strip():
            logger.info("Plotly capability probe returned empty output")
            return PlotlyCapabilityResult(
                status=PlotlyCapabilityStatus.UNAVAILABLE,
                checked_at=now,
                error_message="Empty probe output",
            )

        # Parse ``plotly_version,kaleido_version``
        versions = output.strip().split(",", maxsplit=1)
        plotly_ver = versions[0].strip() if len(versions) >= 1 else None
        kaleido_ver = versions[1].strip() if len(versions) >= 2 else None

        if not plotly_ver:
            return PlotlyCapabilityResult(
                status=PlotlyCapabilityStatus.UNAVAILABLE,
                checked_at=now,
                error_message="Could not parse plotly version from probe output",
            )

        logger.info(
            "Plotly capability detected: plotly=%s, kaleido=%s",
            plotly_ver,
            kaleido_ver,
        )
        return PlotlyCapabilityResult(
            status=PlotlyCapabilityStatus.AVAILABLE,
            plotly_version=plotly_ver,
            kaleido_version=kaleido_ver,
            checked_at=now,
        )

    @staticmethod
    def _extract_output(result: ToolResult) -> str:
        """Extract stdout string from a ToolResult returned by exec_command."""
        data = result.data
        if isinstance(data, dict):
            return data.get("output", "")
        if isinstance(data, str):
            return data
        return str(data) if data is not None else ""
