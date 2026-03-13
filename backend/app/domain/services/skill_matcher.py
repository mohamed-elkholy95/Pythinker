"""Skill auto-detection from user messages.

Matches user messages against skill trigger patterns (regex)
and keyword overlap to identify relevant skills before planning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.domain.models.skill import Skill

logger = logging.getLogger(__name__)


@dataclass
class SkillMatch:
    """A matched skill with confidence and reason."""

    skill: Skill
    confidence: float
    reason: str


class SkillMatcher:
    """Matches user messages to relevant skills using trigger patterns."""

    def match(
        self,
        message: str,
        available_skills: list[Skill],
        threshold: float = 0.6,
    ) -> list[SkillMatch]:
        """Return skills matching the message, ranked by confidence descending."""
        if not message or not available_skills:
            return []

        matches: list[SkillMatch] = []
        message_lower = message.lower()

        for skill in available_skills:
            score, reason = self._compute_match_score(message_lower, skill)
            if score >= threshold:
                matches.append(SkillMatch(skill=skill, confidence=score, reason=reason))

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches

    def _compute_match_score(self, message_lower: str, skill: Skill) -> tuple[float, str]:
        """Score a skill against a message. Returns (score, reason)."""
        score = 0.0
        reasons: list[str] = []

        # 1. Trigger pattern matches (highest signal, capped at 1.0)
        pattern_hits = 0
        for pattern in skill.trigger_patterns:
            try:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    pattern_hits += 1
            except re.error:
                logger.warning("Invalid trigger pattern '%s' in skill '%s'", pattern, skill.id)
                continue

        if pattern_hits > 0:
            # A single pattern match is a strong, deliberate signal — full pattern score
            score += 0.7  # 70% weight for any pattern match

            reasons.append(f"Matched {pattern_hits} trigger pattern(s)")

        # 2. Category keyword overlap (0.3 weight)
        category_keywords = self._category_keywords(skill)
        keyword_hits = sum(1 for kw in category_keywords if kw in message_lower)
        if keyword_hits > 0 and category_keywords:
            keyword_score = min(1.0, keyword_hits / max(len(category_keywords), 1))
            score += keyword_score * 0.3
            reasons.append(f"Matched {keyword_hits} category keyword(s)")

        reason = "; ".join(reasons) if reasons else "No match"
        return score, reason

    def _category_keywords(self, skill: Skill) -> list[str]:
        """Extract keywords from skill name, category, and description."""
        words: list[str] = []
        words.extend(skill.name.lower().split())
        words.append(skill.category.value.lower())
        # Add required tool names as keywords (e.g., "browser" from "browser_navigate")
        for tool in skill.required_tools:
            parts = tool.split("_")
            words.extend(parts)
        return list(set(words))
