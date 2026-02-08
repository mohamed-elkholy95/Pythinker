from __future__ import annotations

DEFAULT_SETTINGS: dict = {
    "llm_provider": "anthropic",
    "model_name": "claude-sonnet-4-20250514",
    "temperature": 0.7,
    "max_tokens": 16000,
    "search_provider": "duckduckgo",
    "browser_agent_max_steps": 25,
    "browser_agent_timeout": 300,
    "browser_agent_use_vision": True,
    "deep_research_auto_run": False,
}

PROVIDERS_INFO: dict = {
    "llm_providers": [
        {
            "id": "anthropic",
            "name": "Anthropic",
            "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
            "requires_api_key": True,
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "o1-preview", "o1-mini"],
            "requires_api_key": True,
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "models": ["anthropic/claude-sonnet-4-20250514", "openai/gpt-4o", "google/gemini-2.5-pro"],
            "requires_api_key": True,
        },
    ],
    "search_providers": [
        {"id": "duckduckgo", "name": "DuckDuckGo", "requires_api_key": False},
        {"id": "google", "name": "Google", "requires_api_key": True},
        {"id": "brave", "name": "Brave", "requires_api_key": True},
        {"id": "tavily", "name": "Tavily", "requires_api_key": True},
        {"id": "serper", "name": "Serper", "requires_api_key": True},
    ],
}

# user_id -> settings dict
user_settings: dict[str, dict] = {}

def get_settings(user_id: str) -> dict:
    return user_settings.get(user_id, {**DEFAULT_SETTINGS})

def update_settings(user_id: str, updates: dict) -> dict:
    current = get_settings(user_id)
    current.update({k: v for k, v in updates.items() if v is not None})
    user_settings[user_id] = current
    return current
