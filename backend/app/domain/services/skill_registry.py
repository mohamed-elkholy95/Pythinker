"""Centralized Skill Registry with Caching.

Provides a singleton registry for skill management with:
- Session-level caching for performance
- Dependency resolution
- Tool restriction computation
- Trigger pattern compilation

Based on dynamic tool selection patterns used in modern agent systems.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.domain.models.skill import Skill

logger = logging.getLogger(__name__)


@dataclass
class SkillContextResult:
    """Complete skill context for agent execution."""

    prompt_addition: str
    allowed_tools: set[str] | None
    required_tools: set[str]
    skill_ids: list[str]

    def has_tool_restrictions(self) -> bool:
        """Check if skills impose tool restrictions."""
        return self.allowed_tools is not None


@dataclass
class CacheEntry:
    """Cache entry with TTL tracking."""

    data: "Skill"
    cached_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_expired(self, ttl: timedelta) -> bool:
        """Check if entry has expired."""
        return datetime.now(UTC) - self.cached_at > ttl


class SkillRegistry:
    """Centralized skill registry with caching and lazy loading.

    Implements the singleton pattern with async-safe initialization.
    Provides session-level caching to reduce database queries.
    """

    _instance: ClassVar["SkillRegistry | None"] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self) -> None:
        self._skills: dict[str, CacheEntry] = {}
        self._context_cache: dict[str, tuple[SkillContextResult, datetime]] = {}
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        self._last_refresh: datetime | None = None
        self._ttl = timedelta(minutes=5)
        self._context_ttl = timedelta(minutes=2)
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "SkillRegistry":
        """Get singleton instance with async-safe initialization."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._load_skills()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None

    async def _load_skills(self) -> None:
        """Load all skills from database into cache."""
        try:
            from app.application.services.skill_service import get_skill_service

            skill_service = get_skill_service()
            skills = await skill_service.get_available_skills()

            for skill in skills:
                self._skills[skill.id] = CacheEntry(data=skill)
                # Compile trigger patterns
                if skill.trigger_patterns:
                    self._compiled_patterns[skill.id] = [
                        re.compile(pattern, re.IGNORECASE) for pattern in skill.trigger_patterns
                    ]

            self._last_refresh = datetime.now(UTC)
            self._initialized = True
            skill_sources = {
                skill.source.value: len([s for s in skills if s.source.value == skill.source.value]) for skill in skills
            }
            logger.info(
                f"✓ SkillRegistry loaded {len(skills)} skills "
                f"(sources: {skill_sources}, patterns: {len(self._compiled_patterns)})"
            )

        except Exception as e:
            logger.warning(f"Failed to load skills into registry: {e}")
            self._initialized = False  # Allow retry on next access
            self._last_refresh = datetime.now(UTC)  # But don't retry immediately

    async def _ensure_fresh(self) -> None:
        """Ensure cache is not stale."""
        if not self._initialized:
            await self._load_skills()
            return

        if self._last_refresh and datetime.now(UTC) - self._last_refresh > self._ttl:
            await self._load_skills()

    async def get_skill(self, skill_id: str) -> "Skill | None":
        """Get skill by ID with cache refresh."""
        await self._ensure_fresh()

        entry = self._skills.get(skill_id)
        if entry is None:
            # Try to fetch from database
            try:
                from app.application.services.skill_service import get_skill_service

                skill_service = get_skill_service()
                skill = await skill_service.get_skill_by_id(skill_id)
                if skill:
                    self._skills[skill_id] = CacheEntry(data=skill)
                    return skill
            except Exception as e:
                logger.warning(f"Failed to fetch skill {skill_id}: {e}")
            return None

        if entry.is_expired(self._ttl):
            # Refresh this specific skill
            try:
                from app.application.services.skill_service import get_skill_service

                skill_service = get_skill_service()
                skill = await skill_service.get_skill_by_id(skill_id)
                if skill:
                    self._skills[skill_id] = CacheEntry(data=skill)
                    return skill
            except Exception as e:
                logger.warning(f"Failed to refresh skill {skill_id}: {e}")

        return entry.data

    async def get_skills(self, skill_ids: list[str]) -> list["Skill"]:
        """Get multiple skills by ID."""
        skills = []
        for skill_id in skill_ids:
            skill = await self.get_skill(skill_id)
            if skill:
                skills.append(skill)
        return skills

    async def get_available_skills(self) -> list["Skill"]:
        """Get all cached skills."""
        await self._ensure_fresh()
        return [entry.data for entry in self._skills.values()]

    async def get_ai_invokable_skills(self) -> list["Skill"]:
        """Get skills that can be invoked by AI."""
        from app.domain.models.skill import SkillInvocationType

        all_skills = await self.get_available_skills()
        return [
            skill for skill in all_skills if skill.invocation_type in (SkillInvocationType.AI, SkillInvocationType.BOTH)
        ]

    async def build_context(
        self,
        skill_ids: list[str],
        arguments: str = "",
        expand_dynamic: bool = True,
    ) -> SkillContextResult:
        """Build complete skill context with caching.

        Args:
            skill_ids: List of skill IDs to build context for
            arguments: Optional arguments for skill expansion
            expand_dynamic: Whether to expand !command syntax

        Returns:
            SkillContextResult with prompt addition, tool restrictions, etc.
        """
        if not skill_ids:
            return SkillContextResult(
                prompt_addition="",
                allowed_tools=None,
                required_tools=set(),
                skill_ids=[],
            )

        # Check context cache
        cache_key = f"{':'.join(sorted(skill_ids))}:{hash(arguments)}:{expand_dynamic}"
        if cache_key in self._context_cache:
            cached_result, cached_time = self._context_cache[cache_key]
            if datetime.now(UTC) - cached_time < self._context_ttl:
                return cached_result
            del self._context_cache[cache_key]

        # Get skills
        skills = await self.get_skills(skill_ids)
        if not skills:
            return SkillContextResult(
                prompt_addition="",
                allowed_tools=None,
                required_tools=set(),
                skill_ids=[],
            )

        # Build prompt addition
        from app.domain.services.prompts.skill_context import (
            build_skill_context,
            build_skill_context_async,
            get_allowed_tools_from_skills,
        )

        if expand_dynamic:
            prompt_addition = await build_skill_context_async(skills)
        else:
            prompt_addition = build_skill_context(skills)

        # Compute tool restrictions
        allowed_tools = get_allowed_tools_from_skills(skills)

        # Compute required tools
        required_tools: set[str] = set()
        for skill in skills:
            required_tools.update(skill.required_tools)

        result = SkillContextResult(
            prompt_addition=prompt_addition,
            allowed_tools=allowed_tools,
            required_tools=required_tools,
            skill_ids=[s.id for s in skills],
        )

        # Cache result
        self._context_cache[cache_key] = (result, datetime.now(UTC))

        return result

    def get_compiled_patterns(self, skill_id: str) -> list[re.Pattern]:
        """Get compiled trigger patterns for a skill."""
        return self._compiled_patterns.get(skill_id, [])

    def invalidate_skill(self, skill_id: str) -> None:
        """Invalidate a specific skill's cache."""
        if skill_id in self._skills:
            del self._skills[skill_id]
        if skill_id in self._compiled_patterns:
            del self._compiled_patterns[skill_id]
        # Clear context cache entries containing this skill
        keys_to_remove = [k for k in self._context_cache if skill_id in k]
        for key in keys_to_remove:
            del self._context_cache[key]

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._skills.clear()
        self._context_cache.clear()
        self._compiled_patterns.clear()
        self._last_refresh = None


async def get_skill_registry() -> SkillRegistry:
    """Get the singleton skill registry instance."""
    return await SkillRegistry.get_instance()


async def invalidate_skill_caches(skill_id: str) -> None:
    """Invalidate all caches for a specific skill.

    Invalidates both the SkillRegistry and SkillTriggerMatcher caches.
    Call this after skill create/update/delete operations.

    Args:
        skill_id: The ID of the skill that was modified
    """
    # Invalidate registry cache
    try:
        registry = await get_skill_registry()
        registry.invalidate_skill(skill_id)
        logger.debug(f"Invalidated SkillRegistry cache for skill: {skill_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate registry cache for {skill_id}: {e}")

    # Invalidate trigger matcher cache
    try:
        from app.domain.services.skill_trigger_matcher import invalidate_skill_triggers

        await invalidate_skill_triggers(skill_id)
        logger.debug(f"Invalidated TriggerMatcher cache for skill: {skill_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate trigger matcher for {skill_id}: {e}")


async def refresh_all_skill_caches() -> None:
    """Refresh all skill caches.

    Clears and reloads both SkillRegistry and SkillTriggerMatcher.
    Use sparingly - prefer invalidate_skill_caches for single skill changes.
    """
    # Clear and reload registry
    try:
        registry = await get_skill_registry()
        registry.clear_cache()
        await registry._load_skills()
        logger.info("Refreshed SkillRegistry cache")
    except Exception as e:
        logger.warning(f"Failed to refresh registry cache: {e}")

    # Refresh trigger matcher
    try:
        from app.domain.services.skill_trigger_matcher import invalidate_trigger_matcher

        await invalidate_trigger_matcher()
        logger.info("Refreshed TriggerMatcher cache")
    except Exception as e:
        logger.warning(f"Failed to refresh trigger matcher: {e}")
