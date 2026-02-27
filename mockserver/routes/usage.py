from fastapi import APIRouter
from stores import usage_store

router = APIRouter(prefix="/usage")


def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}


@router.get("/summary")
async def get_summary():
    return _wrap(usage_store.get_usage_summary())


@router.get("/daily")
async def get_daily(days: int = 30):
    return _wrap(usage_store.get_daily_usage(days))


@router.get("/monthly")
async def get_monthly(months: int = 6):
    return _wrap(usage_store.get_monthly_usage(months))


@router.get("/session/{session_id}")
async def get_session_usage(session_id: str):
    return _wrap(usage_store.get_session_usage(session_id))


@router.get("/pricing")
async def get_pricing():
    return _wrap(usage_store.get_pricing())
