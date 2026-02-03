"""Skill Invocation Meta-Tool for Dynamic Skill Loading.

Implements Claude's meta-tool pattern where the agent can invoke skills
dynamically based on context. The tool lists available skills in its
description and expands skill content into the conversation when invoked.

This is the core of Claude's skills architecture:
- Skills are listed in tool description via <available_skills> section
- Agent calls this tool with skill name to load skill instructions
- Skill content is expanded and returned to guide subsequent actions

SECURITY: Dynamic context execution is delegated to skill_context module
which enforces command allowlisting and OFFICIAL-only restrictions.
"""

import logging
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
    """

    name = "skill_invoke"

    # Template for description - preserved as class constant for re-rendering
    _DESCRIPTION_TEMPLATE = """Invoke a skill to get specialized instructions for a task.

<skill_invocation_guide>
Use this tool when you recognize that a specific skill would help complete the task better.
Skills provide specialized prompts and guidelines for particular domains.

How to use:
- Call with the skill_name parameter
- The skill's instructions will be returned
- Follow those instructions for subsequent actions

When to use:
- User explicitly requests a skill with /skill-name
- Task matches a skill's domain (research, coding, data analysis, etc.)
- You need specialized guidelines for a complex task
</skill_invocation_guide>

<available_skills>
{available_skills}
</available_skills>
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

    def get_input_schema(self) -> dict[str, Any]:
        """Return the input schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The name/ID of the skill to invoke (e.g., 'research', 'coding', 'data-analysis')",
                },
                "arguments": {
                    "type": "string",
                    "description": "Optional arguments to pass to the skill (like /skill-name args)",
                    "default": "",
                },
            },
            "required": ["skill_name"],
        }

    async def execute(self, skill_name: str, arguments: str = "", **kwargs: Any) -> dict[str, Any]:
        """Execute skill invocation.

        Args:
            skill_name: The skill ID to invoke
            arguments: Optional arguments for the skill

        Returns:
            Dict with skill instructions or error message
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
        }

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


class SkillListTool(BaseTool):
    """Tool for listing available skills with their details."""

    name = "skill_list"
    description = "List all available skills with their descriptions and capabilities."

    def __init__(self, available_skills: list["Skill"] | None = None):
        """Initialize skill list tool.

        Args:
            available_skills: Pre-loaded list of available skills
        """
        super().__init__()
        self._available_skills = available_skills or []

    def set_available_skills(self, skills: list["Skill"]) -> None:
        """Update the available skills list."""
        self._available_skills = skills

    def get_input_schema(self) -> dict[str, Any]:
        """Return the input schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (research, coding, browser, etc.)",
                    "default": None,
                },
                "include_user_only": {
                    "type": "boolean",
                    "description": "Include skills that can only be invoked by users",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(
        self,
        category: str | None = None,
        include_user_only: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List available skills.

        Args:
            category: Optional category filter
            include_user_only: Whether to include user-only skills

        Returns:
            Dict with skills list
        """
        skills_list = []

        for skill in self._available_skills:
            # Filter by invocation type
            if not include_user_only and skill.invocation_type == SkillInvocationType.USER:
                continue

            # Filter by category
            if category:
                skill_cat = skill.category.value if hasattr(skill.category, "value") else skill.category
                if skill_cat.lower() != category.lower():
                    continue

            invocation = (
                skill.invocation_type.value if hasattr(skill.invocation_type, "value") else skill.invocation_type
            )

            skills_list.append(
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category.value if hasattr(skill.category, "value") else skill.category,
                    "invocation": invocation,
                    "required_tools": skill.required_tools,
                }
            )

        return {
            "success": True,
            "total": len(skills_list),
            "skills": skills_list,
        }


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
