#!/usr/bin/env python3
"""Initialize MongoDB schema with all collections and indexes.

This script sets up:
- All collections with proper indexes
- GridFS buckets for screenshots and artifacts
- Multi-task and workspace indexes
- Session metrics indexes
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import contextlib
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_mongodb():
    """Initialize MongoDB schema."""
    settings = get_settings()

    logger.info(f"Connecting to MongoDB: {settings.mongodb_uri}")

    # Connect to MongoDB
    if settings.mongodb_username and settings.mongodb_password:
        client = AsyncIOMotorClient(
            settings.mongodb_uri,
            username=settings.mongodb_username,
            password=settings.mongodb_password,
        )
    else:
        client = AsyncIOMotorClient(settings.mongodb_uri)

    db = client[settings.mongodb_database]

    try:
        # Verify connection
        await client.admin.command("ping")
        logger.info("✅ Connected to MongoDB")

        # ====================================
        # 1. SESSIONS COLLECTION
        # ====================================
        logger.info("Setting up sessions collection...")

        # Drop existing indexes (fresh start)
        with contextlib.suppress(Exception):
            await db.sessions.drop_indexes()

        # Create indexes for sessions
        await db.sessions.create_index("user_id")
        await db.sessions.create_index("agent_id")
        await db.sessions.create_index("created_at")
        await db.sessions.create_index("updated_at")
        await db.sessions.create_index("status")
        await db.sessions.create_index("is_shared")

        # Multi-task indexes (Phase 1)
        await db.sessions.create_index("multi_task_challenge.id")
        await db.sessions.create_index("budget_paused")
        await db.sessions.create_index("complexity_score")

        # Compound indexes for common queries
        await db.sessions.create_index([("user_id", 1), ("created_at", -1)])
        await db.sessions.create_index([("user_id", 1), ("status", 1)])

        logger.info("✅ Sessions collection configured")

        # ====================================
        # 2. EVENTS COLLECTION
        # ====================================
        logger.info("Setting up events collection...")

        with contextlib.suppress(Exception):
            await db.events.drop_indexes()

        await db.events.create_index("session_id")
        await db.events.create_index("type")
        await db.events.create_index("timestamp")
        await db.events.create_index([("session_id", 1), ("timestamp", 1)])

        logger.info("✅ Events collection configured")

        # ====================================
        # 3. USERS COLLECTION
        # ====================================
        logger.info("Setting up users collection...")

        with contextlib.suppress(Exception):
            await db.users.drop_indexes()

        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.users.create_index("created_at")

        logger.info("✅ Users collection configured")

        # ====================================
        # 4. USAGE TRACKING COLLECTIONS
        # ====================================
        logger.info("Setting up usage tracking collections...")

        # Usage records
        with contextlib.suppress(Exception):
            await db.usage_records.drop_indexes()

        await db.usage_records.create_index("user_id")
        await db.usage_records.create_index("session_id")
        await db.usage_records.create_index("created_at")
        await db.usage_records.create_index([("user_id", 1), ("created_at", -1)])
        await db.usage_records.create_index([("session_id", 1), ("created_at", -1)])

        # Session usage
        with contextlib.suppress(Exception):
            await db.session_usage.drop_indexes()

        await db.session_usage.create_index("session_id", unique=True)
        await db.session_usage.create_index("user_id")
        await db.session_usage.create_index("last_activity")

        # Daily aggregates
        with contextlib.suppress(Exception):
            await db.daily_usage.drop_indexes()

        await db.daily_usage.create_index([("user_id", 1), ("date", -1)], unique=True)
        await db.daily_usage.create_index("date")

        logger.info("✅ Usage tracking collections configured")

        # ====================================
        # 5. SESSION METRICS COLLECTION (Phase 1)
        # ====================================
        logger.info("Setting up session metrics collection...")

        with contextlib.suppress(Exception):
            await db.session_metrics.drop_indexes()

        await db.session_metrics.create_index("session_id", unique=True)
        await db.session_metrics.create_index("user_id")
        await db.session_metrics.create_index("started_at")
        await db.session_metrics.create_index("updated_at")
        await db.session_metrics.create_index([("user_id", 1), ("started_at", -1)])

        logger.info("✅ Session metrics collection configured")

        # ====================================
        # 6. GRIDFS BUCKETS (Phase 1/2)
        # ====================================
        logger.info("Setting up GridFS buckets...")

        # Screenshots bucket
        try:
            await db["screenshots.files"].drop_indexes()
            await db["screenshots.chunks"].drop_indexes()
        except Exception:
            pass

        await db["screenshots.files"].create_index("uploadDate")
        await db["screenshots.files"].create_index("metadata.session_id")
        await db["screenshots.files"].create_index("metadata.task_id")
        await db["screenshots.files"].create_index("metadata.capture_reason")

        # Artifacts bucket
        try:
            await db["artifacts.files"].drop_indexes()
            await db["artifacts.chunks"].drop_indexes()
        except Exception:
            pass

        await db["artifacts.files"].create_index("uploadDate")
        await db["artifacts.files"].create_index("metadata.session_id")
        await db["artifacts.files"].create_index("metadata.type")

        logger.info("✅ GridFS buckets configured")

        # ====================================
        # 7. AGENT-RELATED COLLECTIONS
        # ====================================
        logger.info("Setting up agent collections...")

        # Agents collection
        with contextlib.suppress(Exception):
            await db.agents.drop_indexes()

        await db.agents.create_index("user_id")
        await db.agents.create_index("name")
        await db.agents.create_index("created_at")

        logger.info("✅ Agent collections configured")

        # ====================================
        # 8. KNOWLEDGE & DATASOURCE COLLECTIONS
        # ====================================
        logger.info("Setting up knowledge collections...")

        with contextlib.suppress(Exception):
            await db.knowledge.drop_indexes()

        await db.knowledge.create_index("session_id")
        await db.knowledge.create_index("scope")
        await db.knowledge.create_index("created_at")

        with contextlib.suppress(Exception):
            await db.datasources.drop_indexes()

        await db.datasources.create_index("session_id")
        await db.datasources.create_index("api_name")

        logger.info("✅ Knowledge collections configured")

        # ====================================
        # SUMMARY
        # ====================================
        collections = await db.list_collection_names()
        logger.info(f"\n{'=' * 60}")
        logger.info("MongoDB Schema Initialization Complete!")
        logger.info(f"{'=' * 60}")
        logger.info(f"Database: {settings.mongodb_database}")
        logger.info(f"Collections created: {len(collections)}")
        logger.info(f"Collections: {', '.join(sorted(collections))}")
        logger.info(f"{'=' * 60}\n")

        # Show index counts
        logger.info("Index counts:")
        for coll_name in sorted(collections):
            if not coll_name.endswith(".chunks"):  # Skip GridFS chunks
                indexes = await db[coll_name].list_indexes().to_list(None)
                logger.info(f"  {coll_name}: {len(indexes)} indexes")

        logger.info("\n✅ MongoDB is ready for development!")

    except Exception as e:
        logger.error(f"❌ Failed to initialize MongoDB: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(init_mongodb())
