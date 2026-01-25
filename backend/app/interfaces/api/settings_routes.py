from fastapi import APIRouter, Depends
import logging

from app.application.errors.exceptions import NotFoundError
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.settings import (
    UserSettingsResponse,
    UpdateUserSettingsRequest,
    ProvidersResponse,
)
from app.core.config import get_settings
from app.domain.models.user import User
from app.infrastructure.storage.mongodb import get_database

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
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
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
    {"id": "searxng", "name": "SearXNG", "requires_api_key": False},
    {"id": "baidu", "name": "Baidu Search", "requires_api_key": False},
    {"id": "tavily", "name": "Tavily", "requires_api_key": True},
]


def get_default_settings() -> dict:
    """Get default settings from environment config"""
    config = get_settings()
    return {
        "llm_provider": config.llm_provider,
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "search_provider": config.search_provider or "bing",
        "browser_agent_max_steps": config.browser_agent_max_steps,
        "browser_agent_timeout": config.browser_agent_timeout,
        "browser_agent_use_vision": config.browser_agent_use_vision,
    }


@router.get("", response_model=APIResponse[UserSettingsResponse])
async def get_user_settings(
    current_user: User = Depends(get_current_user)
) -> APIResponse[UserSettingsResponse]:
    """Get current user's settings"""
    db = await get_database()

    # Try to get user settings from database
    settings_collection = db.get_collection("user_settings")
    settings_doc = await settings_collection.find_one({"user_id": current_user.id})

    if settings_doc:
        # Return saved settings
        return APIResponse.success(UserSettingsResponse(
            llm_provider=settings_doc.get("llm_provider", "openai"),
            model_name=settings_doc.get("model_name", "gpt-4"),
            temperature=settings_doc.get("temperature", 0.7),
            max_tokens=settings_doc.get("max_tokens", 8000),
            search_provider=settings_doc.get("search_provider", "bing"),
            browser_agent_max_steps=settings_doc.get("browser_agent_max_steps", 25),
            browser_agent_timeout=settings_doc.get("browser_agent_timeout", 300),
            browser_agent_use_vision=settings_doc.get("browser_agent_use_vision", True),
        ))

    # Return default settings from environment
    defaults = get_default_settings()
    return APIResponse.success(UserSettingsResponse(**defaults))


@router.put("", response_model=APIResponse[UserSettingsResponse])
async def update_user_settings(
    request: UpdateUserSettingsRequest,
    current_user: User = Depends(get_current_user)
) -> APIResponse[UserSettingsResponse]:
    """Update current user's settings"""
    db = await get_database()
    settings_collection = db.get_collection("user_settings")

    # Get existing settings or defaults
    settings_doc = await settings_collection.find_one({"user_id": current_user.id})

    if not settings_doc:
        # Create new settings with defaults
        settings_doc = {
            "user_id": current_user.id,
            **get_default_settings(),
        }

    # Update only provided fields
    update_data = request.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update_data.items():
        settings_doc[key] = value

    # Save to database
    await settings_collection.update_one(
        {"user_id": current_user.id},
        {"$set": settings_doc},
        upsert=True
    )

    return APIResponse.success(UserSettingsResponse(
        llm_provider=settings_doc.get("llm_provider", "openai"),
        model_name=settings_doc.get("model_name", "gpt-4"),
        temperature=settings_doc.get("temperature", 0.7),
        max_tokens=settings_doc.get("max_tokens", 8000),
        search_provider=settings_doc.get("search_provider", "bing"),
        browser_agent_max_steps=settings_doc.get("browser_agent_max_steps", 25),
        browser_agent_timeout=settings_doc.get("browser_agent_timeout", 300),
        browser_agent_use_vision=settings_doc.get("browser_agent_use_vision", True),
    ))


@router.get("/providers", response_model=APIResponse[ProvidersResponse])
async def get_available_providers(
    current_user: User = Depends(get_current_user)
) -> APIResponse[ProvidersResponse]:
    """Get available LLM and search providers"""
    return APIResponse.success(ProvidersResponse(
        llm_providers=LLM_PROVIDERS,
        search_providers=SEARCH_PROVIDERS,
    ))
