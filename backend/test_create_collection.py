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

        print("Creating collection with named vectors...")
        await client.create_collection(
            collection_name="test_hybrid",
            vectors_config=vectors_config,
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,
                memmap_threshold=50000,
                max_segment_size=200000,
            ),
        )
        print("✅ Collection created successfully!")

        # Check the collection info
        info = await client.get_collection("test_hybrid")
        print(f"Collection info: {info}")

    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
