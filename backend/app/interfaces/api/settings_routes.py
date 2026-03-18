import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

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
        "id": "zai",
        "name": "Z.AI (GLM)",
        "models": ["glm-5-turbo", "glm-5"],
        "requires_api_key": True,
        "api_base": "https://api.z.ai/api/coding/paas/v4",
        "setup_note": (
            "Using the GLM Coding Plan, configure the dedicated Coding API "
            "https://api.z.ai/api/coding/paas/v4 instead of the General API "
            "https://api.z.ai/api/paas/v4"
        ),
    },
    {
        "id": "kimi",
        "name": "Kimi (Moonshot)",
        "models": ["kimi-for-coding", "kimi-k2.5", "moonshot-v1-128k", "moonshot-v1-32k"],
        "requires_api_key": True,
        "api_base": "https://api.kimi.com/coding/v1",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "requires_api_key": True,
        "api_base": "https://api.openai.com/v1",
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
        "api_base": "https://api.anthropic.com",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "requires_api_key": True,
        "api_base": "https://api.deepseek.com",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "models": ["google/gemini-2.5-flash", "nvidia/nemotron-3-nano-30b-a3b"],
        "requires_api_key": True,
        "api_base": "https://openrouter.ai/api/v1",
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "models": ["llama3.2", "llama3.1", "mistral", "codellama", "phi3"],
        "requires_api_key": False,
        "api_base": "http://localhost:11434",
    },
]

SEARCH_PROVIDERS = [
    {"id": "bing", "name": "Bing Search", "requires_api_key": False, "default_chain_rank": None},
    {"id": "google", "name": "Google Search", "requires_api_key": True, "default_chain_rank": None},
    {"id": "duckduckgo", "name": "DuckDuckGo", "requires_api_key": False, "default_chain_rank": 2},
    {"id": "brave", "name": "Brave Search", "requires_api_key": True, "default_chain_rank": None},
    {"id": "tavily", "name": "Tavily", "requires_api_key": True, "default_chain_rank": 1},
    {"id": "serper", "name": "Serper (Google)", "requires_api_key": True, "default_chain_rank": 3},
    {"id": "exa", "name": "Exa", "requires_api_key": True, "default_chain_rank": None},
    {"id": "jina", "name": "Jina Search", "requires_api_key": True, "default_chain_rank": None},
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


class ServerConfigResponse(BaseModel):
    """The actual running server-side configuration (from env vars / singletons)."""

    model_name: str
    api_base: str
    temperature: float
    max_tokens: int
    llm_provider: str
    search_provider: str
    search_provider_chain: list[str]
    configured_search_keys: list[str]


@router.get("/server-config", response_model=APIResponse[ServerConfigResponse])
async def get_server_config(
    current_user: User = Depends(get_current_user),
) -> APIResponse[ServerConfigResponse]:
    """Return the ACTUAL running LLM configuration from the backend.

    This reads from the live LLM singleton (created from env vars at startup),
    NOT from user preferences in MongoDB. Use this to show what the backend
    is actually running.
    """
    from app.core.config import get_settings
    from app.core.search_provider_policy import normalize_search_provider_chain

    settings = get_settings()

    # Read actual running model/api_base from the live LLM singleton via application layer
    live_config = SettingsService.get_live_llm_config()
    actual_model = live_config["model_name"]
    actual_api_base = live_config["api_base"]

    # Search: read actual provider chain from env vars
    search_chain = normalize_search_provider_chain(getattr(settings, "search_provider_chain", None))

    # Detect which search API keys are actually set (non-empty)
    configured_keys: list[str] = []
    key_checks = {
        "tavily": "tavily_api_key",
        "serper": "serper_api_key",
        "brave": "brave_search_api_key",
        "exa": "exa_api_key",
        "jina": "jina_api_key",
        "google": "google_search_api_key",
    }
    for provider_name, attr_name in key_checks.items():
        val = getattr(settings, attr_name, None)
        if val and str(val).strip():
            configured_keys.append(provider_name)

    return APIResponse.success(
        ServerConfigResponse(
            model_name=actual_model,
            api_base=actual_api_base,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            llm_provider=settings.llm_provider,
            search_provider=getattr(settings, "search_provider", "duckduckgo") or "duckduckgo",
            search_provider_chain=search_chain,
            configured_search_keys=configured_keys,
        )
    )
