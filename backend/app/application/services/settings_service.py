"""Application service for user settings."""

import asyncio
import logging
import time
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class SettingsService:
    """Manage persisted user settings with environment defaults."""

    SKILL_POLICY_CACHE_TTL_SECONDS = 60.0
    SKILL_POLICY_CACHE_MAX_ENTRIES = 2000

    def __init__(self) -> None:
        # user_id -> (value, expires_at_monotonic)
        self._skill_policy_cache: OrderedDict[str, tuple[bool, float]] = OrderedDict()
        self._skill_policy_cache_lock = asyncio.Lock()
        self._skill_policy_user_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def get_default_settings() -> dict[str, Any]:
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
            "deep_research_auto_run": False,
            "response_verbosity_preference": "adaptive",
            "clarification_policy": "auto",
            "quality_floor_enforced": True,
            "skill_auto_trigger_enabled": config.skill_auto_trigger_enabled,
        }

    def _get_settings_collection(self):
        config = get_settings()
        mongodb = get_mongodb()
        db = mongodb.client[config.mongodb_database]
        return db.get_collection("user_settings")

    async def get_user_settings(self, user_id: str) -> dict[str, Any]:
        settings_collection = self._get_settings_collection()
        settings_doc = await settings_collection.find_one({"user_id": user_id})
        if settings_doc:
            return {
                "llm_provider": settings_doc.get("llm_provider", "openai"),
                "model_name": settings_doc.get("model_name", "gpt-4"),
                "temperature": settings_doc.get("temperature", 0.7),
                "max_tokens": settings_doc.get("max_tokens", 8000),
                "search_provider": settings_doc.get("search_provider", "bing"),
                "browser_agent_max_steps": settings_doc.get("browser_agent_max_steps", 25),
                "browser_agent_timeout": settings_doc.get("browser_agent_timeout", 300),
                "browser_agent_use_vision": settings_doc.get("browser_agent_use_vision", True),
                "deep_research_auto_run": settings_doc.get("deep_research_auto_run", False),
                "response_verbosity_preference": settings_doc.get("response_verbosity_preference", "adaptive"),
                "clarification_policy": settings_doc.get("clarification_policy", "auto"),
                "quality_floor_enforced": settings_doc.get("quality_floor_enforced", True),
                "skill_auto_trigger_enabled": settings_doc.get(
                    "skill_auto_trigger_enabled", get_settings().skill_auto_trigger_enabled
                ),
            }
        return self.get_default_settings()

    async def get_skill_auto_trigger_enabled(self, user_id: str) -> bool:
        """Get per-user skill auto-trigger policy with a small in-memory TTL cache."""
        cached = await self._get_cached_skill_policy(user_id)
        if cached is not None:
            return cached

        user_lock = self._skill_policy_user_locks.setdefault(user_id, asyncio.Lock())
        async with user_lock:
            # Double-check cache after waiting for lock.
            cached = await self._get_cached_skill_policy(user_id)
            if cached is not None:
                return cached

            fallback = get_settings().skill_auto_trigger_enabled
            value = fallback
            try:
                settings_collection = self._get_settings_collection()
                settings_doc = await settings_collection.find_one(
                    {"user_id": user_id},
                    {"skill_auto_trigger_enabled": 1},
                )
                if settings_doc is not None:
                    value = bool(settings_doc.get("skill_auto_trigger_enabled", fallback))
            except Exception as e:
                logger.warning("Failed to load skill auto-trigger policy for user %s: %s", user_id, e)

            await self._set_cached_skill_policy(user_id, value)
            return value

    async def update_user_settings(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        settings_collection = self._get_settings_collection()
        settings_doc = await settings_collection.find_one({"user_id": user_id})
        if not settings_doc:
            settings_doc = {"user_id": user_id, **self.get_default_settings()}

        for key, value in updates.items():
            settings_doc[key] = value

        await settings_collection.update_one({"user_id": user_id}, {"$set": settings_doc}, upsert=True)
        resolved = await self.get_user_settings(user_id)
        await self._set_cached_skill_policy(user_id, bool(resolved.get("skill_auto_trigger_enabled", False)))
        return resolved

    async def _get_cached_skill_policy(self, user_id: str) -> bool | None:
        now = time.monotonic()
        async with self._skill_policy_cache_lock:
            cached = self._skill_policy_cache.get(user_id)
            if cached is None:
                return None
            value, expires_at = cached
            if expires_at <= now:
                self._skill_policy_cache.pop(user_id, None)
                return None

            # Maintain LRU order for active entries.
            self._skill_policy_cache.move_to_end(user_id)
            return value

    async def _set_cached_skill_policy(self, user_id: str, value: bool) -> None:
        expires_at = time.monotonic() + self.SKILL_POLICY_CACHE_TTL_SECONDS
        async with self._skill_policy_cache_lock:
            self._skill_policy_cache[user_id] = (value, expires_at)
            self._skill_policy_cache.move_to_end(user_id)

            while len(self._skill_policy_cache) > self.SKILL_POLICY_CACHE_MAX_ENTRIES:
                self._skill_policy_cache.popitem(last=False)


@lru_cache
def get_settings_service() -> SettingsService:
    return SettingsService()
