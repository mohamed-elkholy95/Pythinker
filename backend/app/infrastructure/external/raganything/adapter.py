"""RAG-Anything adapter bridging the library to Pythinker infrastructure.

Wraps RAGAnything per-knowledge-base instances, bridging Pythinker's LLM
and embedding clients to the RAG-Anything callable interfaces.

Lazy imports ensure startup does not fail when raganything is not installed.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.domain.exceptions.base import KnowledgeBaseException
from app.domain.models.knowledge_base import KnowledgeBase

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)


class RAGAnythingAdapter:
    """Bridges RAG-Anything library to Pythinker infrastructure.

    Each knowledge base gets its own RAGAnything instance stored in
    `_instances`, keyed by knowledge base ID. Embedding dimensions and
    LLM callables are resolved once and reused.
    """

    EMBEDDING_DIM = 1536  # text-embedding-3-small
    EMBEDDING_MAX_TOKENS = 8192

    def __init__(self, settings: "Settings", llm: "LLM") -> None:
        self._settings = settings
        self._llm = llm
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

    async def process_document(self, kb_id: str, file_path: str, doc_id: str) -> None:
        """Index a document into the knowledge base.

        Runs the blocking MinerU parse + LightRAG insert in a thread pool
        so as not to block the asyncio event loop.
        """
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: instance.insert_file(
                    file_path,
                    file_id=doc_id,
                    parse_method=self._settings.knowledge_base_parse_method,
                ),
            )
        except Exception as exc:
            raise KnowledgeBaseException(f"Failed to index document {file_path}: {exc}") from exc

    async def query(self, kb_id: str, query: str, mode: str = "hybrid") -> str:
        """Run a text query against a knowledge base."""
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: instance.query(query, mode=mode),
            )
            return str(result)
        except Exception as exc:
            raise KnowledgeBaseException(f"Query failed: {exc}") from exc

    async def query_multimodal(self, kb_id: str, query: str, content: list[Any]) -> str:
        """Run a multimodal query against a knowledge base."""
        if kb_id not in self._instances:
            raise KnowledgeBaseException(f"No RAGAnything instance for kb_id={kb_id!r}")

        instance = self._instances[kb_id]
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: instance.query_with_multimodal_content(query, content=content),
            )
            return str(result)
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
            from lightrag import EmbeddingFunc
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

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Delegate embedding to the LLM's embed_batch method if available."""
        embed_batch = getattr(self._llm, "embed_batch", None)
        if embed_batch is None:
            raise KnowledgeBaseException(
                "LLM does not support embed_batch; cannot generate embeddings for knowledge base"
            )
        return await embed_batch(texts)
