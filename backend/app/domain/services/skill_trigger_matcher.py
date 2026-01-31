"""Skill Trigger Pattern Matching Service.

Automatically detects skills that should be activated based on
message content matching against skill trigger patterns.

Implements Claude Code's auto-activation pattern.
"""

import logging
import re
from dataclasses import dataclass

from app.domain.models.skill import Skill

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """Result of a skill pattern match."""

    skill: "Skill"
    skill_id: str
    pattern: str
    matched_text: str
    confidence: float

    def __repr__(self) -> str:
        return f"SkillMatch(skill_id={self.skill_id}, confidence={self.confidence:.2f})"


class SkillTriggerMatcher:
    """Match incoming messages against skill trigger patterns.

    Provides auto-activation of skills based on message content
    matching regex patterns defined in skill configurations.
    """

    def __init__(self) -> None:
        self._compiled_patterns: dict[str, list[tuple[re.Pattern, str]]] = {}
        self._skills_cache: dict[str, Skill] = {}
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure patterns are compiled from registry."""
        if self._initialized:
            return

        try:
            from app.domain.services.skill_registry import get_skill_registry

            registry = await get_skill_registry()
            skills = await registry.get_available_skills()

            from app.domain.models.skill import SkillInvocationType

            for skill in skills:
                # Only include AI-invokable skills with trigger patterns
                if skill.trigger_patterns and skill.invocation_type in (
                    SkillInvocationType.AI,
                    SkillInvocationType.BOTH,
                ):
                    patterns = []
                    for pattern_str in skill.trigger_patterns:
                        try:
                            compiled = re.compile(pattern_str, re.IGNORECASE)
                            patterns.append((compiled, pattern_str))
                        except re.error as e:
                            logger.warning(f"Invalid trigger pattern '{pattern_str}' for skill {skill.id}: {e}")

                    if patterns:
                        self._compiled_patterns[skill.id] = patterns
                        self._skills_cache[skill.id] = skill

            self._initialized = True
            logger.debug(f"SkillTriggerMatcher initialized with {len(self._compiled_patterns)} skills")

        except Exception as e:
            logger.warning(f"Failed to initialize SkillTriggerMatcher: {e}")
            self._initialized = True  # Avoid repeated failures

    async def find_matching_skills(
        self,
        message: str,
        max_matches: int = 3,
        min_confidence: float = 0.3,
    ) -> list[SkillMatch]:
        """Find skills whose trigger patterns match the message.

        Args:
            message: User message to match against patterns
            max_matches: Maximum number of skills to return
            min_confidence: Minimum confidence score (0.0-1.0) for inclusion

        Returns:
            List of SkillMatch objects sorted by confidence (highest first)
        """
        await self._ensure_initialized()

        if not message or not self._compiled_patterns:
            return []

        matches: list[SkillMatch] = []
        message_len = len(message)

        for skill_id, patterns in self._compiled_patterns.items():
            skill = self._skills_cache.get(skill_id)
            if not skill:
                continue

            best_match: SkillMatch | None = None
            best_confidence = 0.0

            for compiled_pattern, pattern_str in patterns:
                match = compiled_pattern.search(message)
                if match:
                    confidence = self._compute_confidence(match, message_len)
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = SkillMatch(
                            skill=skill,
                            skill_id=skill_id,
                            pattern=pattern_str,
                            matched_text=match.group(),
                            confidence=confidence,
                        )

            if best_match and best_match.confidence >= min_confidence:
                matches.append(best_match)

        # Sort by confidence and return top matches
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:max_matches]

    def _compute_confidence(self, match: re.Match, message_len: int) -> float:
        """Compute confidence score for a pattern match.

        Higher confidence for:
        - Longer matches relative to message length
        - Matches at the beginning of the message
        - Matches of complete words

        Args:
            match: The regex match object
            message_len: Total message length

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if message_len == 0:
            return 0.0

        matched_text = match.group()
        match_len = len(matched_text)

        # Factor 1: Match length ratio (longer matches = more specific)
        length_score = min(match_len / max(message_len, 1), 1.0)

        # Factor 2: Position score (earlier = more relevant)
        position_score = 1.0 - (match.start() / max(message_len, 1))

        # Factor 3: Word boundary bonus
        word_boundary_bonus = 0.0
        if match.start() == 0 or match.string[match.start() - 1].isspace():
            word_boundary_bonus += 0.1
        if match.end() == message_len or match.string[match.end()].isspace():
            word_boundary_bonus += 0.1

        # Weighted combination
        confidence = (length_score * 0.4) + (position_score * 0.4) + word_boundary_bonus

        return min(confidence, 1.0)

    async def get_suggested_skills(
        self,
        message: str,
        current_skills: list[str] | None = None,
        max_suggestions: int = 2,
    ) -> list[str]:
        """Get skill ID suggestions for a message.

        Convenience method that returns just skill IDs.

        Args:
            message: User message to analyze
            current_skills: Skills already selected (excluded from results)
            max_suggestions: Maximum suggestions to return

        Returns:
            List of skill IDs to suggest
        """
        current_skills = current_skills or []

        matches = await self.find_matching_skills(message, max_matches=max_suggestions + len(current_skills))

        # Filter out already-selected skills
        suggestions = [m.skill_id for m in matches if m.skill_id not in current_skills]

        return suggestions[:max_suggestions]

    def reset(self) -> None:
        """Reset the matcher state (for testing)."""
        self._compiled_patterns.clear()
        self._skills_cache.clear()
        self._initialized = False

    async def invalidate(self) -> None:
        """Invalidate cached patterns and reload from registry.

        Call this when skills are created, updated, or deleted
        to ensure trigger patterns stay in sync.
        """
        logger.debug("Invalidating SkillTriggerMatcher cache")
        self.reset()
        await self._ensure_initialized()

    async def invalidate_skill(self, skill_id: str) -> None:
        """Invalidate a specific skill from the cache.

        More efficient than full invalidation when only one skill changed.

        Args:
            skill_id: The ID of the skill that changed
        """
        if skill_id in self._compiled_patterns:
            del self._compiled_patterns[skill_id]
        if skill_id in self._skills_cache:
            del self._skills_cache[skill_id]

        # Re-fetch just this skill if needed
        try:
            from app.domain.models.skill import SkillInvocationType
            from app.domain.services.skill_registry import get_skill_registry

            registry = await get_skill_registry()
            skill = await registry.get_skill(skill_id)

            if skill and skill.trigger_patterns and skill.invocation_type in (
                SkillInvocationType.AI,
                SkillInvocationType.BOTH,
            ):
                patterns = []
                for pattern_str in skill.trigger_patterns:
                    try:
                        compiled = re.compile(pattern_str, re.IGNORECASE)
                        patterns.append((compiled, pattern_str))
                    except re.error as e:
                        logger.warning(f"Invalid trigger pattern '{pattern_str}' for skill {skill_id}: {e}")

                if patterns:
                    self._compiled_patterns[skill_id] = patterns
                    self._skills_cache[skill_id] = skill

        except Exception as e:
            logger.warning(f"Failed to refresh skill {skill_id} in trigger matcher: {e}")


# Module-level singleton
_trigger_matcher: SkillTriggerMatcher | None = None


async def get_skill_trigger_matcher() -> SkillTriggerMatcher:
    """Get the singleton trigger matcher instance."""
    global _trigger_matcher
    if _trigger_matcher is None:
        _trigger_matcher = SkillTriggerMatcher()
    return _trigger_matcher


async def invalidate_trigger_matcher() -> None:
    """Invalidate the trigger matcher cache.

    Call this after skill creation/update/deletion.
    """
    matcher = await get_skill_trigger_matcher()
    await matcher.invalidate()


async def invalidate_skill_triggers(skill_id: str) -> None:
    """Invalidate trigger patterns for a specific skill.

    Args:
        skill_id: The ID of the skill that was modified
    """
    matcher = await get_skill_trigger_matcher()
    await matcher.invalidate_skill(skill_id)
