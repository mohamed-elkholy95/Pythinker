#!/usr/bin/env python3
"""Import Superpowers skills into Pythinker.

This script imports all 14 Superpowers workflow skills from the superpowers-main
directory and adds them to MongoDB as OFFICIAL skills.

Usage:
    conda activate pythinker
    cd backend
    python import_superpowers_skills.py
"""

import asyncio
from datetime import UTC, datetime

from beanie import init_beanie

from app.application.services.skill_service import get_skill_service
from app.core.config import get_settings
from app.infrastructure.models.documents import SkillDocument
from app.infrastructure.seeds.superpowers_skills import SUPERPOWERS_SKILLS
from app.infrastructure.storage.mongodb import get_mongodb


async def main():
    """Initialize database and import Superpowers skills."""
    settings = get_settings()

    # Check if we have skills to import
    if not SUPERPOWERS_SKILLS:
        return

    # Print skill list
    for _skill in SUPERPOWERS_SKILLS:
        pass

    # Initialize MongoDB connection
    await get_mongodb().initialize()

    # Initialize Beanie with SkillDocument
    await init_beanie(
        database=get_mongodb().client[settings.mongodb_database],
        document_models=[SkillDocument],
    )

    # Update timestamps
    now = datetime.now(UTC)
    for skill in SUPERPOWERS_SKILLS:
        skill.updated_at = now

    # Import skills
    skill_service = get_skill_service()
    await skill_service.seed_official_skills(SUPERPOWERS_SKILLS)


if __name__ == "__main__":
    asyncio.run(main())
