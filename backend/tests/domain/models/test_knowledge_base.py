"""Tests for knowledge base domain models."""

from app.domain.models.knowledge_base import (
    DocumentStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
    KnowledgeQueryResult,
)


class TestKnowledgeBaseStatus:
    def test_values(self) -> None:
        expected = {"creating", "ready", "indexing", "error"}
        assert {s.value for s in KnowledgeBaseStatus} == expected


class TestDocumentStatus:
    def test_values(self) -> None:
        expected = {"pending", "processing", "indexed", "failed"}
        assert {s.value for s in DocumentStatus} == expected


class TestKnowledgeBase:
    def test_defaults(self) -> None:
        kb = KnowledgeBase(id="kb-1", user_id="u-1", name="My KB")
        assert kb.status == KnowledgeBaseStatus.CREATING
        assert kb.document_count == 0
        assert kb.description == ""


class TestKnowledgeDocument:
    def test_defaults(self) -> None:
        doc = KnowledgeDocument(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="report.pdf",
            file_type="application/pdf",
            file_size_bytes=1024,
        )
        assert doc.status == DocumentStatus.PENDING
        assert doc.chunk_count == 0
        assert doc.error_message is None


class TestKnowledgeQueryResult:
    def test_defaults(self) -> None:
        r = KnowledgeQueryResult(answer="Python is a language")
        assert r.sources == []
        assert r.query_time_ms == 0.0
        assert r.mode == "hybrid"
