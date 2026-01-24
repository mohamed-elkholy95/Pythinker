"""MongoDB implementation of the memory repository.

Provides persistent storage for long-term memories with support for:
- Full-text search
- Vector similarity search (using MongoDB Atlas or local approximation)
- Efficient indexing and querying
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING, TEXT

from app.domain.repositories.memory_repository import MemoryRepository
from app.domain.models.long_term_memory import (
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
    MemoryUpdate,
    MemoryType,
    MemoryImportance,
)


logger = logging.getLogger(__name__)


class MongoMemoryRepository(MemoryRepository):
    """MongoDB implementation for long-term memory storage.

    Uses MongoDB's text search and optional vector search capabilities.
    For vector search, requires either:
    - MongoDB Atlas with vector search index
    - Local cosine similarity computation for smaller datasets
    """

    COLLECTION_NAME = "long_term_memories"

    def __init__(self, database: AsyncIOMotorDatabase):
        """Initialize repository with database connection.

        Args:
            database: Motor async MongoDB database instance
        """
        self._db = database
        self._collection: AsyncIOMotorCollection = database[self.COLLECTION_NAME]
        self._indexes_created = False

    async def ensure_indexes(self) -> None:
        """Create required indexes for efficient querying."""
        if self._indexes_created:
            return

        try:
            # User + time index for recent queries
            await self._collection.create_index(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="user_created_idx"
            )

            # User + type index
            await self._collection.create_index(
                [("user_id", ASCENDING), ("memory_type", ASCENDING)],
                name="user_type_idx"
            )

            # User + entities index
            await self._collection.create_index(
                [("user_id", ASCENDING), ("entities", ASCENDING)],
                name="user_entities_idx"
            )

            # User + content hash for deduplication
            await self._collection.create_index(
                [("user_id", ASCENDING), ("content_hash", ASCENDING)],
                name="user_hash_idx"
            )

            # Full-text search on content and keywords
            await self._collection.create_index(
                [("content", TEXT), ("keywords", TEXT)],
                name="text_search_idx",
                default_language="english"
            )

            # Access count for most accessed queries
            await self._collection.create_index(
                [("user_id", ASCENDING), ("access_count", DESCENDING)],
                name="user_access_idx"
            )

            # Expiration index for cleanup - TTL index only processes docs with expires_at field
            await self._collection.create_index(
                [("expires_at", ASCENDING)],
                name="expiration_idx",
                expireAfterSeconds=0,  # TTL index
                partialFilterExpression={"expires_at": {"$type": "date"}}
            )

            self._indexes_created = True
            logger.info("Memory repository indexes created successfully")

        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
            # Continue without indexes - queries will be slower but work

    def _to_document(self, memory: MemoryEntry) -> Dict[str, Any]:
        """Convert memory entry to MongoDB document."""
        doc = memory.model_dump()
        doc["_id"] = memory.id
        doc["content_hash"] = memory.content_hash()
        return doc

    def _from_document(self, doc: Dict[str, Any]) -> MemoryEntry:
        """Convert MongoDB document to memory entry."""
        if "_id" in doc:
            doc["id"] = str(doc.pop("_id"))
        doc.pop("content_hash", None)  # Remove computed field
        return MemoryEntry.model_validate(doc)

    async def create(self, memory: MemoryEntry) -> MemoryEntry:
        """Create a new memory entry."""
        await self.ensure_indexes()

        # Generate ID if not provided
        if not memory.id:
            memory.id = str(uuid.uuid4())

        doc = self._to_document(memory)

        try:
            await self._collection.insert_one(doc)
            logger.debug(f"Created memory {memory.id} for user {memory.user_id}")
            return memory
        except Exception as e:
            logger.error(f"Failed to create memory: {e}")
            raise

    async def create_many(self, memories: List[MemoryEntry]) -> List[MemoryEntry]:
        """Create multiple memories in batch."""
        await self.ensure_indexes()

        for memory in memories:
            if not memory.id:
                memory.id = str(uuid.uuid4())

        docs = [self._to_document(m) for m in memories]

        try:
            await self._collection.insert_many(docs)
            logger.debug(f"Created {len(memories)} memories in batch")
            return memories
        except Exception as e:
            logger.error(f"Failed to create memories batch: {e}")
            raise

    async def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get memory by ID."""
        doc = await self._collection.find_one({"_id": memory_id})
        if doc:
            return self._from_document(doc)
        return None

    async def get_by_ids(self, memory_ids: List[str]) -> List[MemoryEntry]:
        """Get multiple memories by IDs.

        Args:
            memory_ids: List of memory IDs to fetch

        Returns:
            List of memories in same order as input IDs (None entries excluded)
        """
        if not memory_ids:
            return []

        # Create a map for preserving order
        cursor = self._collection.find({"_id": {"$in": memory_ids}})

        id_to_memory = {}
        async for doc in cursor:
            memory = self._from_document(doc)
            id_to_memory[memory.id] = memory

        # Return in original order, excluding missing
        return [id_to_memory[mid] for mid in memory_ids if mid in id_to_memory]

    async def update(self, memory_id: str, update: MemoryUpdate) -> Optional[MemoryEntry]:
        """Update an existing memory."""
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_by_id(memory_id)

        update_data["updated_at"] = datetime.utcnow()

        # Recompute content hash if content changed
        if "content" in update_data:
            import hashlib
            update_data["content_hash"] = hashlib.sha256(
                update_data["content"].encode()
            ).hexdigest()[:16]

        result = await self._collection.find_one_and_update(
            {"_id": memory_id},
            {"$set": update_data},
            return_document=True
        )

        if result:
            return self._from_document(result)
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete memory by ID."""
        result = await self._collection.delete_one({"_id": memory_id})
        return result.deleted_count > 0

    async def delete_by_user(self, user_id: str) -> int:
        """Delete all memories for a user."""
        result = await self._collection.delete_many({"user_id": user_id})
        logger.info(f"Deleted {result.deleted_count} memories for user {user_id}")
        return result.deleted_count

    async def search(self, query: MemoryQuery) -> List[MemorySearchResult]:
        """Search memories with various criteria."""
        await self.ensure_indexes()

        # Build MongoDB query
        mongo_query: Dict[str, Any] = {"user_id": query.user_id}

        if not query.include_expired:
            mongo_query["is_active"] = True

        # Type filter
        if query.memory_types:
            mongo_query["memory_type"] = {"$in": [t.value for t in query.memory_types]}

        # Importance filter
        if query.min_importance:
            importance_order = ["low", "medium", "high", "critical"]
            min_idx = importance_order.index(query.min_importance.value)
            valid_importances = importance_order[min_idx:]
            mongo_query["importance"] = {"$in": valid_importances}

        # Tag filter
        if query.tag_filter:
            mongo_query["tags"] = {"$all": query.tag_filter}

        # Entity filter
        if query.entity_filter:
            mongo_query["entities"] = {"$in": query.entity_filter}

        # Time filters
        if query.created_after:
            mongo_query.setdefault("created_at", {})["$gte"] = query.created_after
        if query.created_before:
            mongo_query.setdefault("created_at", {})["$lte"] = query.created_before
        if query.accessed_after:
            mongo_query["last_accessed"] = {"$gte": query.accessed_after}

        results = []

        # Text search if query text provided
        if query.query_text:
            mongo_query["$text"] = {"$search": query.query_text}

            cursor = self._collection.find(
                mongo_query,
                {"score": {"$meta": "textScore"}}
            ).sort(
                [("score", {"$meta": "textScore"})]
            ).skip(query.offset).limit(query.limit)

            async for doc in cursor:
                score = doc.pop("score", 0.5)
                # Normalize score (MongoDB text scores can be > 1)
                normalized_score = min(score / 10.0, 1.0)

                if normalized_score >= query.min_relevance:
                    memory = self._from_document(doc)
                    results.append(MemorySearchResult(
                        memory=memory,
                        relevance_score=normalized_score,
                        match_type="text"
                    ))

        # Keyword matching
        elif query.keywords:
            mongo_query["keywords"] = {"$in": query.keywords}

            cursor = self._collection.find(mongo_query).sort(
                [("access_count", DESCENDING), ("created_at", DESCENDING)]
            ).skip(query.offset).limit(query.limit)

            async for doc in cursor:
                memory = self._from_document(doc)
                # Score based on keyword overlap
                overlap = len(set(memory.keywords) & set(query.keywords))
                score = overlap / max(len(query.keywords), 1)
                results.append(MemorySearchResult(
                    memory=memory,
                    relevance_score=score,
                    match_type="keyword"
                ))

        # Default: filter-based retrieval
        else:
            cursor = self._collection.find(mongo_query).sort(
                [("importance", DESCENDING), ("created_at", DESCENDING)]
            ).skip(query.offset).limit(query.limit)

            async for doc in cursor:
                memory = self._from_document(doc)
                results.append(MemorySearchResult(
                    memory=memory,
                    relevance_score=0.5,  # Default score for filter matches
                    match_type="filter"
                ))

        return results

    async def vector_search(
        self,
        user_id: str,
        embedding: List[float],
        limit: int = 10,
        min_score: float = 0.0,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemorySearchResult]:
        """Search by vector similarity.

        Uses local cosine similarity computation. For production scale,
        consider MongoDB Atlas vector search or external vector DB.
        """
        await self.ensure_indexes()

        # Build base query
        query: Dict[str, Any] = {
            "user_id": user_id,
            "is_active": True,
            "embedding": {"$exists": True, "$ne": None}
        }

        if memory_types:
            query["memory_type"] = {"$in": [t.value for t in memory_types]}

        # Fetch candidates (limit to reasonable number for local computation)
        cursor = self._collection.find(query).limit(500)

        candidates = []
        async for doc in cursor:
            if doc.get("embedding"):
                candidates.append(doc)

        if not candidates:
            return []

        # Compute cosine similarity
        import math

        def cosine_similarity(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        # Score and rank
        scored = []
        for doc in candidates:
            score = cosine_similarity(embedding, doc["embedding"])
            if score >= min_score:
                scored.append((score, doc))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Convert to results
        results = []
        for score, doc in scored[:limit]:
            memory = self._from_document(doc)
            results.append(MemorySearchResult(
                memory=memory,
                relevance_score=score,
                match_type="semantic"
            ))

        return results

    async def find_duplicates(
        self,
        user_id: str,
        content_hash: str
    ) -> List[MemoryEntry]:
        """Find memories with matching content hash."""
        cursor = self._collection.find({
            "user_id": user_id,
            "content_hash": content_hash
        })

        results = []
        async for doc in cursor:
            results.append(self._from_document(doc))
        return results

    async def get_by_entities(
        self,
        user_id: str,
        entities: List[str],
        limit: int = 20
    ) -> List[MemoryEntry]:
        """Get memories mentioning specific entities."""
        cursor = self._collection.find({
            "user_id": user_id,
            "is_active": True,
            "entities": {"$in": entities}
        }).sort("access_count", DESCENDING).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._from_document(doc))
        return results

    async def get_recent(
        self,
        user_id: str,
        limit: int = 10,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryEntry]:
        """Get most recently created memories."""
        query: Dict[str, Any] = {
            "user_id": user_id,
            "is_active": True
        }

        if memory_types:
            query["memory_type"] = {"$in": [t.value for t in memory_types]}

        cursor = self._collection.find(query).sort(
            "created_at", DESCENDING
        ).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._from_document(doc))
        return results

    async def get_most_accessed(
        self,
        user_id: str,
        limit: int = 10,
        since: Optional[datetime] = None
    ) -> List[MemoryEntry]:
        """Get most frequently accessed memories."""
        query: Dict[str, Any] = {
            "user_id": user_id,
            "is_active": True
        }

        if since:
            query["last_accessed"] = {"$gte": since}

        cursor = self._collection.find(query).sort(
            "access_count", DESCENDING
        ).limit(limit)

        results = []
        async for doc in cursor:
            results.append(self._from_document(doc))
        return results

    async def get_stats(self, user_id: str) -> MemoryStats:
        """Get memory statistics for a user."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "active": {"$sum": {"$cond": ["$is_active", 1, 0]}},
                "oldest": {"$min": "$created_at"},
                "newest": {"$max": "$created_at"},
            }}
        ]

        stats_result = await self._collection.aggregate(pipeline).to_list(1)

        # Get counts by type
        type_pipeline = [
            {"$match": {"user_id": user_id, "is_active": True}},
            {"$group": {"_id": "$memory_type", "count": {"$sum": 1}}}
        ]
        type_counts = await self._collection.aggregate(type_pipeline).to_list(100)
        by_type = {item["_id"]: item["count"] for item in type_counts}

        # Get counts by importance
        imp_pipeline = [
            {"$match": {"user_id": user_id, "is_active": True}},
            {"$group": {"_id": "$importance", "count": {"$sum": 1}}}
        ]
        imp_counts = await self._collection.aggregate(imp_pipeline).to_list(100)
        by_importance = {item["_id"]: item["count"] for item in imp_counts}

        # Get most accessed
        most_accessed_doc = await self._collection.find_one(
            {"user_id": user_id, "is_active": True},
            sort=[("access_count", DESCENDING)]
        )

        base_stats = stats_result[0] if stats_result else {}

        return MemoryStats(
            user_id=user_id,
            total_memories=base_stats.get("total", 0),
            active_memories=base_stats.get("active", 0),
            by_type=by_type,
            by_importance=by_importance,
            oldest_memory=base_stats.get("oldest"),
            newest_memory=base_stats.get("newest"),
            most_accessed=most_accessed_doc.get("_id") if most_accessed_doc else None
        )

    async def cleanup_expired(self, user_id: Optional[str] = None) -> int:
        """Remove expired memories."""
        query: Dict[str, Any] = {
            "expires_at": {"$lt": datetime.utcnow()}
        }

        if user_id:
            query["user_id"] = user_id

        result = await self._collection.delete_many(query)
        logger.info(f"Cleaned up {result.deleted_count} expired memories")
        return result.deleted_count

    async def record_access(self, memory_id: str) -> None:
        """Record memory access."""
        await self._collection.update_one(
            {"_id": memory_id},
            {
                "$set": {"last_accessed": datetime.utcnow()},
                "$inc": {"access_count": 1}
            }
        )

    async def merge_memories(
        self,
        memory_ids: List[str],
        merged_content: str,
        keep_original: bool = False
    ) -> MemoryEntry:
        """Merge multiple memories into one."""
        # Fetch original memories
        originals = []
        for mid in memory_ids:
            mem = await self.get_by_id(mid)
            if mem:
                originals.append(mem)

        if not originals:
            raise ValueError("No valid memories to merge")

        # Create merged memory
        first = originals[0]
        merged = MemoryEntry(
            id=str(uuid.uuid4()),
            user_id=first.user_id,
            content=merged_content,
            memory_type=first.memory_type,
            importance=max(m.importance for m in originals),
            source=first.source,
            keywords=list(set(kw for m in originals for kw in m.keywords)),
            entities=list(set(e for m in originals for e in m.entities)),
            tags=list(set(t for m in originals for t in m.tags)),
            related_memories=memory_ids,
            metadata={"merged_from": memory_ids},
            access_count=sum(m.access_count for m in originals)
        )

        # Save merged memory
        await self.create(merged)

        # Handle originals
        if keep_original:
            for mid in memory_ids:
                await self.update(mid, MemoryUpdate(
                    is_active=False,
                    metadata={"merged_into": merged.id}
                ))
        else:
            for mid in memory_ids:
                await self.delete(mid)

        return merged
