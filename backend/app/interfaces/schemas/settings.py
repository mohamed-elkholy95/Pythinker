from pydantic import BaseModel


class UserSettingsResponse(BaseModel):
    """Response schema for user settings"""

    llm_provider: str
    model_name: str
    temperature: float
    max_tokens: int
    search_provider: str
    browser_agent_max_steps: int
    browser_agent_timeout: int
    browser_agent_use_vision: bool
    deep_research_auto_run: bool = False


class UpdateUserSettingsRequest(BaseModel):
    """Request schema for updating user settings"""

    llm_provider: str | None = None
    model_name: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    search_provider: str | None = None
    browser_agent_max_steps: int | None = None
    browser_agent_timeout: int | None = None
    browser_agent_use_vision: bool | None = None
    deep_research_auto_run: bool | None = None


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
