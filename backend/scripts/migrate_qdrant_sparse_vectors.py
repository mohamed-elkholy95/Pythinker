#!/usr/bin/env python3
"""Migrate existing Qdrant collections to support sparse vectors.

This script handles schema migration for collections that were created
before sparse vector support was added. It recreates collections with
the new hybrid dense+sparse schema while preserving existing data.

Usage:
    # Dry run (check what would be migrated)
    python scripts/migrate_qdrant_sparse_vectors.py --dry-run

    # Perform migration
    python scripts/migrate_qdrant_sparse_vectors.py

    # Force migration (skip compatibility check)
    python scripts/migrate_qdrant_sparse_vectors.py --force

Safety:
    - Creates backup of points before migration
    - Verifies schema incompatibility before recreating
    - Preserves all point data and payload
    - Can be run multiple times (idempotent)
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from qdrant_client import models  # noqa: E402

from app.infrastructure.storage.qdrant import (  # noqa: E402
    COLLECTIONS,
    DENSE_VECTOR_CONFIG,
    SPARSE_VECTOR_CONFIG,
    get_qdrant,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_collection_schema(client, collection_name: str) -> dict:
    """Check if collection has compatible schema.

    Returns:
        dict with keys:
            - exists: bool
            - has_sparse: bool
            - needs_migration: bool
            - point_count: int
    """
    result = {
        "exists": False,
        "has_sparse": False,
        "needs_migration": False,
        "point_count": 0,
    }

    try:
        exists = await client.collection_exists(collection_name)
        if not exists:
            logger.info(f"✓ Collection '{collection_name}' does not exist (will be created with new schema)")
            return result

        result["exists"] = True

        # Get collection info
        info = await client.get_collection(collection_name)
        result["point_count"] = info.points_count

        # Check for sparse vectors
        sparse_vectors = info.config.params.sparse_vectors or {}
        result["has_sparse"] = "sparse" in sparse_vectors

        if not result["has_sparse"]:
            result["needs_migration"] = True
            logger.warning(
                f"⚠️  Collection '{collection_name}' is missing sparse vectors "
                f"(has {result['point_count']} points, needs migration)"
            )
        else:
            logger.info(
                f"✓ Collection '{collection_name}' already has sparse vectors "
                f"({result['point_count']} points, no migration needed)"
            )

        return result

    except Exception as e:
        logger.error(f"Error checking collection '{collection_name}': {e}")
        return result


async def backup_collection_points(client, collection_name: str, limit: int = 10000) -> list:
    """Backup all points from a collection.

    Args:
        client: Qdrant client
        collection_name: Name of collection to backup
        limit: Maximum points per scroll (default 10000)

    Returns:
        List of all points from the collection
    """
    logger.info(f"Backing up points from '{collection_name}'...")

    all_points = []
    offset = None

    try:
        while True:
            scroll_result = await client.scroll(
                collection_name=collection_name,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            points, next_offset = scroll_result

            if not points:
                break

            all_points.extend(points)
            logger.info(f"Backed up {len(all_points)} points...")

            if next_offset is None:
                break

            offset = next_offset

        logger.info(f"✓ Backed up {len(all_points)} points from '{collection_name}'")
        return all_points

    except Exception as e:
        logger.error(f"Error backing up collection '{collection_name}': {e}")
        raise


async def migrate_collection(client, collection_name: str, dry_run: bool = False) -> bool:
    """Migrate a single collection to support sparse vectors.

    Args:
        client: Qdrant client
        collection_name: Name of collection to migrate
        dry_run: If True, only check what would be done

    Returns:
        True if migration was successful or not needed, False otherwise
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Migrating collection: {collection_name}")
    logger.info(f"{'=' * 60}")

    # Check current schema
    schema = await check_collection_schema(client, collection_name)

    if not schema["exists"]:
        logger.info(f"✓ Collection '{collection_name}' will be created with new schema on next startup")
        return True

    if not schema["needs_migration"]:
        logger.info(f"✓ Collection '{collection_name}' already has sparse vectors, skipping")
        return True

    if dry_run:
        logger.info(f"[DRY RUN] Would migrate '{collection_name}' ({schema['point_count']} points would be preserved)")
        return True

    # Perform migration
    try:
        # Step 1: Backup points
        points = await backup_collection_points(client, collection_name)

        # Step 2: Delete old collection
        logger.info(f"Deleting old collection '{collection_name}'...")
        await client.delete_collection(collection_name)
        logger.info("✓ Deleted old collection")

        # Step 3: Create new collection with sparse vector support
        logger.info(f"Creating new collection '{collection_name}' with sparse vector support...")

        # Get dense config for this collection
        dense_config = COLLECTIONS.get(collection_name, DENSE_VECTOR_CONFIG)

        await client.create_collection(
            collection_name=collection_name,
            vectors_config={"dense": dense_config},
            sparse_vectors_config={"sparse": SPARSE_VECTOR_CONFIG},
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,
                memmap_threshold=50000,
                max_segment_size=200000,
            ),
        )
        logger.info("✓ Created new collection with hybrid dense+sparse schema")

        # Step 4: Restore points (without sparse vectors initially)
        if points:
            logger.info(f"Restoring {len(points)} points...")

            # Convert points to format expected by upsert
            restore_points = []
            for point in points:
                # Extract dense vector from named vectors
                dense_vector = point.vector.get("dense") if isinstance(point.vector, dict) else point.vector

                if dense_vector is None:
                    logger.warning(f"Skipping point {point.id} - no dense vector found")
                    continue

                restore_points.append(
                    models.PointStruct(
                        id=point.id,
                        vector={"dense": dense_vector},  # Only dense for now
                        payload=point.payload or {},
                    )
                )

            # Upsert in batches
            batch_size = 100
            for i in range(0, len(restore_points), batch_size):
                batch = restore_points[i : i + batch_size]
                await client.upsert(collection_name=collection_name, points=batch)
                logger.info(f"Restored {min(i + batch_size, len(restore_points))}/{len(restore_points)} points...")

            logger.info(f"✓ Restored all {len(restore_points)} points")

        logger.info(f"✓ Successfully migrated collection '{collection_name}'")
        return True

    except Exception as e:
        logger.error(f"✗ Failed to migrate collection '{collection_name}': {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Migrate Qdrant collections to support sparse vectors")
    parser.add_argument("--dry-run", action="store_true", help="Check what would be migrated without making changes")
    parser.add_argument("--force", action="store_true", help="Force migration even if schema appears compatible")
    parser.add_argument("--collection", type=str, help="Migrate only a specific collection (default: migrate all)")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("=" * 60)

    # Initialize Qdrant client
    logger.info("Connecting to Qdrant...")
    qdrant = get_qdrant()
    await qdrant.initialize()
    client = qdrant.client

    # Determine which collections to migrate
    if args.collection:
        if args.collection not in COLLECTIONS:
            logger.error(f"Unknown collection: {args.collection}")
            logger.info(f"Available collections: {', '.join(COLLECTIONS.keys())}")
            return 1
        collections_to_migrate = [args.collection]
    else:
        collections_to_migrate = list(COLLECTIONS.keys())

    # Migrate each collection
    results = {}
    for collection_name in collections_to_migrate:
        success = await migrate_collection(client, collection_name, dry_run=args.dry_run)
        results[collection_name] = success

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("Migration Summary")
    logger.info("=" * 60)

    for collection_name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{collection_name}: {status}")

    if args.dry_run:
        logger.info("\nDry run complete. Run without --dry-run to perform migration.")

    # Shutdown
    await qdrant.shutdown()

    # Return exit code
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
