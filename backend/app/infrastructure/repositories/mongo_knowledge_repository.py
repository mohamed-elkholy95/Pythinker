"""MongoDB repository for knowledge base and document metadata.

Stores KnowledgeBase and KnowledgeDocument records. Vector data is managed
by RAG-Anything / LightRAG in the per-KB working directory on disk.
"""

import logging
from datetime import UTC, datetime

from pymongo import ASCENDING, IndexModel
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from app.domain.exceptions.base import DuplicateResourceException, IntegrationException
from app.domain.models.knowledge_base import DocumentStatus, KnowledgeBase, KnowledgeDocument
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class MongoKnowledgeRepository:
    """CRUD operations for knowledge bases and their documents."""

    COLLECTION_KB = "knowledge_bases"
    COLLECTION_DOCS = "knowledge_documents"

    def __init__(self, db: Database | None = None) -> None:
        if db is None:
            from app.core.config import get_settings

            settings = get_settings()
            db = get_mongodb().client[settings.mongodb_database]
        self._db = db

    # ── Index setup ───────────────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """Create collection indexes for efficient filtered queries."""
        kb_col = self._db[self.COLLECTION_KB]
        doc_col = self._db[self.COLLECTION_DOCS]

        await kb_col.create_indexes(
            [
                IndexModel([("user_id", ASCENDING)]),
                IndexModel([("user_id", ASCENDING), ("id", ASCENDING)], unique=True),
            ]
        )
        await doc_col.create_indexes(
            [
                IndexModel([("knowledge_base_id", ASCENDING)]),
                IndexModel([("id", ASCENDING)], unique=True),
                IndexModel([("knowledge_base_id", ASCENDING), ("status", ASCENDING)]),
            ]
        )
        logger.info("Knowledge base MongoDB indexes ensured")

    # ── KnowledgeBase CRUD ────────────────────────────────────────────────

    async def create_knowledge_base(self, kb: KnowledgeBase) -> KnowledgeBase:
        col = self._db[self.COLLECTION_KB]
        try:
            await col.insert_one(kb.model_dump())
        except DuplicateKeyError as e:
            logger.warning("Knowledge base already exists: %s — %s", kb.id, e)
            raise DuplicateResourceException(f"Knowledge base already exists: {kb.id}") from e
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error creating knowledge base %s: %s", kb.id, e)
            raise IntegrationException(f"Failed to create knowledge base: {e}", service="mongodb") from e
        return kb

    async def get_knowledge_base(self, kb_id: str, user_id: str) -> KnowledgeBase | None:
        col = self._db[self.COLLECTION_KB]
        doc = await col.find_one({"id": kb_id, "user_id": user_id})
        if doc is None:
            return None
        doc.pop("_id", None)
        return KnowledgeBase(**doc)

    async def list_knowledge_bases(self, user_id: str) -> list[KnowledgeBase]:
        col = self._db[self.COLLECTION_KB]
        cursor = col.find({"user_id": user_id}).sort("created_at", ASCENDING)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(KnowledgeBase(**doc))
        return results

    async def update_knowledge_base(self, kb_id: str, updates: dict) -> None:
        col = self._db[self.COLLECTION_KB]
        updates["updated_at"] = datetime.now(UTC)
        await col.update_one({"id": kb_id}, {"$set": updates})

    async def delete_knowledge_base(self, kb_id: str) -> None:
        kb_col = self._db[self.COLLECTION_KB]
        doc_col = self._db[self.COLLECTION_DOCS]
        await kb_col.delete_one({"id": kb_id})
        await doc_col.delete_many({"knowledge_base_id": kb_id})

    # ── KnowledgeDocument CRUD ────────────────────────────────────────────

    async def create_document(self, doc: KnowledgeDocument) -> KnowledgeDocument:
        col = self._db[self.COLLECTION_DOCS]
        try:
            await col.insert_one(doc.model_dump())
        except DuplicateKeyError as e:
            logger.warning("Knowledge document already exists: %s — %s", doc.id, e)
            raise DuplicateResourceException(f"Knowledge document already exists: {doc.id}") from e
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error creating knowledge document %s: %s", doc.id, e)
            raise IntegrationException(f"Failed to create knowledge document: {e}", service="mongodb") from e
        return doc

    async def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        col = self._db[self.COLLECTION_DOCS]
        raw = await col.find_one({"id": doc_id})
        if raw is None:
            return None
        raw.pop("_id", None)
        return KnowledgeDocument(**raw)

    async def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        col = self._db[self.COLLECTION_DOCS]
        cursor = col.find({"knowledge_base_id": kb_id}).sort("created_at", ASCENDING)
        results = []
        async for raw in cursor:
            raw.pop("_id", None)
            results.append(KnowledgeDocument(**raw))
        return results

    async def update_document_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        chunk_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        col = self._db[self.COLLECTION_DOCS]
        updates: dict = {
            "status": status.value,
            "updated_at": datetime.now(UTC),
        }
        if chunk_count:
            updates["chunk_count"] = chunk_count
        if error_message is not None:
            updates["error_message"] = error_message
        await col.update_one({"id": doc_id}, {"$set": updates})
