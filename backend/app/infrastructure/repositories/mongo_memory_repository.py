"""MongoDB implementation of the memory repository.

Provides persistent storage for long-term memories with support for:
- Full-text search
- Vector similarity search (using MongoDB Atlas or local approximation)
- Efficient indexing and querying
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from app.domain.exceptions.base import DuplicateResourceException, IntegrationException, MergeException
from app.domain.models.long_term_memory import (
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    MemoryStats,
    MemoryType,
    MemoryUpdate,
)
from app.domain.repositories.memory_repository import MemoryRepository

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
                [("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created_idx"
            )

            # User + type index
            await self._collection.create_index(
                [("user_id", ASCENDING), ("memory_type", ASCENDING)], name="user_type_idx"
            )

            # User + entities index
            await self._collection.create_index(
                [("user_id", ASCENDING), ("entities", ASCENDING)], name="user_entities_idx"
            )

            # User + content hash for deduplication
            await self._collection.create_index(
                [("user_id", ASCENDING), ("content_hash", ASCENDING)], name="user_hash_idx"
            )

            # Full-text search on content and keywords
            await self._collection.create_index(
                [("content", TEXT), ("keywords", TEXT)], name="text_search_idx", default_language="english"
            )

            # Access count for most accessed queries
            await self._collection.create_index(
                [("user_id", ASCENDING), ("access_count", DESCENDING)], name="user_access_idx"
            )

            # Expiration index for cleanup - TTL index only processes docs with expires_at field
            await self._collection.create_index(
                [("expires_at", ASCENDING)],
                name="expiration_idx",
                expireAfterSeconds=0,  # TTL index
                partialFilterExpression={"expires_at": {"$type": "date"}},
            )

            self._indexes_created = True
            logger.info("Memory repository indexes created successfully")

        except (ConnectionFailure, OperationFailure) as e:
            logger.error("Failed to create memory indexes: %s", e)
            # Continue without indexes - queries will be slower but work

    def _to_document(self, memory: MemoryEntry) -> dict[str, Any]:
        """Convert memory entry to MongoDB document."""
        doc = memory.model_dump()
        doc["_id"] = memory.id
        doc["content_hash"] = memory.content_hash()
        return doc

    def _from_document(self, doc: dict[str, Any]) -> MemoryEntry:
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
        except DuplicateKeyError as e:
            logger.warning("Memory already exists: %s", memory.id)
            raise DuplicateResourceException(f"Memory {memory.id} already exists") from e
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("Failed to create memory: %s", e)
            raise IntegrationException(f"MongoDB write failed: {e}", service="mongodb") from e

    async def create_many(self, memories: list[MemoryEntry]) -> list[MemoryEntry]:
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
        except DuplicateKeyError as e:
            logger.warning("Duplicate key in memory batch insert: %s", e)
            raise DuplicateResourceException("Duplicate memory in batch insert") from e
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("Failed to create memories batch: %s", e)
            raise IntegrationException(f"MongoDB batch write failed: {e}", service="mongodb") from e

    async def get_by_id(self, memory_id: str) -> MemoryEntry | None:
        """Get memory by ID."""
        try:
            doc = await self._collection.find_one({"_id": memory_id})
            if doc:
                return self._from_document(doc)
            return None
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_by_id failed for %s: %s", memory_id, e)
            return None

    async def get_by_ids(self, memory_ids: list[str]) -> list[MemoryEntry]:
        """Get multiple memories by IDs.

        Args:
            memory_ids: List of memory IDs to fetch

        Returns:
            List of memories in same order as input IDs (None entries excluded)
        """
        if not memory_ids:
            return []

        # Create a map for preserving order
        try:
            cursor = self._collection.find({"_id": {"$in": memory_ids}})

            id_to_memory = {}
            async for doc in cursor:
                memory = self._from_document(doc)
                id_to_memory[memory.id] = memory

            # Return in original order, excluding missing
            return [id_to_memory[mid] for mid in memory_ids if mid in id_to_memory]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_by_ids failed for %d IDs: %s", len(memory_ids), e)
            return []

    async def update(self, memory_id: str, update: MemoryUpdate) -> MemoryEntry | None:
        """Update an existing memory."""
        update_data = update.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_by_id(memory_id)

        update_data["updated_at"] = datetime.now(UTC)

        # Recompute content hash if content changed
        if "content" in update_data:
            import hashlib

            update_data["content_hash"] = hashlib.sha256(update_data["content"].encode()).hexdigest()[:16]

        try:
            result = await self._collection.find_one_and_update(
                {"_id": memory_id}, {"$set": update_data}, return_document=True
            )
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB update failed for memory %s: %s", memory_id, e)
            raise IntegrationException(f"MongoDB update failed: {e}", service="mongodb") from e

        if result:
            return self._from_document(result)
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete memory by ID."""
        try:
            result = await self._collection.delete_one({"_id": memory_id})
            return result.deleted_count > 0
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB delete failed for memory %s: %s", memory_id, e)
            return False

    async def delete_by_user(self, user_id: str) -> int:
        """Delete all memories for a user."""
        result = await self._collection.delete_many({"user_id": user_id})
        logger.info(f"Deleted {result.deleted_count} memories for user {user_id}")
        return result.deleted_count

    async def search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """Search memories with various criteria."""
        await self.ensure_indexes()

        # Build MongoDB query
        mongo_query: dict[str, Any] = {"user_id": query.user_id}

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

            cursor = (
                self._collection.find(mongo_query, {"score": {"$meta": "textScore"}})
                .sort([("score", {"$meta": "textScore"})])
                .skip(query.offset)
                .limit(query.limit)
            )

            async for doc in cursor:
                score = doc.pop("score", 0.5)
                # Normalize score (MongoDB text scores can be > 1)
                normalized_score = min(score / 10.0, 1.0)

                if normalized_score >= query.min_relevance:
                    memory = self._from_document(doc)
                    results.append(
                        MemorySearchResult(memory=memory, relevance_score=normalized_score, match_type="text")
                    )

        # Keyword matching
        elif query.keywords:
            mongo_query["keywords"] = {"$in": query.keywords}

            cursor = (
                self._collection.find(mongo_query)
                .sort([("access_count", DESCENDING), ("created_at", DESCENDING)])
                .skip(query.offset)
                .limit(query.limit)
            )

            async for doc in cursor:
                memory = self._from_document(doc)
                # Score based on keyword overlap
                overlap = len(set(memory.keywords) & set(query.keywords))
                score = overlap / max(len(query.keywords), 1)
                results.append(MemorySearchResult(memory=memory, relevance_score=score, match_type="keyword"))

        # Default: filter-based retrieval
        else:
            # Sort by numeric importance rank (not alphabetically) to ensure
            # critical > high > medium > low ordering. String sort gives wrong
            # order: m(edium) > l(ow) > h(igh) > c(ritical) alphabetically.
            pipeline = [
                {"$match": mongo_query},
                {
                    "$addFields": {
                        "_importance_rank": {
                            "$switch": {
                                "branches": [
                                    {"case": {"$eq": ["$importance", "critical"]}, "then": 4},
                                    {"case": {"$eq": ["$importance", "high"]}, "then": 3},
                                    {"case": {"$eq": ["$importance", "medium"]}, "then": 2},
                                    {"case": {"$eq": ["$importance", "low"]}, "then": 1},
                                ],
                                "default": 0,
                            }
                        }
                    }
                },
                {"$sort": {"_importance_rank": -1, "created_at": -1}},
                {"$skip": query.offset},
                {"$limit": query.limit},
                {"$project": {"_importance_rank": 0}},
            ]
            cursor = self._collection.aggregate(pipeline)

            async for doc in cursor:
                memory = self._from_document(doc)
                results.append(
                    MemorySearchResult(
                        memory=memory,
                        relevance_score=0.5,  # Default score for filter matches
                        match_type="filter",
                    )
                )

        return results

    async def vector_search(
        self,
        user_id: str,
        embedding: list[float],
        limit: int = 10,
        min_score: float = 0.0,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemorySearchResult]:
        """Search by vector similarity.

        Uses local cosine similarity computation. For production scale,
        consider MongoDB Atlas vector search or external vector DB.
        """
        await self.ensure_indexes()

        # Build base query
        query: dict[str, Any] = {"user_id": user_id, "is_active": True, "embedding": {"$exists": True, "$ne": None}}

        if memory_types:
            query["memory_type"] = {"$in": [t.value for t in memory_types]}

        # Fetch candidates (limit to reasonable number for local computation)
        cursor = self._collection.find(query).limit(500)

        candidates = [doc async for doc in cursor if doc.get("embedding")]

        if not candidates:
            return []

        # Compute cosine similarity
        import math

        def cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=False))
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
            results.append(MemorySearchResult(memory=memory, relevance_score=score, match_type="semantic"))

        return results

    async def find_duplicates(self, user_id: str, content_hash: str) -> list[MemoryEntry]:
        """Find memories with matching content hash."""
        try:
            cursor = self._collection.find({"user_id": user_id, "content_hash": content_hash})
            return [self._from_document(doc) async for doc in cursor]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB find_duplicates failed for user %s: %s", user_id, e)
            return []

    async def get_by_entities(self, user_id: str, entities: list[str], limit: int = 20) -> list[MemoryEntry]:
        """Get memories mentioning specific entities."""
        try:
            cursor = (
                self._collection.find({"user_id": user_id, "is_active": True, "entities": {"$in": entities}})
                .sort("access_count", DESCENDING)
                .limit(limit)
            )
            return [self._from_document(doc) async for doc in cursor]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_by_entities failed for user %s: %s", user_id, e)
            return []

    async def get_recent(
        self, user_id: str, limit: int = 10, memory_types: list[MemoryType] | None = None
    ) -> list[MemoryEntry]:
        """Get most recently created memories."""
        query: dict[str, Any] = {"user_id": user_id, "is_active": True}

        if memory_types:
            query["memory_type"] = {"$in": [t.value for t in memory_types]}

        try:
            cursor = self._collection.find(query).sort("created_at", DESCENDING).limit(limit)
            return [self._from_document(doc) async for doc in cursor]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_recent failed for user %s: %s", user_id, e)
            return []

    async def get_most_accessed(
        self, user_id: str, limit: int = 10, since: datetime | None = None
    ) -> list[MemoryEntry]:
        """Get most frequently accessed memories."""
        query: dict[str, Any] = {"user_id": user_id, "is_active": True}

        if since:
            query["last_accessed"] = {"$gte": since}

        try:
            cursor = self._collection.find(query).sort("access_count", DESCENDING).limit(limit)
            return [self._from_document(doc) async for doc in cursor]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_most_accessed failed for user %s: %s", user_id, e)
            return []

    async def get_all_content(self, limit: int = 10000) -> list[str]:
        """Get content strings from all active memories for BM25 corpus fitting."""
        try:
            cursor = self._collection.find({"is_active": True}, {"content": 1}).limit(limit)
            return [doc["content"] async for doc in cursor if doc.get("content")]
        except (ConnectionFailure, OperationFailure) as e:
            logger.warning("MongoDB get_all_content failed: %s", e)
            return []

    async def get_stats(self, user_id: str) -> MemoryStats:
        """Get memory statistics for a user."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "active": {"$sum": {"$cond": ["$is_active", 1, 0]}},
                    "oldest": {"$min": "$created_at"},
                    "newest": {"$max": "$created_at"},
                }
            },
        ]

        stats_result = await self._collection.aggregate(pipeline).to_list(1)

        # Get counts by type
        type_pipeline = [
            {"$match": {"user_id": user_id, "is_active": True}},
            {"$group": {"_id": "$memory_type", "count": {"$sum": 1}}},
        ]
        type_counts = await self._collection.aggregate(type_pipeline).to_list(100)
        by_type = {item["_id"]: item["count"] for item in type_counts}

        # Get counts by importance
        imp_pipeline = [
            {"$match": {"user_id": user_id, "is_active": True}},
            {"$group": {"_id": "$importance", "count": {"$sum": 1}}},
        ]
        imp_counts = await self._collection.aggregate(imp_pipeline).to_list(100)
        by_importance = {item["_id"]: item["count"] for item in imp_counts}

        # Get most accessed
        most_accessed_doc = await self._collection.find_one(
            {"user_id": user_id, "is_active": True}, sort=[("access_count", DESCENDING)]
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
            most_accessed=most_accessed_doc.get("_id") if most_accessed_doc else None,
        )

    async def cleanup_expired(self, user_id: str | None = None) -> int:
        """Remove expired memories."""
        query: dict[str, Any] = {"expires_at": {"$lt": datetime.now(UTC)}}

        if user_id:
            query["user_id"] = user_id

        result = await self._collection.delete_many(query)
        logger.info(f"Cleaned up {result.deleted_count} expired memories")
        return result.deleted_count

    async def record_access(self, memory_id: str) -> None:
        """Record memory access."""
        await self._collection.update_one(
            {"_id": memory_id}, {"$set": {"last_accessed": datetime.now(UTC)}, "$inc": {"access_count": 1}}
        )

    async def merge_memories(
        self, memory_ids: list[str], merged_content: str, keep_original: bool = False
    ) -> MemoryEntry:
        """Merge multiple memories into one."""
        # Fetch original memories in a single batch query
        originals = await self.get_by_ids(memory_ids)

        if not originals:
            raise MergeException("No valid memories to merge")

        # Create merged memory
        first = originals[0]
        merged = MemoryEntry(
            id=str(uuid.uuid4()),
            user_id=first.user_id,
            content=merged_content,
            memory_type=first.memory_type,
            importance=max(m.importance for m in originals),
            source=first.source,
            keywords=list({kw for m in originals for kw in m.keywords}),
            entities=list({e for m in originals for e in m.entities}),
            tags=list({t for m in originals for t in m.tags}),
            related_memories=memory_ids,
            metadata={"merged_from": memory_ids},
            access_count=sum(m.access_count for m in originals),
        )

        # Save merged memory
        await self.create(merged)

        # Handle originals
        if keep_original:
            for mid in memory_ids:
                await self.update(mid, MemoryUpdate(is_active=False, metadata={"merged_into": merged.id}))
        else:
            for mid in memory_ids:
                await self.delete(mid)

        return merged
