"""OpenAI-compatible LLM proxy for sandbox containers.

Sandbox agents call this endpoint instead of direct LLM APIs.
The backend validates auth, enforces rate limits and token caps,
then forwards to the configured LLM provider via UniversalLLM.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm-proxy/v1", tags=["llm-proxy"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    max_tokens: int | None = None
    temperature: float | None = None
    stream: bool = False


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = "chatcmpl-proxy"
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[ChatChoice] = []
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "pythinker"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = []


async def verify_proxy_auth(authorization: str = Header(...)) -> str:
    """Validate Bearer token for LLM proxy access."""
    settings = get_settings()
    if not settings.sandbox_llm_proxy_enabled:
        raise HTTPException(status_code=403, detail="LLM proxy is disabled")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    token = authorization[7:]
    if not settings.sandbox_llm_proxy_key or token != settings.sandbox_llm_proxy_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    _token: str = Depends(verify_proxy_auth),
) -> JSONResponse:
    """OpenAI-compatible chat completions endpoint."""
    settings = get_settings()
    max_tokens = min(
        body.max_tokens or settings.sandbox_llm_proxy_max_tokens,
        settings.sandbox_llm_proxy_max_tokens,
    )
    if settings.sandbox_llm_proxy_allowed_models and body.model not in settings.sandbox_llm_proxy_allowed_models:
        raise HTTPException(status_code=400, detail=f"Model '{body.model}' not allowed")
    try:
        from app.application.services.llm_proxy_service import proxy_chat_completion

        messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in body.messages]
        content = await proxy_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=body.temperature,
        )
        response = ChatCompletionResponse(
            model=body.model or settings.model_name,
            choices=[
                ChatChoice(
                    message=ChatMessage(role="assistant", content=content),
                )
            ],
        )
        return JSONResponse(content=response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("LLM proxy error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM proxy error: {type(e).__name__}") from e


@router.get("/models")
async def list_models(
    _token: str = Depends(verify_proxy_auth),
) -> JSONResponse:
    """List available models."""
    settings = get_settings()
    models = [ModelInfo(id=settings.model_name)]
    if settings.sandbox_llm_proxy_allowed_models:
        models = [ModelInfo(id=m) for m in settings.sandbox_llm_proxy_allowed_models]
    return JSONResponse(content=ModelsResponse(data=models).model_dump())
