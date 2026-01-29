"""
Lightweight health check endpoint for quick connectivity verification.
Separate from the comprehensive monitoring endpoints for minimal overhead.
"""

from fastapi import APIRouter
from typing import Dict, Any
from datetime import datetime

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Lightweight health check endpoint for quick connectivity verification.

    Returns basic system health without detailed component checks.
    Use /monitoring/health for comprehensive health information.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "pythinker-backend"
    }
