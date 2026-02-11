#!/usr/bin/env python3
"""Reset Qdrant collections with Phase 1 named-vector schema.

For dev mode: Drop all collections and recreate with correct schema.

Usage:
    python scripts/reset_qdrant_collections.py
"""

import asyncio
import logging

from app.infrastructure.storage.qdrant import get_qdrant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reset_collections():
    """Drop and recreate all Qdrant collections."""
    qdrant = get_qdrant()

    logger.info("Connecting to Qdrant...")
    await qdrant.initialize()

    # Get existing collections
    collections = await qdrant.client.get_collections()
    existing_names = {c.name for c in collections.collections}

    logger.info(f"Found {len(existing_names)} existing collections: {existing_names}")

    # Drop all collections
    for name in existing_names:
        logger.info(f"Dropping collection: {name}")
        await qdrant.client.delete_collection(name)

    logger.info("All collections dropped. Reinitializing with Phase 1 schema...")

    # Reinitialize will create collections with new schema
    await qdrant.shutdown()
    await qdrant.initialize()

    # Verify
    collections = await qdrant.client.get_collections()
    new_names = {c.name for c in collections.collections}
    logger.info(f"Created {len(new_names)} collections with named vectors: {new_names}")

    # Print schema info
    for name in new_names:
        info = await qdrant.client.get_collection(name)
        logger.info(f"Collection '{name}': {info.points_count} points")
        logger.info(f"  Vectors: {list(info.config.params.vectors.keys())}")

    logger.info("✅ Qdrant collections reset complete!")


if __name__ == "__main__":
    asyncio.run(reset_collections())
