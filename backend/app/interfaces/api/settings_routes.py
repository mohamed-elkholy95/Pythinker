import logging

from fastapi import APIRouter, Depends

from app.application.services.settings_service import SettingsService
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user, get_settings_service
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.settings import (
    ProvidersResponse,
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


# Available providers configuration
LLM_PROVIDERS = [
    {
        "id": "openai",
        "name": "OpenAI",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "requires_api_key": True,
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        "requires_api_key": True,
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "models": ["llama3.2", "llama3.1", "mistral", "codellama", "phi3"],
        "requires_api_key": False,
    },
]

SEARCH_PROVIDERS = [
    {"id": "bing", "name": "Bing Search", "requires_api_key": False},
    {"id": "google", "name": "Google Search", "requires_api_key": True},
    {"id": "duckduckgo", "name": "DuckDuckGo", "requires_api_key": False},
    {"id": "brave", "name": "Brave Search", "requires_api_key": True},
    {"id": "tavily", "name": "Tavily", "requires_api_key": True},
    {"id": "serper", "name": "Serper (Google)", "requires_api_key": True},
]


@router.get("", response_model=APIResponse[UserSettingsResponse])
async def get_user_settings(
    current_user: User = Depends(get_current_user),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[UserSettingsResponse]:
    """Get current user's settings"""
    settings_doc = await settings_service.get_user_settings(str(current_user.id))
    return APIResponse.success(UserSettingsResponse(**settings_doc))


@router.put("", response_model=APIResponse[UserSettingsResponse])
async def update_user_settings(
    request: UpdateUserSettingsRequest,
    current_user: User = Depends(get_current_user),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[UserSettingsResponse]:
    """Update current user's settings"""
    update_data = request.model_dump(exclude_unset=True, exclude_none=True)
    settings_doc = await settings_service.update_user_settings(str(current_user.id), update_data)
    return APIResponse.success(UserSettingsResponse(**settings_doc))


@router.get("/providers", response_model=APIResponse[ProvidersResponse])
async def get_available_providers(current_user: User = Depends(get_current_user)) -> APIResponse[ProvidersResponse]:
    """Get available LLM and search providers"""
    return APIResponse.success(
        ProvidersResponse(
            llm_providers=LLM_PROVIDERS,
            search_providers=SEARCH_PROVIDERS,
        )
    )
