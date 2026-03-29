#!/usr/bin/env python3
"""Reseed official skills."""

import asyncio

from app.infrastructure.models.documents import SkillDocument
from app.infrastructure.seeds.skills_seed import seed_official_skills
from app.infrastructure.storage.mongodb import get_mongodb, initialize_beanie


async def main():
    """Initialize database and seed official skills."""
    # Initialize MongoDB connection
    await get_mongodb().initialize()

    # Initialize Beanie with SkillDocument
    await initialize_beanie([SkillDocument])

    # Seed official skills
    await seed_official_skills()


if __name__ == "__main__":
    asyncio.run(main())
