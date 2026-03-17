#!/usr/bin/env python3
"""Test creating a Qdrant collection with named vectors."""

import asyncio
import traceback

from qdrant_client import AsyncQdrantClient, models


async def main():
    client: AsyncQdrantClient | None = None
    try:
        client = AsyncQdrantClient(url="http://qdrant:6333")

        vectors_config = {
            "dense": models.VectorParams(size=1536, distance=models.Distance.COSINE),
            "sparse": models.SparseVectorParams(),
        }

        await client.create_collection(
            collection_name="test_hybrid",
            vectors_config=vectors_config,
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,
                memmap_threshold=50000,
                max_segment_size=200000,
            ),
        )

        # Check the collection info
        await client.get_collection("test_hybrid")

    except Exception:
        traceback.print_exc()
    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
