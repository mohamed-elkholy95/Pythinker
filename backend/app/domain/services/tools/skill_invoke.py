"""Skill Invocation Meta-Tool for Dynamic Skill Loading.

Implements Claude's meta-tool pattern where the agent can invoke skills
dynamically based on context. The tool lists available skills in its
description and expands skill content into the conversation when invoked.

This is the core of Claude's skills architecture:
- Skills are listed in tool description via <available_skills> section
- Agent calls this tool with skill name to load skill instructions
- Skill content is expanded and returned to guide subsequent actions

Enterprise-grade enforcement (Phase 2):
- Priority-driven tool description instructs LLM to invoke BEFORE other tools
- Strict schema with enum constraints prevents hallucinated skill names
- Enforcement metadata returned with workflow steps for tracking

SECURITY: Dynamic context execution is delegated to skill_context module
which enforces command allowlisting and OFFICIAL-only restrictions.
"""

import logging
import re
from typing import TYPE_CHECKING, Any

from app.domain.models.skill import SkillInvocationType
from app.domain.services.tools.base import BaseTool

if TYPE_CHECKING:
    from app.domain.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillInvokeTool(BaseTool):
    """Meta-tool for invoking skills dynamically.

    When invoked, this tool:
    1. Validates the skill exists and can be AI-invoked
    2. Expands any dynamic context (!command syntax)
    3. Returns the skill's system_prompt_addition as instructions
    4. Returns enforcement metadata with workflow steps (Phase 5)
    """

    name = "skill_invoke"

    # Priority-driven description template (Phase 2b)
    _DESCRIPTION_TEMPLATE = """PRIORITY: Invoke a skill BEFORE using other tools when the task matches a skill domain.

<skill_invocation_protocol>
## When to invoke (MANDATORY):
- Task involves research, data analysis, coding, or any listed skill domain
- You haven't loaded skill instructions for the current step yet
- Task complexity benefits from specialized workflow guidance

## Invocation is the FIRST action you should take for any matching task.

Available skill domains:
{available_skills}
</skill_invocation_protocol>
"""

    # Initial description - will be updated by _update_description()
    description = _DESCRIPTION_TEMPLATE.format(available_skills="No skills currently available.")

    def __init__(
        self,
        available_skills: list["Skill"] | None = None,
        session_id: str | None = None,
    ):
        """Initialize skill invoke tool.

        Args:
            available_skills: Pre-loaded list of available skills for the session
            session_id: Current session ID for context
        """
        super().__init__()
        self._available_skills = available_skills or []
        self._session_id = session_id
        self._skill_cache: dict[str, Skill] = {}
        self._update_description()

    def _update_description(self) -> None:
        """Update tool description with available skills list.

        Uses the preserved template to re-render the description,
        allowing multiple updates without losing the placeholder.
        """
        if not self._available_skills:
            skills_list = "No skills currently available."
        else:
            skills_lines = []
            for skill in self._available_skills:
                # Only list AI-invokable skills
                if skill.invocation_type in (SkillInvocationType.AI, SkillInvocationType.BOTH):
                    skills_lines.append(f"- **{skill.id}**: {skill.description}")
                    self._skill_cache[skill.id] = skill

            skills_list = "\n".join(skills_lines) if skills_lines else "No AI-invokable skills available."

        # Use the preserved template instead of self.description
        self.description = self._DESCRIPTION_TEMPLATE.format(available_skills=skills_list)

    def set_available_skills(self, skills: list["Skill"]) -> None:
        """Update the available skills list.

        Args:
            skills: List of skills available for invocation
        """
        self._available_skills = skills
        self._skill_cache.clear()
        self._update_description()

    def _get_ai_invokable_skill_ids(self) -> list[str]:
        """Return list of skill IDs that can be AI-invoked."""
        return [
            s.id
            for s in self._available_skills
            if s.invocation_type in (SkillInvocationType.AI, SkillInvocationType.BOTH)
        ]

    def get_input_schema(self) -> dict[str, Any]:
        """Return the input schema for this tool.

        When strict schema is enabled, includes enum constraints to prevent
        hallucinated skill names and additionalProperties: false for strict
        mode compliance (Phase 2a).
        """
        skill_ids = self._get_ai_invokable_skill_ids()

        # Build skill_name property with optional enum constraint
        skill_name_prop: dict[str, Any] = {
            "type": "string",
            "description": "The name/ID of the skill to invoke",
        }

        # Add enum constraint when strict schema is enabled and skills are available
        if skill_ids:
            try:
                from app.core.config import get_settings

                settings = get_settings()
                if getattr(settings, "skill_strict_schema_enabled", True):
                    skill_name_prop["enum"] = skill_ids
            except Exception:
                # Fallback: add enum anyway for safety
                skill_name_prop["enum"] = skill_ids

        return {
            "type": "object",
            "properties": {
                "skill_name": skill_name_prop,
            },
            "required": ["skill_name"],
            "additionalProperties": False,
        }

    async def execute(self, skill_name: str, arguments: str = "", **kwargs: Any) -> dict[str, Any]:
        """Execute skill invocation.

        Args:
            skill_name: The skill ID to invoke
            arguments: Optional arguments for the skill

        Returns:
            Dict with skill instructions, enforcement metadata, or error message
        """
        # Normalize skill name (handle /skill-name format)
        skill_name = skill_name.lstrip("/").lower().strip()

        # Find the skill
        skill = self._skill_cache.get(skill_name)

        if not skill:
            # Try to fetch from service
            try:
                from app.application.services.skill_service import get_skill_service

                skill_service = get_skill_service()
                skill = await skill_service.get_skill_by_id(skill_name)
            except Exception as e:
                logger.warning(f"Failed to fetch skill {skill_name}: {e}")
                skill = None

        if not skill:
            available = list(self._skill_cache.keys())
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found.",
                "available_skills": available,
                "hint": f"Available skills: {', '.join(available) if available else 'none'}",
            }

        # Check if AI can invoke this skill
        if skill.invocation_type == SkillInvocationType.USER:
            return {
                "success": False,
                "error": f"Skill '{skill_name}' can only be invoked by the user via /{skill_name}",
                "hint": "Ask the user to invoke this skill directly.",
            }

        # Build skill content
        content = await self._build_skill_content(skill, arguments)

        logger.info(f"Invoked skill '{skill_name}' for session {self._session_id}")

        return {
            "success": True,
            "skill_name": skill.name,
            "skill_id": skill.id,
            "category": skill.category.value if hasattr(skill.category, "value") else skill.category,
            "instructions": content,
            "required_tools": skill.required_tools,
            "allowed_tools": skill.allowed_tools,
            "message": f"The '{skill.name}' skill is now active. Follow the instructions below.",
            "enforcement": {
                "must_use_tools": skill.required_tools,
                "workflow_steps": self._extract_workflow_steps(content),
                "completion_criteria": "Follow ALL steps in the skill instructions",
            },
        }

    @staticmethod
    def _extract_workflow_steps(content: str) -> list[str]:
        """Extract workflow steps from skill instructions for tracking.

        Parses numbered steps, bulleted steps with **Step** markers, and
        heading-level steps from the skill's system_prompt_addition.
        """
        steps: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r"^(#{1,3}\s+Step\s+\d|[\d]+\.\s|[-*]\s+\*\*Step)", stripped):
                steps.append(stripped)
        return steps[:10]  # Cap at 10 steps

    async def _build_skill_content(self, skill: "Skill", arguments: str = "") -> str:
        """Build the skill content with dynamic context expansion.

        Delegates to the centralized skill_context module which enforces
        security restrictions on dynamic context expansion.

        Args:
            skill: The skill to build content for
            arguments: Optional arguments

        Returns:
            Expanded skill content
        """
        from app.domain.services.prompts.skill_context import build_skill_content

        return await build_skill_content(skill, arguments)


def create_skill_invoke_tool(
    available_skills: list["Skill"] | None = None,
    session_id: str | None = None,
) -> SkillInvokeTool:
    """Factory function to create a skill invoke tool.

    Args:
        available_skills: List of skills available for invocation
        session_id: Current session ID

    Returns:
        Configured SkillInvokeTool instance
    """
    return SkillInvokeTool(available_skills=available_skills, session_id=session_id)
