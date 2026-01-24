#!/usr/bin/env python3
"""One-time migration of existing MongoDB memories to Qdrant.

This script migrates all existing memory embeddings from MongoDB to Qdrant
for faster vector similarity search.

Usage:
    # From backend directory with activated venv
    python scripts/migrate_to_qdrant.py

    # Or with specific environment
    MONGODB_URI=mongodb://localhost:27017 QDRANT_URL=http://localhost:6333 python scripts/migrate_to_qdrant.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.infrastructure.storage.mongodb import get_mongodb
from app.infrastructure.storage.qdrant import get_qdrant
from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository
from app.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def migrate():
    """Migrate memories from MongoDB to Qdrant."""
    settings = get_settings()

    logger.info("Starting Qdrant migration...")
    logger.info(f"MongoDB URI: {settings.mongodb_uri}")
    logger.info(f"Qdrant URL: {settings.qdrant_url}")
    logger.info(f"Qdrant Collection: {settings.qdrant_collection}")

    # Initialize storage connections
    try:
        await get_mongodb().initialize()
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return

    try:
        await get_qdrant().initialize()
        logger.info("Connected to Qdrant")
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        await get_mongodb().shutdown()
        return

    # Get MongoDB collection
    db = get_mongodb().client[settings.mongodb_database]
    collection = db["long_term_memories"]

    # Get Qdrant repository
    qdrant_repo = QdrantMemoryRepository()

    # Count documents to migrate
    total_docs = await collection.count_documents({
        "embedding": {"$exists": True, "$ne": None}
    })
    logger.info(f"Found {total_docs} memories with embeddings to migrate")

    if total_docs == 0:
        logger.info("No memories to migrate. Exiting.")
        await get_mongodb().shutdown()
        await get_qdrant().shutdown()
        return

    # Migrate in batches
    batch_size = 100
    migrated = 0
    failed = 0
    skipped = 0

    cursor = collection.find({
        "embedding": {"$exists": True, "$ne": None}
    })

    batch = []

    async for doc in cursor:
        try:
            # Validate required fields
            memory_id = str(doc.get("_id", doc.get("id")))
            user_id = doc.get("user_id")
            embedding = doc.get("embedding")

            if not memory_id or not user_id or not embedding:
                skipped += 1
                continue

            if not isinstance(embedding, list) or len(embedding) == 0:
                skipped += 1
                continue

            batch.append({
                "memory_id": memory_id,
                "user_id": user_id,
                "embedding": embedding,
                "memory_type": doc.get("memory_type", "fact"),
                "importance": doc.get("importance", "medium"),
                "tags": doc.get("tags", []),
            })

            # Process batch when full
            if len(batch) >= batch_size:
                try:
                    await qdrant_repo.upsert_memories_batch(batch)
                    migrated += len(batch)
                    logger.info(f"Migrated {migrated}/{total_docs} memories...")
                except Exception as e:
                    logger.error(f"Failed to migrate batch: {e}")
                    failed += len(batch)
                batch = []

        except Exception as e:
            logger.warning(f"Error processing document: {e}")
            failed += 1

    # Process remaining batch
    if batch:
        try:
            await qdrant_repo.upsert_memories_batch(batch)
            migrated += len(batch)
        except Exception as e:
            logger.error(f"Failed to migrate final batch: {e}")
            failed += len(batch)

    # Report results
    logger.info("=" * 50)
    logger.info("Migration Complete!")
    logger.info(f"  Total documents: {total_docs}")
    logger.info(f"  Migrated: {migrated}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"  Failed: {failed}")
    logger.info("=" * 50)

    # Verify Qdrant count
    try:
        qdrant_count = await qdrant_repo.get_memory_count()
        logger.info(f"Qdrant collection now has {qdrant_count} vectors")
    except Exception as e:
        logger.warning(f"Could not verify Qdrant count: {e}")

    # Cleanup
    await get_mongodb().shutdown()
    await get_qdrant().shutdown()
    logger.info("Disconnected from databases")


async def verify_migration():
    """Verify migration by checking a sample of memories."""
    settings = get_settings()

    await get_mongodb().initialize()
    await get_qdrant().initialize()

    db = get_mongodb().client[settings.mongodb_database]
    collection = db["long_term_memories"]
    qdrant_repo = QdrantMemoryRepository()

    # Get a sample of memories
    sample = await collection.find({
        "embedding": {"$exists": True, "$ne": None}
    }).limit(10).to_list(10)

    verified = 0
    for doc in sample:
        memory_id = str(doc.get("_id", doc.get("id")))
        exists = await qdrant_repo.memory_exists(memory_id)
        if exists:
            verified += 1
            logger.info(f"  Verified memory {memory_id[:8]}...")
        else:
            logger.warning(f"  Missing memory {memory_id[:8]}...")

    logger.info(f"Verified {verified}/{len(sample)} sampled memories")

    await get_mongodb().shutdown()
    await get_qdrant().shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate memories to Qdrant")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing migration, don't migrate"
    )
    args = parser.parse_args()

    if args.verify_only:
        asyncio.run(verify_migration())
    else:
        asyncio.run(migrate())
