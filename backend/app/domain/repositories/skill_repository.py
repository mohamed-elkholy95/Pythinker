"""Repository interface for Skill aggregate.

Includes marketplace features for skill discovery and sharing.
"""

from typing import Any, Protocol

from app.domain.models.skill import Skill, SkillCategory


class SkillRepository(Protocol):
    """Repository interface for Skill aggregate."""

    async def get_all(self) -> list[Skill]:
        """Get all available skills."""
        ...

    async def get_by_id(self, skill_id: str) -> Skill | None:
        """Find a skill by its ID."""
        ...

    async def get_by_category(self, category: SkillCategory) -> list[Skill]:
        """Get all skills in a category."""
        ...

    async def get_by_ids(self, skill_ids: list[str]) -> list[Skill]:
        """Get multiple skills by their IDs."""
        ...

    async def create(self, skill: Skill) -> Skill:
        """Create a new skill."""
        ...

    async def update(self, skill_id: str, skill: Skill) -> Skill | None:
        """Update an existing skill."""
        ...

    async def upsert(self, skill: Skill) -> Skill:
        """Create or update a skill."""
        ...

    async def delete(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        ...

    async def get_by_owner(self, owner_id: str) -> list[Skill]:
        """Get all custom skills owned by a user."""
        ...

    async def get_public_skills(self) -> list[Skill]:
        """Get all public/community skills."""
        ...

    # Marketplace methods

    async def search(
        self,
        filters: Any,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "community_rating",
        sort_order: int = -1,
    ) -> tuple[list[Skill], int]:
        """Search skills in the marketplace."""
        ...

    async def get_featured(self, limit: int = 10) -> list[Skill]:
        """Get featured skills for the marketplace."""
        ...

    async def get_popular(self, limit: int = 10) -> list[Skill]:
        """Get most popular skills by usage/rating."""
        ...

    async def get_recent(self, limit: int = 10) -> list[Skill]:
        """Get recently added public skills."""
        ...

    async def get_by_tags(self, tags: list[str], limit: int = 20) -> list[Skill]:
        """Get skills by tags."""
        ...

    async def rate_skill(self, skill_id: str, user_id: str, rating: float) -> bool:
        """Rate a skill."""
        ...

    async def increment_install_count(self, skill_id: str) -> bool:
        """Increment the install count for a skill."""
        ...

    async def publish_skill(self, skill_id: str, owner_id: str) -> bool:
        """Publish a skill to the marketplace."""
        ...

    async def unpublish_skill(self, skill_id: str, owner_id: str) -> bool:
        """Remove a skill from the marketplace."""
        ...

    async def fork_skill(self, skill_id: str, new_owner_id: str, new_name: str | None = None) -> Skill | None:
        """Fork a public skill for customization."""
        ...
