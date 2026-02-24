"""
CDP Navigation API for takeover browser controls.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.services.cdp_navigation import CDPNavigationService

router = APIRouter()
logger = logging.getLogger(__name__)


async def _with_navigation_service() -> CDPNavigationService:
    service = CDPNavigationService()
    connected = await service.connect()
    if not connected:
        await service.disconnect()
        raise HTTPException(status_code=503, detail="Failed to connect to Chrome CDP")
    return service


@router.get("/history")
async def get_navigation_history():
    service = await _with_navigation_service()
    try:
        return await service.get_navigation_history()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch navigation history: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch navigation history") from e
    finally:
        await service.disconnect()


@router.post("/back")
async def navigate_back():
    service = await _with_navigation_service()
    try:
        ok, message = await service.go_back()
        return {"ok": ok, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Back navigation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Back navigation failed") from e
    finally:
        await service.disconnect()


@router.post("/forward")
async def navigate_forward():
    service = await _with_navigation_service()
    try:
        ok, message = await service.go_forward()
        return {"ok": ok, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forward navigation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Forward navigation failed") from e
    finally:
        await service.disconnect()


@router.post("/reload")
async def reload_page():
    service = await _with_navigation_service()
    try:
        ok, message = await service.reload()
        return {"ok": ok, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Reload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Reload failed") from e
    finally:
        await service.disconnect()


@router.post("/stop")
async def stop_loading():
    service = await _with_navigation_service()
    try:
        ok, message = await service.stop_loading()
        return {"ok": ok, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Stop loading failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Stop loading failed") from e
    finally:
        await service.disconnect()
