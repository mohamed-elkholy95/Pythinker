"""Browser lifecycle API endpoints.

Provides ``POST /api/v1/browser/ensure`` for the backend to request Chrome
startup, and ``GET /api/v1/browser/status`` for observability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.response import Response
from app.services.chrome_lifecycle import get_chrome_lifecycle

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ensure", response_model=Response)
async def ensure_browser():
    """Ensure Chrome is running and CDP is ready.

    Idempotent — if Chrome is already running, returns immediately (~1ms).
    If Chrome is stopped, starts it and waits for CDP readiness (~2-5s).

    Called by the backend before every browser operation.
    """
    lifecycle = get_chrome_lifecycle()
    if lifecycle is None:
        # On-demand disabled — Chrome is always-on
        return Response(
            success=True,
            message="Chrome on-demand disabled (always-on mode)",
            data={"cold_start": False, "startup_ms": None, "state": "always_on"},
        )

    try:
        result = await lifecycle.ensure_running()
        msg = (
            f"Chrome started in {result['startup_ms']}ms"
            if result["cold_start"]
            else "Chrome already running"
        )
        return Response(success=True, message=msg, data=result)
    except TimeoutError as e:
        logger.error("Chrome startup timeout: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Chrome startup failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Chrome startup failed: {e}")


@router.get("/status", response_model=Response)
async def browser_status():
    """Get Chrome lifecycle status and stats."""
    lifecycle = get_chrome_lifecycle()
    if lifecycle is None:
        return Response(
            success=True,
            message="Chrome on-demand disabled",
            data={"mode": "always_on"},
        )

    return Response(
        success=True,
        message=f"Chrome is {lifecycle.state.value}",
        data=lifecycle.stats,
    )
