from datetime import UTC, datetime

from pydantic import BaseModel


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
    search_provider: str = "bing"  # "bing", "google", "duckduckgo", "brave", "searxng", "baidu"

    # Browser Agent settings
    browser_agent_max_steps: int = 25
    browser_agent_timeout: int = 300
    browser_agent_use_vision: bool = True

    # Timestamps
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)

    def update(self, **kwargs) -> None:
        """Update settings with provided values"""
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)
        self.updated_at = datetime.now(UTC)
