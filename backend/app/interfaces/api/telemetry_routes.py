"""
Telemetry endpoints for frontend error reporting and session replay.

Receives batched JavaScript errors from the browser client and records
them as Prometheus metrics + structured log lines (picked up by Loki
via Promtail).  No auth required — fire-and-forget from the frontend.

Also provides session replay endpoints for debugging failed agent sessions.
"""

import dataclasses
import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.core.prometheus_metrics import FRONTEND_ERRORS
from app.domain.models.user import User
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.session_replay import build_session_replay
from app.interfaces.dependencies import require_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter: max 10 requests / 60s per client IP
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10

_ip_hits: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(ip: str) -> bool:
    """Return True if *ip* has exceeded the per-minute request cap."""
    now = time.monotonic()
    # Prune expired timestamps
    _ip_hits[ip] = [t for t in _ip_hits[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_ip_hits[ip]) >= _RATE_LIMIT_MAX:
        return True
    _ip_hits[ip].append(now)
    return False


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = frozenset(
    {"network", "timeout", "auth", "validation", "server", "sse", "vue", "unhandled", "unknown"}
)
_VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})


class FrontendError(BaseModel):
    """Single error reported by the browser client."""

    message: str
    category: str  # network, timeout, auth, validation, server, sse, vue, unhandled, unknown
    severity: str  # low, medium, high, critical
    component: str = ""
    url: str = ""  # pathname only — no query params for privacy
    user_agent: str = ""
    timestamp: float  # epoch ms
    session_id: str = ""
    details: dict[str, Any] = {}


class FrontendErrorBatch(BaseModel):
    """Batched payload from the frontend error tracker."""

    errors: list[FrontendError] = Field(max_length=25)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/frontend-errors", status_code=202)
async def receive_frontend_errors(
    payload: FrontendErrorBatch,
    request: Request,
) -> dict[str, str]:
    """Receive a batch of frontend errors.

    Logs each error at the appropriate severity and increments
    ``pythinker_frontend_errors_total`` Prometheus counter.
    """
    client_ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_ip):
        return Response(
            content='{"detail":"rate limited"}',
            status_code=429,
            media_type="application/json",
        )

    for err in payload.errors:
        # Sanitise free-form label values to prevent cardinality explosion
        category = err.category if err.category in _VALID_CATEGORIES else "unknown"
        severity = err.severity if err.severity in _VALID_SEVERITIES else "low"
        component = err.component[:64] if err.component else ""

        # Prometheus counter
        FRONTEND_ERRORS.inc({"category": category, "severity": severity, "component": component})

        # Structured log — level depends on severity
        log_data = {
            "event": "frontend_error",
            "error_message": err.message[:512],
            "category": category,
            "severity": severity,
            "component": component,
            "url": err.url[:256],
            "session_id": err.session_id[:64] if err.session_id else "",
            "client_ip": client_ip,
            "client_timestamp": err.timestamp,
        }

        if severity == "critical":
            logger.error("frontend_error", extra=log_data)
        elif severity == "high":
            logger.warning("frontend_error", extra=log_data)
        else:
            logger.info("frontend_error", extra=log_data)

    return {"status": "accepted", "count": str(len(payload.errors))}


# ---------------------------------------------------------------------------
# Session Replay endpoint (admin-only)
# ---------------------------------------------------------------------------


def _get_session_repository() -> SessionRepository:
    """Get session repository instance for dependency injection."""
    from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository

    return MongoSessionRepository()


@router.get("/session-replay/{session_id}")
async def get_session_replay(
    session_id: str,
    errors_only: bool = Query(default=False, description="Only return steps that contain errors"),
    current_user: User = Depends(require_admin_user),
    session_repo: SessionRepository = Depends(_get_session_repository),
) -> dict:
    """Get structured session replay for debugging.

    Returns a timeline of all events grouped by step with error context
    and timing information for post-mortem analysis.

    When errors_only=True, only returns steps that contain errors.

    Requires admin authentication.
    """
    # Load the full session (with events) from MongoDB
    session = await session_repo.find_by_id_full(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        )

    if not session.events:
        logger.info("Session %s has no events for replay", session_id)

    # Build the structured replay
    replay = build_session_replay(session)

    # Filter to error-only steps if requested
    steps = replay.steps
    if errors_only:
        steps = [s for s in steps if s.errors]

    # Serialize dataclasses to dicts for JSON response
    return {
        "session_id": replay.session_id,
        "status": replay.status,
        "task": replay.task,
        "started_at": replay.started_at.isoformat() if replay.started_at else None,
        "ended_at": replay.ended_at.isoformat() if replay.ended_at else None,
        "total_duration_ms": replay.total_duration_ms,
        "total_steps": replay.total_steps,
        "total_tool_calls": replay.total_tool_calls,
        "total_errors": replay.total_errors,
        "has_errors": replay.has_errors,
        "steps": [_serialize_step(s) for s in steps],
        "error_summary": [_serialize_error(e) for e in replay.error_summary],
    }


def _serialize_step(step: object) -> dict:
    """Serialize a ReplayStep dataclass to a JSON-safe dict."""
    d = dataclasses.asdict(step)
    # Convert datetime objects to ISO format strings
    if d.get("started_at"):
        d["started_at"] = d["started_at"].isoformat()
    if d.get("ended_at"):
        d["ended_at"] = d["ended_at"].isoformat()
    for tc in d.get("tool_calls", []):
        if tc.get("timestamp"):
            tc["timestamp"] = tc["timestamp"].isoformat()
    for err in d.get("errors", []):
        if err.get("timestamp"):
            err["timestamp"] = err["timestamp"].isoformat()
    return d


def _serialize_error(error: object) -> dict:
    """Serialize a ReplayError dataclass to a JSON-safe dict."""
    d = dataclasses.asdict(error)
    if d.get("timestamp"):
        d["timestamp"] = d["timestamp"].isoformat()
    return d
