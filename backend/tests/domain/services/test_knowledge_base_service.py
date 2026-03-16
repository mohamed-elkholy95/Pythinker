"""Unit tests for knowledge base service indexing and query behavior."""

import asyncio
import os
import tempfile
from types import SimpleNamespace
from typing import Any

import pytest

from app.domain.models.knowledge_base import DocumentStatus, KnowledgeBase, KnowledgeBaseStatus, KnowledgeDocument
from app.domain.services.knowledge_base_service import KnowledgeBaseService


class _FakeKnowledgeRepository:
    def __init__(self, kb: KnowledgeBase) -> None:
        self._kb = kb
        self.documents: dict[str, KnowledgeDocument] = {}
        self.kb_updates: list[tuple[str, dict[str, Any]]] = []

    async def get_knowledge_base(self, kb_id: str, user_id: str) -> KnowledgeBase | None:
        if self._kb.id == kb_id and self._kb.user_id == user_id:
            return self._kb
        return None

    async def create_document(self, doc: KnowledgeDocument) -> KnowledgeDocument:
        self.documents[doc.id] = doc
        return doc

    async def update_document_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        chunk_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        current = self.documents[doc_id]
        updates: dict[str, Any] = {"status": status}
        if chunk_count:
            updates["chunk_count"] = chunk_count
        if error_message is not None:
            updates["error_message"] = error_message
        self.documents[doc_id] = current.model_copy(update=updates)

    async def list_documents(self, kb_id: str) -> list[KnowledgeDocument]:
        return [doc for doc in self.documents.values() if doc.knowledge_base_id == kb_id]

    async def update_knowledge_base(self, kb_id: str, updates: dict[str, Any]) -> None:
        self.kb_updates.append((kb_id, updates))


class _FakeAdapter:
    def __init__(
        self,
        *,
        process_error: Exception | None = None,
        query_result: tuple[str, list[str]] = ("", []),
        multimodal_query_result: tuple[str, list[str]] = ("", []),
    ) -> None:
        self.process_error = process_error
        self.query_result = query_result
        self.multimodal_query_result = multimodal_query_result
        self.process_calls: list[tuple[str, str, str]] = []
        self.query_calls: list[tuple[str, str, str]] = []
        self.multimodal_calls: list[tuple[str, str, list[Any]]] = []

    async def get_or_create_instance(self, _kb: KnowledgeBase) -> object:
        return object()

    async def process_document(self, kb_id: str, file_path: str, doc_id: str) -> None:
        self.process_calls.append((kb_id, file_path, doc_id))
        if self.process_error is not None:
            raise self.process_error

    async def query(self, kb_id: str, query: str, mode: str = "hybrid") -> tuple[str, list[str]]:
        self.query_calls.append((kb_id, query, mode))
        return self.query_result

    async def query_multimodal(self, kb_id: str, query: str, content: list[Any]) -> tuple[str, list[str]]:
        self.multimodal_calls.append((kb_id, query, content))
        return self.multimodal_query_result

    async def close_instance(self, _kb_id: str) -> None:
        return None


def _build_service(
    *,
    process_error: Exception | None = None,
    query_result: tuple[str, list[str]] = ("", []),
    multimodal_query_result: tuple[str, list[str]] = ("", []),
) -> tuple[KnowledgeBaseService, _FakeKnowledgeRepository]:
    kb = KnowledgeBase(
        id="kb-1",
        user_id="user-1",
        name="Test KB",
        description="",
        status=KnowledgeBaseStatus.READY,
        storage_path="/tmp/kb-1",
    )
    repo = _FakeKnowledgeRepository(kb)
    adapter = _FakeAdapter(
        process_error=process_error,
        query_result=query_result,
        multimodal_query_result=multimodal_query_result,
    )
    settings = SimpleNamespace(
        knowledge_base_storage_dir="/tmp",
        knowledge_base_max_file_size_mb=10,
    )
    return KnowledgeBaseService(repo, adapter, settings), repo


def _create_temp_upload_file(content: bytes = b"test document") -> str:
    fd, path = tempfile.mkstemp(prefix="kb_upload_test_", suffix=".txt")
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    return path


@pytest.mark.asyncio
async def test_index_document_async_cleans_up_temp_file_on_success() -> None:
    service, repo = _build_service()
    file_path = _create_temp_upload_file()

    doc = await service.index_document_async(
        kb_id="kb-1",
        user_id="user-1",
        file_path=file_path,
        filename="sample.txt",
    )
    await asyncio.wait_for(service._indexing_tasks[doc.id], timeout=2.0)

    assert not os.path.exists(file_path)
    assert repo.documents[doc.id].status == DocumentStatus.INDEXED
    assert repo.kb_updates[-1][0] == "kb-1"


@pytest.mark.asyncio
async def test_index_document_async_cleans_up_temp_file_on_failure() -> None:
    service, repo = _build_service(process_error=RuntimeError("mineru failed"))
    file_path = _create_temp_upload_file()

    doc = await service.index_document_async(
        kb_id="kb-1",
        user_id="user-1",
        file_path=file_path,
        filename="broken.pdf",
    )
    await asyncio.wait_for(service._indexing_tasks[doc.id], timeout=2.0)

    assert not os.path.exists(file_path)
    assert repo.documents[doc.id].status == DocumentStatus.FAILED
    assert repo.documents[doc.id].error_message is not None
    assert "mineru failed" in repo.documents[doc.id].error_message


@pytest.mark.asyncio
async def test_query_propagates_sources_from_adapter() -> None:
    service, _repo = _build_service(
        query_result=(
            "A synthesized answer",
            ["source-a.pdf", "chunk:42"],
        )
    )

    result = await service.query(
        kb_id="kb-1",
        user_id="user-1",
        query="What does the document say?",
        mode="hybrid",
    )

    assert result.answer == "A synthesized answer"
    assert result.sources == ["source-a.pdf", "chunk:42"]
    assert result.mode == "hybrid"
    assert result.query_time_ms >= 0


@pytest.mark.asyncio
async def test_query_multimodal_propagates_sources_from_adapter() -> None:
    service, _repo = _build_service(
        multimodal_query_result=(
            "Multimodal answer",
            ["table:1", "equation:3"],
        )
    )

    result = await service.query_multimodal(
        kb_id="kb-1",
        user_id="user-1",
        query="Compare this table with the doc",
        content=[{"type": "table", "table_data": "a,b\n1,2"}],
    )

    assert result.answer == "Multimodal answer"
    assert result.sources == ["table:1", "equation:3"]
    assert result.mode == "multimodal"
    assert result.query_time_ms >= 0
