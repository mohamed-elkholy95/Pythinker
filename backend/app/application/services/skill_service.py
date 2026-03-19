"""Skill service for managing agent skills.

This service handles:
- Listing available skills
- User skill preferences (enable/disable, configuration)
- Getting tools required by enabled skills
"""

import logging
from typing import Any

from app.domain.models.skill import Skill, SkillCategory, UserSkillConfig
from app.domain.repositories.skill_repository import SkillRepository

logger = logging.getLogger(__name__)


class SkillService:
    """Service for managing agent skills."""

    def __init__(self, skill_repo: SkillRepository | None = None):
        """Initialize the skill service.

        Args:
            skill_repo: Optional skill repository (creates default if not provided)
        """
        if skill_repo is None:
            from app.infrastructure.repositories.mongo_skill_repository import MongoSkillRepository

            skill_repo = MongoSkillRepository()
        self._skill_repo = skill_repo

    async def get_available_skills(self) -> list[Skill]:
        """Get all available skills.

        Returns:
            List of all available skills
        """
        return await self._skill_repo.get_all()

    async def get_skill_by_id(self, skill_id: str) -> Skill | None:
        """Get a skill by its ID.

        Args:
            skill_id: The skill ID (slug)

        Returns:
            The skill if found, None otherwise
        """
        return await self._skill_repo.get_by_id(skill_id)

    async def get_skills_by_category(self, category: SkillCategory) -> list[Skill]:
        """Get all skills in a category.

        Args:
            category: The skill category

        Returns:
            List of skills in the category
        """
        return await self._skill_repo.get_by_category(category)

    async def get_skills_by_ids(self, skill_ids: list[str]) -> list[Skill]:
        """Get multiple skills by their IDs.

        Args:
            skill_ids: List of skill IDs

        Returns:
            List of matching skills
        """
        if not skill_ids:
            return []
        return await self._skill_repo.get_by_ids(skill_ids)

    async def create_skill(self, skill: Skill) -> Skill:
        """Create a new skill.

        Args:
            skill: The skill to create

        Returns:
            The created skill
        """
        return await self._skill_repo.create(skill)

    async def update_skill(self, skill_id: str, skill: Skill) -> Skill | None:
        """Update an existing skill.

        Args:
            skill_id: The skill ID to update
            skill: The updated skill data

        Returns:
            The updated skill if found, None otherwise
        """
        return await self._skill_repo.update(skill_id, skill)

    async def upsert_skill(self, skill: Skill) -> Skill:
        """Create or update a skill.

        Args:
            skill: The skill to upsert

        Returns:
            The upserted skill
        """
        return await self._skill_repo.upsert(skill)

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.

        Args:
            skill_id: The skill ID to delete

        Returns:
            True if deleted, False if not found
        """
        return await self._skill_repo.delete(skill_id)

    async def get_skills_by_owner(self, owner_id: str) -> list[Skill]:
        """Get all custom skills owned by a user.

        Args:
            owner_id: The user ID

        Returns:
            List of skills owned by the user
        """
        return await self._skill_repo.get_by_owner(owner_id)

    async def get_public_skills(self) -> list[Skill]:
        """Get all public/community skills.

        Returns:
            List of public skills
        """
        return await self._skill_repo.get_public_skills()

    def get_skill_tools(self, skills: list[Skill]) -> set[str]:
        """Get all tools required by a list of skills.

        Args:
            skills: List of skills

        Returns:
            Set of tool names required by the skills
        """
        tool_names: set[str] = set()
        for skill in skills:
            tool_names.update(skill.required_tools)
            tool_names.update(skill.optional_tools)
        return tool_names

    def get_skill_prompt_additions(self, skills: list[Skill]) -> list[str]:
        """Get system prompt additions from skills.

        Args:
            skills: List of skills

        Returns:
            List of system prompt additions (non-empty strings)
        """
        return [skill.system_prompt_addition for skill in skills if skill.system_prompt_addition]

    async def get_tools_for_skill_ids(self, skill_ids: list[str]) -> set[str]:
        """Get all tools required by a list of skill IDs.

        Args:
            skill_ids: List of skill IDs

        Returns:
            Set of tool names required by the skills
        """
        if not skill_ids:
            return set()

        skills = await self.get_skills_by_ids(skill_ids)
        return self.get_skill_tools(skills)

    def build_user_skill_configs(
        self,
        skills: list[Skill],
        enabled_skill_ids: list[str],
        user_configs: dict[str, dict],
    ) -> list[UserSkillConfig]:
        """Build user skill configurations from skills and user settings.

        Args:
            skills: List of available skills
            enabled_skill_ids: List of skill IDs the user has enabled
            user_configs: User's per-skill configurations

        Returns:
            List of UserSkillConfig for each skill
        """
        configs = []
        enabled_set = set(enabled_skill_ids)

        for i, skill in enumerate(skills):
            configs.append(
                UserSkillConfig(
                    skill_id=skill.id,
                    enabled=skill.id in enabled_set,
                    config=user_configs.get(skill.id, {}),
                    order=i,
                )
            )

        return configs

    async def generate_skill_draft(
        self,
        name: str,
        description: str,
        required_tools: list[str],
        optional_tools: list[str],
        llm: Any,
    ) -> dict[str, Any]:
        """Generate a structured skill draft using the configured LLM.

        Returns a dict with:
            - instructions: SKILL.md body markdown
            - description_suggestion: improved trigger-oriented description
            - resource_plan: suggested bundled resources for future phases
        """
        tools_section = ""
        if required_tools or optional_tools:
            all_tools = [*required_tools, *optional_tools]
            tools_section = f"\nAvailable tools: {', '.join(all_tools)}"

        system_prompt = (
            "You are a skill instruction writer for Pythinker, an AI agent platform.\n"
            "Given a skill name, description, and available tools, generate:\n\n"
            "1. A SKILL.md body in markdown with:\n"
            "   - Purpose (1-2 sentences)\n"
            "   - Step-by-step workflow (numbered)\n"
            "   - Guidelines and constraints (bulleted)\n"
            "   - Example outputs (1-2 examples)\n\n"
            "2. Keep under 3000 characters. Use imperative form. Be specific.\n"
            "3. Reference the available tools naturally in the workflow steps.\n"
            "4. Write instructions the agent can follow directly."
        )

        user_prompt = (
            f"Skill name: {name}\n"
            f"Skill description: {description}"
            f"{tools_section}\n\n"
            "Generate the SKILL.md body markdown."
        )

        response = await llm.ask(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        instructions = (response.get("content") or "").strip()

        # Generate a trigger-oriented description suggestion
        desc_suggestion = description
        if len(description) < 80:
            desc_suggestion = (
                f"{description} Use this skill whenever the task involves "
                f"{name.replace('-', ' ')} workflows or related operations."
            )

        return {
            "instructions": instructions,
            "description_suggestion": desc_suggestion,
            "resource_plan": {
                "references": [],
                "scripts": [],
                "templates": [],
            },
        }

    async def seed_official_skills(self, skills: list[Skill]) -> int:
        """Seed official skills into the database.

        Args:
            skills: List of official skills to seed

        Returns:
            Number of skills upserted
        """
        count = 0
        for skill in skills:
            await self._skill_repo.upsert(skill)
            count += 1
            logger.info(f"Seeded skill: {skill.id}")

        return count


# Global singleton instance
_skill_service: SkillService | None = None


def get_skill_service() -> SkillService:
    """Get the global SkillService instance."""
    global _skill_service
    if _skill_service is None:
        _skill_service = SkillService()
    return _skill_service
