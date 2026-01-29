#!/usr/bin/env python3
"""Reset development database - DESTRUCTIVE OPERATION.

This script will:
1. Drop the entire MongoDB database
2. Recreate all collections and indexes
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset_database():
    """Drop and recreate database."""
    settings = get_settings()

    logger.warning("="*60)
    logger.warning("  ⚠️  DEV DATABASE RESET - DESTRUCTIVE OPERATION")
    logger.warning("="*60)
    logger.warning("")
    logger.warning(f"Database: {settings.mongodb_database}")
    logger.warning(f"URI: {settings.mongodb_uri}")
    logger.warning("")
    logger.warning("This will DELETE ALL DATA in the database!")
    logger.warning("")

    # Require confirmation
    confirmation = input("Type 'yes' to confirm: ")
    if confirmation.lower() != 'yes':
        logger.info("Aborted.")
        return

    logger.info("")
    logger.info("🗑️  Dropping database...")

    # Connect to MongoDB
    if settings.mongodb_username and settings.mongodb_password:
        client = AsyncIOMotorClient(
            settings.mongodb_uri,
            username=settings.mongodb_username,
            password=settings.mongodb_password,
        )
    else:
        client = AsyncIOMotorClient(settings.mongodb_uri)

    try:
        # Drop the database
        await client.drop_database(settings.mongodb_database)
        logger.info("✅ Database dropped")

        logger.info("")
        logger.info("🔧 Reinitializing schema...")
        logger.info("")

        # Close client before running init script
        client.close()

        # Import and run init script
        from init_mongodb import init_mongodb
        await init_mongodb()

        logger.info("")
        logger.info("="*60)
        logger.info("✅ Database reset complete!")
        logger.info("="*60)
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Start the backend: ./dev.sh up -d")
        logger.info("  2. Create a test user via API")
        logger.info("  3. Start developing!")
        logger.info("")

    except Exception as e:
        logger.error(f"❌ Failed to reset database: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(reset_database())
