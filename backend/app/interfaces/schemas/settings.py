from typing import Optional, List
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


class UpdateUserSettingsRequest(BaseModel):
    """Request schema for updating user settings"""
    llm_provider: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    search_provider: Optional[str] = None
    browser_agent_max_steps: Optional[int] = None
    browser_agent_timeout: Optional[int] = None
    browser_agent_use_vision: Optional[bool] = None


class ProvidersResponse(BaseModel):
    """Response schema for available providers"""
    llm_providers: List[dict]  # [{"id": "openai", "name": "OpenAI", "models": [...]}]
    search_providers: List[dict]  # [{"id": "bing", "name": "Bing Search"}]


class LLMProviderInfo(BaseModel):
    """LLM provider information"""
    id: str
    name: str
    models: List[str]
    requires_api_key: bool = True


class SearchProviderInfo(BaseModel):
    """Search provider information"""
    id: str
    name: str
    requires_api_key: bool = False
