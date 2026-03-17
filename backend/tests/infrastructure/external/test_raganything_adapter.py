"""Unit tests for RAGAnythingAdapter response normalization."""

from types import SimpleNamespace

import pytest

from app.infrastructure.external.raganything.adapter import RAGAnythingAdapter


class _DummyLLM:
    supports_vision = False


def _build_adapter() -> RAGAnythingAdapter:
    from unittest.mock import MagicMock

    settings = SimpleNamespace(
        knowledge_base_parse_method="auto",
        knowledge_base_enable_image_processing=True,
        knowledge_base_enable_table_processing=True,
        knowledge_base_enable_equation_processing=True,
        knowledge_base_vlm_enhanced=False,
    )
    return RAGAnythingAdapter(settings=settings, llm=_DummyLLM(), embedding_client=MagicMock())


def test_normalize_query_response_from_mapping_with_sources() -> None:
    adapter = _build_adapter()

    answer, sources = adapter._normalize_query_response(
        {
            "answer": "Structured answer",
            "sources": [
                {"path": "/docs/report.pdf"},
                {"doc_id": "doc-123"},
                "chunk-9",
            ],
        }
    )

    assert answer == "Structured answer"
    assert sources == ["/docs/report.pdf", "doc-123", "chunk-9"]


def test_normalize_query_response_uses_fallback_keys() -> None:
    adapter = _build_adapter()

    answer, sources = adapter._normalize_query_response(
        {
            "response": "Fallback answer key",
            "citations": [{"id": "citation-1"}, {"title": "Appendix A"}],
        }
    )

    assert answer == "Fallback answer key"
    assert sources == ["citation-1", "Appendix A"]


def test_normalize_query_response_from_plain_string() -> None:
    adapter = _build_adapter()

    answer, sources = adapter._normalize_query_response("Plain text answer")

    assert answer == "Plain text answer"
    assert sources == []


@pytest.mark.asyncio
async def test_query_requests_references_when_supported() -> None:
    adapter = _build_adapter()

    class _FakeInstance:
        def __init__(self) -> None:
            self.aquery_calls: list[dict] = []

        async def _ensure_lightrag_initialized(self) -> None:
            pass

        async def aquery(self, query: str, mode: str = "hybrid"):
            self.aquery_calls.append({"query": query, "mode": mode})
            return {
                "answer": f"answer for {query} in {mode}",
                "references": [{"file_path": "/docs/ref.md"}],
            }

    instance = _FakeInstance()
    adapter._instances["kb-1"] = instance

    answer, sources = await adapter.query("kb-1", "what is this", mode="hybrid")

    assert len(instance.aquery_calls) == 1
    assert instance.aquery_calls[0] == {"query": "what is this", "mode": "hybrid"}
    assert answer == "answer for what is this in hybrid"
    assert sources == ["/docs/ref.md"]


@pytest.mark.asyncio
async def test_query_falls_back_for_legacy_signature_without_reference_kwarg() -> None:
    adapter = _build_adapter()

    class _FakeInstance:
        def __init__(self) -> None:
            self.aquery_calls: list[dict] = []

        async def _ensure_lightrag_initialized(self) -> None:
            pass

        async def aquery(self, query: str, mode: str = "hybrid"):
            self.aquery_calls.append({"query": query, "mode": mode})
            return {
                "response": f"legacy answer for {query} in {mode}",
                "references": [{"file_path": "/legacy/ref.txt"}],
            }

    instance = _FakeInstance()
    adapter._instances["kb-2"] = instance

    answer, sources = await adapter.query("kb-2", "legacy question", mode="local")

    assert len(instance.aquery_calls) == 1
    assert answer == "legacy answer for legacy question in local"
    assert sources == ["/legacy/ref.txt"]
