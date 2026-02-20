"""RAG-Anything adapter bridging the library to Pythinker infrastructure.

Wraps RAGAnything per-knowledge-base instances, bridging Pythinker's LLM
and embedding clients to the RAG-Anything callable interfaces.

Lazy imports ensure startup does not fail when raganything is not installed.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.domain.exceptions.base import KnowledgeBaseException
from app.domain.models.knowledge_base import KnowledgeBase

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.external.llm import LLM
    from app.infrastructure.external.embedding.client import EmbeddingClient

logger = logging.getLogger(__name__)


class RAGAnythingAdapter:
    """Bridges RAG-Anything library to Pythinker infrastructure.

    Each knowledge base gets its own RAGAnything instance stored in
    `_instances`, keyed by knowledge base ID. Embedding dimensions and
    LLM callables are resolved once and reused.
    """

    EMBEDDING_DIM = 1536  # text-embedding-3-small
    EMBEDDING_MAX_TOKENS = 8192

    def __init__(self, settings: "Settings", llm: "LLM", embedding_client: "EmbeddingClient") -> None:
        self._settings = settings
        self._llm = llm
        self._embedding_client = embedding_client
        self._instances: dict[str, Any] = {}  # kb_id -> RAGAnything instance

    # ── Public API ────────────────────────────────────────────────────────

    async def get_or_create_instance(self, kb: KnowledgeBase) -> Any:
        """Return the RAGAnything instance for a knowledge base, creating if needed."""
        if kb.id in self._instances:
            return self._instances[kb.id]

        try:
            from raganything import RAGAnything, RAGAnythingConfig
        except ImportError as exc:
            raise KnowledgeBaseException("raganything is not installed. Run: pip install raganything") from exc

        working_dir = Path(kb.storage_path)
        working_dir.mkdir(parents=True, exist_ok=True)

        config = RAGAnythingConfig(
            working_dir=str(working_dir),
            parse_method=self._settings.knowledge_base_parse_method,
            enable_image_processing=self._settings.knowledge_base_enable_image_processing,
            enable_table_processing=self._settings.knowledge_base_enable_table_processing,
            enable_equation_processing=self._settings.knowledge_base_enable_equation_processing,
        )

        llm_func = self._build_llm_func()
        vision_func = self._build_vision_func() if self._settings.knowledge_base_vlm_enhanced else None
        embedding_func = self._build_embedding_func()

        instance = RAGAnything(
            config=config,
            llm_model_func=llm_func,
            vision_model_func=vision_func,
            embedding_func=embedding_func,
        )
        self._instances[kb.id] = instance
        logger.info("Created RAGAnything instance for kb=%s at %s", kb.id, working_dir)
        return instance

    # Plain-text file extensions that can be read directly — no MinerU needed.
    _TEXT_EXTENSIONS = frozenset(
        {".txt", ".md", ".rst", ".csv", ".json", ".xml", ".html", ".htm", ".yaml", ".yml", ".log"}
    )

    async def process_document(self, kb_id: str, file_path: str, doc_id: str) -> None:
        """Index a document into the knowledge base.

        Plain-text files are inserted via insert_content_list() to bypass MinerU
        (which loads heavy ML models and causes OOM in constrained containers).
        Binary/PDF files use process_document_complete() for full MinerU parsing.
        """
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        suffix = Path(file_path).suffix.lower()
        try:
            if suffix in self._TEXT_EXTENSIONS:
                # Fast path: read text and insert directly into LightRAG —
                # bypasses MinerU (heavy ML models not needed for plain text).
                text = Path(file_path).read_text(encoding="utf-8", errors="replace").strip()
                if not text:
                    raise KnowledgeBaseException(f"Document {file_path} is empty")
                content_list = [{"type": "text", "text": text}]
                await instance._ensure_lightrag_initialized()
                await instance.insert_content_list(content_list, file_path=file_path, doc_id=doc_id)
                await instance.finalize_storages()
            else:
                # Full MinerU pipeline for PDFs, Office docs, images, etc.
                await instance.process_document_complete(
                    file_path,
                    doc_id=doc_id,
                    parse_method=self._settings.knowledge_base_parse_method,
                )
        except Exception as exc:
            raise KnowledgeBaseException(f"Failed to index document {file_path}: {exc}") from exc

    async def query(self, kb_id: str, query: str, mode: str = "hybrid") -> tuple[str, list[str]]:
        """Run a text query and return normalized answer and source references."""
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        try:
            await instance._ensure_lightrag_initialized()
            result = await instance.aquery(query, mode=mode)
            return self._normalize_query_response(result)
        except Exception as exc:
            raise KnowledgeBaseException(f"Query failed: {exc}") from exc

    async def query_multimodal(self, kb_id: str, query: str, content: list[Any]) -> tuple[str, list[str]]:
        """Run a multimodal query and return normalized answer and source references."""
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        try:
            await instance._ensure_lightrag_initialized()
            result = await instance.aquery_with_multimodal(query, multimodal_content=content, mode="mix")
            return self._normalize_query_response(result)
        except Exception as exc:
            raise KnowledgeBaseException(f"Multimodal query failed: {exc}") from exc

    async def close_instance(self, kb_id: str) -> None:
        """Release resources for a knowledge base instance."""
        instance = self._instances.pop(kb_id, None)
        if instance is not None:
            try:
                close = getattr(instance, "close", None)
                if close is not None:
                    if asyncio.iscoroutinefunction(close):
                        await close()
                    else:
                        close()
            except Exception as exc:
                logger.warning("Error closing RAGAnything instance kb=%s: %s", kb_id, exc)

    async def close_all(self) -> None:
        """Release all knowledge base instances."""
        for kb_id in list(self._instances.keys()):
            await self.close_instance(kb_id)

    # ── Private bridge builders ───────────────────────────────────────────

    def _build_llm_func(self) -> Callable:
        """Build an async LLM callable compatible with RAG-Anything."""
        llm = self._llm

        async def _llm_func(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> str:
            messages: list[dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if history_messages:
                messages.extend(history_messages)
            messages.append({"role": "user", "content": prompt})
            response = await llm.ask(messages)
            return response.content if hasattr(response, "content") else str(response)

        return _llm_func

    def _build_vision_func(self) -> Callable | None:
        """Build an async vision LLM callable. Returns None if not supported."""
        llm = self._llm

        # Only attach vision func if the LLM signals vision support
        if not getattr(llm, "supports_vision", False):
            logger.debug("LLM does not support vision; VLM-enhanced queries disabled")
            return None

        async def _vision_func(
            prompt: str,
            image_data: str,  # base64
            image_media_type: str = "image/jpeg",
            system_prompt: str | None = None,
            **kwargs: Any,
        ) -> str:
            messages: list[dict[str, Any]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{image_media_type};base64,{image_data}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            )
            response = await llm.ask(messages)
            return response.content if hasattr(response, "content") else str(response)

        return _vision_func

    def _build_embedding_func(self) -> Any:
        """Build an EmbeddingFunc wrapping Pythinker's LLM embed_batch."""
        try:
            from lightrag.utils import EmbeddingFunc
        except ImportError:
            # lightrag is a transitive dependency of raganything; if absent, return a stub
            logger.warning("lightrag not available; embedding func will be a plain async callable")

            async def _plain_embed(texts: list[str]) -> list[list[float]]:
                return await self._embed_texts(texts)

            return _plain_embed

        async def _embed_texts(texts: list[str]) -> list[list[float]]:
            return await self._embed_texts(texts)

        return EmbeddingFunc(
            embedding_dim=self.EMBEDDING_DIM,
            max_token_size=self.EMBEDDING_MAX_TOKENS,
            func=_embed_texts,
        )

    async def _embed_texts(self, texts: list[str]) -> Any:
        """Delegate embedding to the EmbeddingClient.

        Returns a numpy ndarray (shape: [n_texts, embedding_dim]) because
        LightRAG's EmbeddingFunc.__call__ validates via result.size (numpy API).
        """
        import numpy as np

        vectors = await self._embedding_client.embed_batch(texts)
        return np.array(vectors, dtype=np.float32)

    def _normalize_query_response(self, result: Any) -> tuple[str, list[str]]:
        """Normalize diverse query response formats into (answer, sources).

        LightRAG naive mode may return:
        - A plain string (most modes)
        - A ChatCompletionMessage object (openai SDK) with a .content attribute
        - A dict with a 'content' key
        - A stringified representation of the above (str(message_object))
        """
        # Handle OpenAI ChatCompletionMessage objects (and similar) before string check.
        # These have a .content attribute but are not plain str/Mapping instances.
        if hasattr(result, "content") and not isinstance(result, (str, bytes)):
            content = getattr(result, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip(), []

        if isinstance(result, str):
            # LightRAG naive mode may return str(ChatCompletionMessage) in some versions,
            # producing a serialized message-like dictionary string.
            # Parse safely via json after normalising Python single-quote dicts.
            stripped = result.strip()
            if stripped.startswith("{") and "content" in stripped:
                import json

                try:
                    # Replace Python single-quotes with double-quotes for JSON parsing.
                    # Only attempt this when the string looks like a serialised dict.
                    json_str = (
                        stripped.replace("'", '"')
                        .replace("None", "null")
                        .replace("True", "true")
                        .replace("False", "false")
                    )
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict):
                        content = parsed.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip(), []
                except Exception as exc:
                    logger.debug("Failed to parse serialized query response payload: %s", exc)
            return result, []

        answer: str | None = None
        sources: list[str] = []

        if isinstance(result, Mapping):
            answer = self._extract_answer_from_mapping(result)
            sources = self._normalize_sources(
                result.get("sources")
                or result.get("citations")
                or result.get("references")
                or result.get("retrieved_contexts")
                or result.get("contexts")
            )
        else:
            answer = self._extract_answer_from_object(result)
            sources = self._normalize_sources(
                getattr(result, "sources", None)
                or getattr(result, "citations", None)
                or getattr(result, "references", None)
                or getattr(result, "retrieved_contexts", None)
            )

        if answer is None:
            answer = str(result)
        return answer, sources

    def _extract_answer_from_mapping(self, result: Mapping[str, Any]) -> str | None:
        for key in ("answer", "response", "result", "content", "text", "message"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _extract_answer_from_object(self, result: Any) -> str | None:
        for attr in ("answer", "response", "result", "content", "text", "message"):
            value = getattr(result, attr, None)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _normalize_sources(self, raw_sources: Any) -> list[str]:
        if raw_sources is None:
            return []
        if isinstance(raw_sources, str):
            return [raw_sources]
        if isinstance(raw_sources, Mapping):
            source = self._source_item_to_string(raw_sources)
            return [source] if source else []
        if isinstance(raw_sources, Iterable):
            normalized: list[str] = []
            for item in raw_sources:
                source = self._source_item_to_string(item)
                if source:
                    normalized.append(source)
            return normalized
        return [str(raw_sources)]

    def _source_item_to_string(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, Mapping):
            for key in ("source", "id", "title", "path", "file_path", "doc_id", "chunk_id", "content", "text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return str(dict(item))
        if item is None:
            return ""
        return str(item)
