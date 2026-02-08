from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/ratings")

def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}

class RatingRequest(BaseModel):
    session_id: str
    report_id: str
    rating: int
    feedback: str | None = None

@router.post("")
async def submit_rating(req: RatingRequest):
    return _wrap({"status": "recorded"})
