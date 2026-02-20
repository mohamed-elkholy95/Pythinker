"""Domain service orchestrating knowledge base lifecycle and queries.

Delegates storage to MongoKnowledgeRepository and vector indexing to
RAGAnythingAdapter. Background indexing tasks are tracked in memory so
callers can poll document status without blocking.
"""

import asyncio
import contextlib
import logging
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.exceptions.base import KnowledgeBaseException, ResourceNotFoundException
from app.domain.models.knowledge_base import (
    DocumentStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
    KnowledgeQueryResult,
)

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.infrastructure.external.raganything.adapter import RAGAnythingAdapter
    from app.infrastructure.repositories.mongo_knowledge_repository import MongoKnowledgeRepository

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """High-level knowledge base operations with async indexing."""

    def __init__(
        self,
        repository: "MongoKnowledgeRepository",
        adapter: "RAGAnythingAdapter",
        settings: "Settings",
    ) -> None:
        self._repo = repository
        self._adapter = adapter
        self._settings = settings
        self._indexing_tasks: dict[str, asyncio.Task] = {}  # doc_id → background task

    # ── Knowledge Base CRUD ───────────────────────────────────────────────

    async def create_knowledge_base(self, user_id: str, name: str, description: str = "") -> KnowledgeBase:
        kb_id = str(uuid.uuid4())
        storage_path = os.path.join(self._settings.knowledge_base_storage_dir, user_id, kb_id)
        kb = KnowledgeBase(
            id=kb_id,
            user_id=user_id,
            name=name,
            description=description,
            status=KnowledgeBaseStatus.READY,
            storage_path=storage_path,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        await self._repo.create_knowledge_base(kb)
        logger.info("Created knowledge base kb=%s user=%s", kb_id, user_id)
        return kb

    async def list_knowledge_bases(self, user_id: str) -> list[KnowledgeBase]:
        return await self._repo.list_knowledge_bases(user_id)

    async def get_knowledge_base(self, kb_id: str, user_id: str) -> KnowledgeBase:
        kb = await self._repo.get_knowledge_base(kb_id, user_id)
        if kb is None:
            raise ResourceNotFoundException(
                f"Knowledge base {kb_id!r} not found",
                resource_type="knowledge_base",
                resource_id=kb_id,
            )
        return kb

    async def delete_knowledge_base(self, kb_id: str, user_id: str) -> None:
        kb = await self.get_knowledge_base(kb_id, user_id)
        await self._adapter.close_instance(kb_id)
        await self._repo.delete_knowledge_base(kb_id)
        # Best-effort cleanup of on-disk data
        try:
            import shutil

            if kb.storage_path and os.path.isdir(kb.storage_path):
                shutil.rmtree(kb.storage_path, ignore_errors=True)
        except Exception as exc:
            logger.warning("Could not remove kb storage dir: %s", exc)

    # ── Document Indexing ─────────────────────────────────────────────────

    async def index_document_async(
        self,
        kb_id: str,
        user_id: str,
        file_path: str,
        filename: str,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> KnowledgeDocument:
        """Create a document record and spawn background indexing.

        Returns immediately with status=PENDING. The background task
        transitions the document through PROCESSING → INDEXED (or FAILED).
        """
        kb = await self.get_knowledge_base(kb_id, user_id)

        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        max_bytes = self._settings.knowledge_base_max_file_size_mb * 1024 * 1024
        if file_size > max_bytes:
            raise KnowledgeBaseException(
                f"File size {file_size} exceeds limit of {self._settings.knowledge_base_max_file_size_mb} MB"
            )

        suffix = Path(filename).suffix.lstrip(".").lower() or "bin"
        doc = KnowledgeDocument(
            id=str(uuid.uuid4()),
            knowledge_base_id=kb_id,
            filename=filename,
            file_type=suffix,
            file_size_bytes=file_size,
            status=DocumentStatus.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await self._repo.create_document(doc)

        # Ensure RAGAnything instance is ready before spawning task
        await self._adapter.get_or_create_instance(kb)

        task = asyncio.create_task(
            self._run_indexing(kb, doc, file_path, progress_callback),
            name=f"kb-index-{doc.id}",
        )
        self._indexing_tasks[doc.id] = task
        task.add_done_callback(lambda t: self._indexing_tasks.pop(doc.id, None))

        logger.info("Spawned indexing task for doc=%s kb=%s file=%s", doc.id, kb_id, filename)
        return doc

    async def _run_indexing(
        self,
        kb: KnowledgeBase,
        doc: KnowledgeDocument,
        file_path: str,
        progress_callback: Callable[[int, str], None] | None,
    ) -> None:
        """Background task that indexes a document and updates its status."""
        try:
            await self._repo.update_document_status(doc.id, DocumentStatus.PROCESSING)
            if progress_callback:
                with contextlib.suppress(Exception):
                    progress_callback(10, "Parsing document")

            await self._adapter.process_document(kb.id, file_path, doc.id)

            if progress_callback:
                with contextlib.suppress(Exception):
                    progress_callback(90, "Finalizing index")

            await self._repo.update_document_status(doc.id, DocumentStatus.INDEXED)
            await self._repo.update_knowledge_base(
                kb.id,
                {"document_count": await self._count_indexed_docs(kb.id)},
            )
            logger.info("Indexed doc=%s in kb=%s", doc.id, kb.id)
        except Exception as exc:
            logger.error("Indexing failed for doc=%s: %s", doc.id, exc)
            await self._repo.update_document_status(doc.id, DocumentStatus.FAILED, error_message=str(exc))
        finally:
            # Upload handler passes temp files and indexing owns their lifecycle.
            if os.path.exists(file_path):
                with contextlib.suppress(OSError):
                    os.unlink(file_path)

    async def _count_indexed_docs(self, kb_id: str) -> int:
        docs = await self._repo.list_documents(kb_id)
        return sum(1 for d in docs if d.status == DocumentStatus.INDEXED)

    async def get_indexing_status(self, doc_id: str) -> DocumentStatus:
        doc = await self._repo.get_document(doc_id)
        if doc is None:
            raise ResourceNotFoundException(
                f"Document {doc_id!r} not found",
                resource_type="knowledge_document",
                resource_id=doc_id,
            )
        return doc.status

    # ── Querying ──────────────────────────────────────────────────────────

    async def query(
        self,
        kb_id: str,
        user_id: str,
        query: str,
        mode: str = "hybrid",
    ) -> KnowledgeQueryResult:
        import time

        kb = await self.get_knowledge_base(kb_id, user_id)
        await self._adapter.get_or_create_instance(kb)

        start = time.monotonic()
        answer, sources = await self._adapter.query(kb_id, query, mode=mode)
        elapsed_ms = (time.monotonic() - start) * 1000

        return KnowledgeQueryResult(
            answer=answer,
            sources=sources,
            query_time_ms=elapsed_ms,
            mode=mode,
        )

    async def query_multimodal(
        self,
        kb_id: str,
        user_id: str,
        query: str,
        content: list,
    ) -> KnowledgeQueryResult:
        import time

        kb = await self.get_knowledge_base(kb_id, user_id)
        await self._adapter.get_or_create_instance(kb)

        start = time.monotonic()
        answer, sources = await self._adapter.query_multimodal(kb_id, query, content)
        elapsed_ms = (time.monotonic() - start) * 1000

        return KnowledgeQueryResult(
            answer=answer,
            sources=sources,
            query_time_ms=elapsed_ms,
            mode="multimodal",
        )
