from typing import Any, Literal

from pydantic import BaseModel, field_validator

from app.core.search_provider_policy import (
    normalize_search_provider_chain,
)


class UserSettingsResponse(BaseModel):
    """Response schema for user settings"""

    llm_provider: str
    model_name: str
    api_base: str = ""
    temperature: float
    max_tokens: int
    search_provider: str
    search_provider_chain: list[str]
    browser_agent_max_steps: int
    browser_agent_timeout: int
    browser_agent_use_vision: bool
    response_verbosity_preference: Literal["adaptive", "concise", "detailed"] = "adaptive"
    clarification_policy: Literal["auto", "always", "never"] = "auto"
    quality_floor_enforced: bool = True
    skill_auto_trigger_enabled: bool = False

    @field_validator("search_provider_chain", mode="before")
    @classmethod
    def _normalize_search_provider_chain(cls, value: Any) -> list[str]:
        return normalize_search_provider_chain(value)


class UpdateUserSettingsRequest(BaseModel):
    """Request schema for updating user settings"""

    llm_provider: str | None = None
    model_name: str | None = None
    api_base: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    search_provider: str | None = None
    search_provider_chain: list[str] | None = None
    browser_agent_max_steps: int | None = None
    browser_agent_timeout: int | None = None
    browser_agent_use_vision: bool | None = None
    response_verbosity_preference: Literal["adaptive", "concise", "detailed"] | None = None
    clarification_policy: Literal["auto", "always", "never"] | None = None
    quality_floor_enforced: bool | None = None
    skill_auto_trigger_enabled: bool | None = None

    @field_validator("search_provider_chain", mode="before")
    @classmethod
    def _normalize_search_provider_chain(
        cls,
        value: Any,
    ) -> list[str] | None:
        if value is None:
            return None
        return normalize_search_provider_chain(value)


class ProvidersResponse(BaseModel):
    """Response schema for available providers"""

    llm_providers: list[dict]  # [{"id": "openai", "name": "OpenAI", "models": [...]}]
    search_providers: list[dict]  # [{"id": "bing", "name": "Bing Search"}]


class LLMProviderInfo(BaseModel):
    """LLM provider information"""

    id: str
    name: str
    models: list[str]
    requires_api_key: bool = True


class SearchProviderInfo(BaseModel):
    """Search provider information"""

    id: str
    name: str
    requires_api_key: bool = False
