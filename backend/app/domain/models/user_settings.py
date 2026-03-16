from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.search_provider_policy import (
    DEFAULT_SEARCH_PROVIDER_CHAIN,
    normalize_search_provider_chain,
)


class UserSettings(BaseModel):
    """User settings domain model"""

    id: str  # Same as user_id
    user_id: str

    # LLM Provider settings
    llm_provider: str = "openai"  # "openai", "anthropic", "ollama"
    model_name: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 8000

    # Search Provider settings
    search_provider: str = "duckduckgo"  # "bing", "google", "duckduckgo", "brave", "tavily", "serper", "exa", "jina"
    search_provider_chain: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SEARCH_PROVIDER_CHAIN),
        description="Ordered search fallback chain policy",
    )

    # Browser Agent settings
    browser_agent_max_steps: int = 25
    browser_agent_timeout: int = 300
    browser_agent_use_vision: bool = True
    response_verbosity_preference: str = "adaptive"  # adaptive, concise, detailed
    clarification_policy: str = "auto"  # auto, always, never
    quality_floor_enforced: bool = True
    skill_auto_trigger_enabled: bool = False

    # Skills configuration
    enabled_skills: list[str] = Field(
        default_factory=list,
        description="List of enabled skill IDs",
    )
    skill_configs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-skill configurations keyed by skill ID",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("search_provider_chain", mode="before")
    @classmethod
    def _normalize_provider_chain(cls, value: Any) -> list[str]:
        return normalize_search_provider_chain(value)

    @field_validator("search_provider_chain", mode="before")
    @classmethod
    def _normalize_provider_chain(cls, value: Any) -> list[str]:
        return normalize_search_provider_chain(value)

    def update(self, **kwargs) -> None:
        """Update settings with provided values"""
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
        self.updated_at = datetime.now(UTC)
