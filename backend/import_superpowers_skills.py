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
        print("No Superpowers skills found.")
        print("Make sure the superpowers-main directory exists in the project root.")
        return

    print(f"Found {len(SUPERPOWERS_SKILLS)} Superpowers skills to import")
    print("-" * 60)

    # Print skill list
    for skill in SUPERPOWERS_SKILLS:
        print(f"  - {skill.name} ({skill.id})")
        print(f"    Category: {skill.category.value}, Icon: {skill.icon}")
        print(f"    Invocation: {skill.invocation_type.value}")
        print(f"    Triggers: {len(skill.trigger_patterns)} pattern(s)")
        print()

    print("-" * 60)

    # Initialize MongoDB connection
    print("Connecting to MongoDB...")
    await get_mongodb().initialize()

    # Initialize Beanie with SkillDocument
    print("Initializing Beanie...")
    await init_beanie(
        database=get_mongodb().client[settings.mongodb_database],
        document_models=[SkillDocument],
    )

    # Update timestamps
    now = datetime.now(UTC)
    for skill in SUPERPOWERS_SKILLS:
        skill.updated_at = now

    # Import skills
    print("Importing Superpowers skills...")
    skill_service = get_skill_service()
    count = await skill_service.seed_official_skills(SUPERPOWERS_SKILLS)

    print(f"\nSuccessfully imported {count} Superpowers skills!")
    print("\nSkills are now available:")
    print("  - Auto-trigger via user input (for skills with trigger patterns)")
    print("  - Manual invocation via /skill-name command (coming in Phase 3)")
    print("  - AI invocation based on context")


if __name__ == "__main__":
    asyncio.run(main())
