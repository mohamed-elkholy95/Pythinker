#!/usr/bin/env python3
"""Reseed official skills."""

import asyncio

from beanie import init_beanie

from app.core.config import get_settings
from app.infrastructure.models.documents import SkillDocument
from app.infrastructure.seeds.skills_seed import seed_official_skills
from app.infrastructure.storage.mongodb import get_mongodb


async def main():
    """Initialize database and seed official skills."""
    settings = get_settings()

    # Initialize MongoDB connection
    await get_mongodb().initialize()

    # Initialize Beanie with SkillDocument
    await init_beanie(
        database=get_mongodb().client[settings.mongodb_database],
        document_models=[SkillDocument],
    )

    # Seed official skills
    await seed_official_skills()


if __name__ == "__main__":
    asyncio.run(main())
