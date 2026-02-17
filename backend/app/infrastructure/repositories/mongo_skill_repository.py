"""MongoDB implementation of SkillRepository.

Enhanced with marketplace features for skill discovery and sharing.
"""

import re
from datetime import UTC, datetime
from typing import Any

from app.domain.models.skill import Skill, SkillCategory, SkillSource
from app.domain.repositories.skill_repository import SkillRepository
from app.infrastructure.models.documents import SkillDocument

# Allowlist of fields that may be used for sorting in marketplace queries.
# Prevents NoSQL injection via arbitrary field names passed to MongoDB .sort().
ALLOWED_SORT_FIELDS: frozenset[str] = frozenset(
    {
        "community_rating",
        "install_count",
        "created_at",
        "updated_at",
        "name",
    }
)


class SkillSearchFilters:
    """Filters for skill marketplace search."""

    def __init__(
        self,
        query: str | None = None,
        category: SkillCategory | None = None,
        source: SkillSource | None = None,
        min_rating: float | None = None,
        tags: list[str] | None = None,
        is_featured: bool | None = None,
        is_public: bool = True,
    ) -> None:
        """Initialize search filters."""
        self.query = query
        self.category = category
        self.source = source
        self.min_rating = min_rating
        self.tags = tags or []
        self.is_featured = is_featured
        self.is_public = is_public

    def to_mongo_query(self) -> dict[str, Any]:
        """Convert filters to MongoDB query."""
        query: dict[str, Any] = {}

        if self.is_public is not None:
            query["is_public"] = self.is_public

        if self.category:
            query["category"] = self.category.value

        if self.source:
            query["source"] = self.source.value

        if self.min_rating:
            query["community_rating"] = {"$gte": self.min_rating}

        if self.tags:
            query["tags"] = {"$in": self.tags}

        if self.is_featured is not None:
            query["is_featured"] = self.is_featured

        if self.query:
            # Escape special regex characters to prevent regex injection
            escaped_query = re.escape(self.query)
            query["$or"] = [
                {"name": {"$regex": escaped_query, "$options": "i"}},
                {"description": {"$regex": escaped_query, "$options": "i"}},
            ]

        return query


class MongoSkillRepository(SkillRepository):
    """MongoDB implementation of SkillRepository."""

    async def get_all(self) -> list[Skill]:
        """Get all available skills."""
        documents = await SkillDocument.find_all().to_list()
        return [doc.to_domain() for doc in documents]

    async def get_by_id(self, skill_id: str) -> Skill | None:
        """Find a skill by its ID."""
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        return document.to_domain() if document else None

    async def get_by_category(self, category: SkillCategory) -> list[Skill]:
        """Get all skills in a category."""
        documents = await SkillDocument.find(SkillDocument.category == category).to_list()
        return [doc.to_domain() for doc in documents]

    async def get_by_ids(self, skill_ids: list[str]) -> list[Skill]:
        """Get multiple skills by their IDs."""
        if not skill_ids:
            return []
        documents = await SkillDocument.find({"skill_id": {"$in": skill_ids}}).to_list()
        return [doc.to_domain() for doc in documents]

    async def create(self, skill: Skill) -> Skill:
        """Create a new skill."""
        document = SkillDocument.from_domain(skill)
        await document.save()
        return document.to_domain()

    async def update(self, skill_id: str, skill: Skill) -> Skill | None:
        """Update an existing skill."""
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not document:
            return None

        document.update_from_domain(skill)
        document.updated_at = datetime.now(UTC)
        await document.save()
        return document.to_domain()

    async def upsert(self, skill: Skill) -> Skill:
        """Create or update a skill."""
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill.id)
        if document:
            document.update_from_domain(skill)
            document.updated_at = datetime.now(UTC)
            await document.save()
            return document.to_domain()

        return await self.create(skill)

    async def delete(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not document:
            return False
        await document.delete()
        return True

    async def get_by_owner(self, owner_id: str) -> list[Skill]:
        """Get all custom skills owned by a user.

        Args:
            owner_id: The user ID to filter by

        Returns:
            List of skills owned by the user
        """
        documents = await SkillDocument.find(SkillDocument.owner_id == owner_id).sort([("created_at", -1)]).to_list()
        return [doc.to_domain() for doc in documents]

    async def get_public_skills(self) -> list[Skill]:
        """Get all public/community skills.

        Returns:
            List of public skills shared by the community
        """
        documents = (
            await SkillDocument.find({"is_public": True, "source": SkillSource.COMMUNITY.value})
            .sort([("created_at", -1)])
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    # Marketplace methods

    async def search(
        self,
        filters: SkillSearchFilters,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "community_rating",
        sort_order: int = -1,
    ) -> tuple[list[Skill], int]:
        """Search skills in the marketplace.

        Args:
            filters: Search filters
            skip: Number of results to skip
            limit: Maximum results to return
            sort_by: Field to sort by
            sort_order: 1 for ascending, -1 for descending

        Returns:
            Tuple of (skills list, total count)
        """
        # Validate sort_by against allowlist to prevent NoSQL injection
        if sort_by not in ALLOWED_SORT_FIELDS:
            raise ValueError(
                f"Invalid sort field: '{sort_by}'. Allowed fields: {', '.join(sorted(ALLOWED_SORT_FIELDS))}"
            )

        query = filters.to_mongo_query()

        # Get total count
        total = await SkillDocument.find(query).count()

        # Get paginated results
        documents = await SkillDocument.find(query).sort([(sort_by, sort_order)]).skip(skip).limit(limit).to_list()

        return [doc.to_domain() for doc in documents], total

    async def get_featured(self, limit: int = 10) -> list[Skill]:
        """Get featured skills for the marketplace.

        Args:
            limit: Maximum number of featured skills

        Returns:
            List of featured skills
        """
        documents = (
            await SkillDocument.find({"is_public": True, "is_featured": True})
            .sort([("community_rating", -1)])
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def get_popular(self, limit: int = 10) -> list[Skill]:
        """Get most popular skills by usage/rating.

        Args:
            limit: Maximum number of skills

        Returns:
            List of popular skills
        """
        documents = (
            await SkillDocument.find({"is_public": True})
            .sort(
                [
                    ("install_count", -1),
                    ("community_rating", -1),
                ]
            )
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def get_recent(self, limit: int = 10) -> list[Skill]:
        """Get recently added public skills.

        Args:
            limit: Maximum number of skills

        Returns:
            List of recent skills
        """
        documents = await SkillDocument.find({"is_public": True}).sort([("created_at", -1)]).limit(limit).to_list()
        return [doc.to_domain() for doc in documents]

    async def get_by_tags(self, tags: list[str], limit: int = 20) -> list[Skill]:
        """Get skills by tags.

        Args:
            tags: List of tags to match
            limit: Maximum number of skills

        Returns:
            List of matching skills
        """
        documents = (
            await SkillDocument.find({"is_public": True, "tags": {"$in": tags}})
            .sort([("community_rating", -1)])
            .limit(limit)
            .to_list()
        )
        return [doc.to_domain() for doc in documents]

    async def rate_skill(self, skill_id: str, user_id: str, rating: float) -> bool:
        """Rate a skill.

        Args:
            skill_id: Skill to rate
            user_id: User rating the skill
            rating: Rating value (1-5)

        Returns:
            True if rating was successful
        """
        if not 1 <= rating <= 5:
            return False

        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not document:
            return False

        # Get or initialize rating data
        ratings = getattr(document, "ratings", {}) or {}

        # Update the rating
        ratings[user_id] = rating

        # Recalculate average
        avg_rating = sum(ratings.values()) / len(ratings) if ratings else 0

        # Update document
        await SkillDocument.find_one(SkillDocument.skill_id == skill_id).update(
            {
                "$set": {
                    "ratings": ratings,
                    "community_rating": avg_rating,
                    "rating_count": len(ratings),
                }
            }
        )

        return True

    async def increment_install_count(self, skill_id: str) -> bool:
        """Increment the install count for a skill.

        Args:
            skill_id: Skill that was installed

        Returns:
            True if update was successful
        """
        result = await SkillDocument.find_one(SkillDocument.skill_id == skill_id).update({"$inc": {"install_count": 1}})
        return result is not None

    async def publish_skill(self, skill_id: str, owner_id: str) -> bool:
        """Publish a skill to the marketplace.

        Args:
            skill_id: Skill to publish
            owner_id: Owner requesting publication

        Returns:
            True if publication was successful
        """
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not document:
            return False

        # Verify ownership
        if document.owner_id != owner_id:
            return False

        # Update to public
        document.is_public = True
        document.source = SkillSource.COMMUNITY
        document.updated_at = datetime.now(UTC)
        await document.save()

        return True

    async def unpublish_skill(self, skill_id: str, owner_id: str) -> bool:
        """Remove a skill from the marketplace.

        Args:
            skill_id: Skill to unpublish
            owner_id: Owner requesting removal

        Returns:
            True if removal was successful
        """
        document = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not document:
            return False

        # Verify ownership
        if document.owner_id != owner_id:
            return False

        # Update to private
        document.is_public = False
        document.source = SkillSource.CUSTOM
        document.updated_at = datetime.now(UTC)
        await document.save()

        return True

    async def fork_skill(self, skill_id: str, new_owner_id: str, new_name: str | None = None) -> Skill | None:
        """Fork a public skill for customization.

        Args:
            skill_id: Skill to fork
            new_owner_id: User forking the skill
            new_name: Optional new name for the fork

        Returns:
            The forked skill or None if fork failed
        """
        original = await SkillDocument.find_one(SkillDocument.skill_id == skill_id)
        if not original:
            return None

        # Create a copy with new ID
        import uuid

        forked_id = f"{skill_id}-fork-{uuid.uuid4().hex[:8]}"

        forked = Skill(
            id=forked_id,
            name=new_name or f"{original.name} (Fork)",
            description=original.description,
            category=original.category,
            source=SkillSource.CUSTOM,
            icon=original.icon,
            required_tools=original.required_tools.copy(),
            optional_tools=original.optional_tools.copy(),
            system_prompt_addition=original.system_prompt_addition,
            configurations=original.configurations.copy(),
            default_enabled=False,
            invocation_type=original.invocation_type,
            allowed_tools=original.allowed_tools.copy() if original.allowed_tools else None,
            supports_dynamic_context=original.supports_dynamic_context,
            trigger_patterns=original.trigger_patterns.copy(),
            version="1.0.0",
            author=None,
            owner_id=new_owner_id,
            is_public=False,
            parent_skill_id=skill_id,
        )

        return await self.create(forked)
