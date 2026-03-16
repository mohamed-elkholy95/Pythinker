from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from stores import settings_store
from routes.auth import _get_current_user

router = APIRouter(prefix="/settings")


def _wrap(data):
    return {"code": 0, "msg": "success", "data": data}


@router.get("")
async def get_settings(request: Request):
    user = _get_current_user(request)
    return _wrap(settings_store.get_settings(user["id"]))


class UpdateSettingsRequest(BaseModel):
    llm_provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    search_provider: str | None = None
    browser_agent_max_steps: int | None = None
    browser_agent_timeout: int | None = None
    browser_agent_use_vision: bool | None = None
    deep_research_auto_run: bool | None = None


@router.put("")
async def update_settings(req: UpdateSettingsRequest, request: Request):
    user = _get_current_user(request)
    updated = settings_store.update_settings(
        user["id"], req.model_dump(exclude_none=True)
    )
    return _wrap(updated)


@router.get("/providers")
async def get_providers():
    return _wrap(settings_store.PROVIDERS_INFO)
