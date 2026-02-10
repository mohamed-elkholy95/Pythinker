"""Skill activation framework for explicit/controlled skill usage.

This service centralizes how incoming user messages activate skills.
Default policy keeps auto-triggering disabled; skills are activated only by:
1) explicit chat-box skill selection
2) slash-command invocation (e.g. /brainstorm)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from app.domain.services.command_registry import get_command_registry

logger = logging.getLogger(__name__)

_SKILL_CREATOR_EMBEDDED_PATTERN = re.compile(r"(^|\s)/skill-creator(\s|$)", re.IGNORECASE)


class SkillActivationSource(str, Enum):
    """How a skill was activated for the current message."""

    CHAT_SELECTION = "chat_selection"
    COMMAND = "command"
    EMBEDDED_COMMAND = "embedded_command"
    AUTO_TRIGGER = "auto_trigger"


@dataclass(slots=True)
class SkillActivationResult:
    """Resolved skill activation state for an incoming message."""

    skill_ids: list[str] = field(default_factory=list)
    activation_sources: dict[str, list[str]] = field(default_factory=dict)
    command_skill_id: str | None = None
    auto_trigger_enabled: bool = False
    auto_triggered_skill_ids: list[str] = field(default_factory=list)


class SkillActivationFramework:
    """Resolve effective skill activation for a message."""

    async def resolve(
        self,
        message: str,
        selected_skills: list[str] | None,
        *,
        auto_trigger_enabled: bool = False,
    ) -> SkillActivationResult:
        selected = {skill_id for skill_id in (selected_skills or []) if skill_id}
        source_index: dict[str, set[str]] = {
            skill_id: {SkillActivationSource.CHAT_SELECTION.value} for skill_id in selected
        }

        command_skill_id = self._resolve_command_skill(message)
        if command_skill_id:
            source_index.setdefault(command_skill_id, set()).add(SkillActivationSource.COMMAND.value)
        elif self._has_embedded_skill_creator_command(message):
            # Backward-compatible fallback used by existing "Build with Pythinker" entry points.
            source_index.setdefault("skill-creator", set()).add(SkillActivationSource.EMBEDDED_COMMAND.value)

        auto_triggered_skill_ids: list[str] = []
        if auto_trigger_enabled:
            auto_triggered_skill_ids = await self._resolve_auto_triggered_skills(message, set(source_index.keys()))
            for skill_id in auto_triggered_skill_ids:
                source_index.setdefault(skill_id, set()).add(SkillActivationSource.AUTO_TRIGGER.value)

        activation_sources = {skill_id: sorted(sources) for skill_id, sources in source_index.items()}
        skill_ids = sorted(source_index.keys())

        return SkillActivationResult(
            skill_ids=skill_ids,
            activation_sources=activation_sources,
            command_skill_id=command_skill_id,
            auto_trigger_enabled=auto_trigger_enabled,
            auto_triggered_skill_ids=auto_triggered_skill_ids,
        )

    def _resolve_command_skill(self, message: str) -> str | None:
        try:
            command_registry = get_command_registry()
            skill_id, _remaining = command_registry.parse_command(message)
            if skill_id:
                logger.info("Command invoked skill activation: %s -> %s", message.split()[0], skill_id)
            return skill_id
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Failed to parse skill command: %s", exc)
            return None

    async def _resolve_auto_triggered_skills(self, message: str, selected: set[str]) -> list[str]:
        try:
            from app.domain.services.skill_trigger_matcher import get_skill_trigger_matcher

            matcher = await get_skill_trigger_matcher()
            matches = await matcher.find_matching_skills(message, max_matches=3, min_confidence=0.3)
            candidates = [match.skill_id for match in matches]
            return sorted({skill_id for skill_id in candidates if skill_id not in selected})
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Failed to auto-trigger skills: %s", exc)
            return []

    def _has_embedded_skill_creator_command(self, message: str) -> bool:
        return bool(_SKILL_CREATOR_EMBEDDED_PATTERN.search(message))


_skill_activation_framework: SkillActivationFramework | None = None


def get_skill_activation_framework() -> SkillActivationFramework:
    """Get singleton skill activation framework."""
    global _skill_activation_framework
    if _skill_activation_framework is None:
        _skill_activation_framework = SkillActivationFramework()
    return _skill_activation_framework
