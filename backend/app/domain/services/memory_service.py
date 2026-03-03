"""Memory service for cross-session knowledge management.

Provides high-level operations for:
- Storing and retrieving long-term memories
- Extracting memories from conversations
- Semantic search with embeddings
- Memory consolidation and cleanup
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from openai import APIConnectionError as OpenAIConnectionError
from openai import APIError as OpenAIAPIError
from openai import AsyncOpenAI

from app.core.async_utils import gather_compat
from app.domain.exceptions.base import IntegrationException, LLMException
from app.domain.external.llm import LLM
from app.domain.models.long_term_memory import (
    ExtractedMemory,
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemorySearchResult,
    MemorySource,
    MemoryStats,
    MemoryType,
    MemoryUpdate,
)
from app.domain.models.sync_outbox import OutboxCreate, OutboxOperation
from app.domain.repositories.memory_repository import MemoryRepository
from app.domain.repositories.sync_outbox_repository import SyncOutboxRepositoryProtocol
from app.domain.repositories.vector_memory_repository import get_vector_memory_repository

if TYPE_CHECKING:
    from app.domain.models.memory import Memory


def _get_vector_repo():
    """Get VectorMemoryRepository via domain singleton."""
    return get_vector_memory_repository()


logger = logging.getLogger(__name__)


# Patterns for extracting memorable content
PREFERENCE_PATTERNS = [
    r"(?:I |i )(?:prefer|like|love|hate|dislike|want|need)\s+(.+?)(?:\.|$)",
    r"(?:my|My)\s+(?:favorite|preferred)\s+(.+?)\s+is\s+(.+?)(?:\.|$)",
    r"(?:always|never|usually)\s+(.+?)(?:\.|$)",
]

FACT_PATTERNS = [
    r"(?:I |i )(?:am|work|live|have)\s+(.+?)(?:\.|$)",
    r"(?:my|My)\s+(.+?)\s+is\s+(.+?)(?:\.|$)",
]


class MemoryService:
    """Service for managing long-term memories.

    Provides:
    - Memory CRUD with automatic embedding generation
    - Semantic and keyword search
    - Memory extraction from conversations
    - Automatic consolidation and cleanup
    """

    def __init__(
        self,
        repository: MemoryRepository,
        llm: LLM | None = None,
        embedding_model: str | None = None,
        outbox_repo: SyncOutboxRepositoryProtocol | None = None,
    ):
        """Initialize memory service.

        Args:
            repository: Memory storage backend
            llm: Optional LLM for memory extraction and embedding
            embedding_model: Optional model name for embeddings
            outbox_repo: Optional outbox repository for reliable sync (injected from composition root)
        """
        self._repository = repository
        self._llm = llm

        # Phase 2: Outbox repository for reliable sync (injected via DI)
        self._outbox_repo = outbox_repo

        # Initialize embedding client (separate from chat model)
        # This allows using OpenAI embeddings while using any chat provider
        from app.core.config import get_settings

        settings = get_settings()
        self._embedding_model = embedding_model or settings.embedding_model

        # Create dedicated embedding client
        embedding_api_key = settings.embedding_api_key or settings.api_key
        if embedding_api_key and settings.embedding_api_base:
            self._embedding_client = AsyncOpenAI(api_key=embedding_api_key, base_url=settings.embedding_api_base)
            logger.info(f"Embedding client initialized with {settings.embedding_api_base}")
        else:
            self._embedding_client = None
            logger.warning("No embedding API configured, using fallback embeddings")

        # Configuration
        self._max_memories_per_user = 10000
        self._dedup_threshold = 0.95  # Similarity threshold for deduplication
        self._consolidation_threshold = 0.85  # Threshold for merging similar memories

    @staticmethod
    def _get_settings():
        """Lazy-load settings to avoid top-level core import."""
        from app.core.config import get_settings

        return get_settings()

    async def store_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        source: MemorySource = MemorySource.SYSTEM,
        session_id: str | None = None,
        entities: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        generate_embedding: bool = True,
    ) -> MemoryEntry:
        """Store a new memory.

        Args:
            user_id: User who owns this memory
            content: Memory content text
            memory_type: Type of memory
            importance: Importance level
            source: Where memory came from
            session_id: Session where created
            entities: Named entities in content
            tags: User/system tags
            metadata: Additional metadata
            generate_embedding: Whether to generate embedding

        Returns:
            Created memory entry
        """
        # Check for duplicates
        content_hash = self._compute_hash(content)
        duplicates = await self._repository.find_duplicates(user_id, content_hash)

        if duplicates:
            # Update existing instead of creating duplicate
            existing = duplicates[0]
            logger.debug(f"Found duplicate memory {existing.id}, updating instead")
            await self._repository.update(
                existing.id,
                MemoryUpdate(
                    importance=importance if importance.value > existing.importance.value else None,
                    tags=list(set(existing.tags + (tags or []))),
                ),
            )
            return existing

        # Extract keywords
        keywords = self._extract_keywords(content)

        # Phase 1: Generate both dense and sparse vectors
        embedding = None
        sparse_vector = None
        embedding_model = None
        embedding_provider = None
        embedding_quality = 1.0

        if generate_embedding and self._llm:
            try:
                # Dense embedding (OpenAI API)
                embedding = await self._generate_embedding(content)
                embedding_model = self._embedding_model
                embedding_provider = "openai" if self._embedding_client else "fallback"
                embedding_quality = 1.0 if self._embedding_client else 0.5

                # Sparse vector (self-hosted BM25)
                sparse_vector = self._generate_sparse_vector(content)

            except (OpenAIAPIError, OpenAIConnectionError) as e:
                logger.warning("Embedding API error during store_memory: %s", e)
            except (ValueError, TypeError) as e:
                logger.warning("Invalid input for embedding generation: %s", e)

        # Create memory entry with Phase 1 metadata
        memory = MemoryEntry(
            id="",  # Will be generated
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            source=source,
            embedding=embedding,
            keywords=keywords,
            session_id=session_id,
            entities=entities or [],
            tags=tags or [],
            metadata=metadata or {},
            # Phase 1: Embedding metadata
            embedding_model=embedding_model,
            embedding_provider=embedding_provider,
            embedding_quality=embedding_quality,
        )

        # Phase 5: Check if parallel memory writes are enabled
        settings = self._get_settings()
        use_parallel = settings.feature_parallel_memory

        if use_parallel and embedding:
            # Use parallel writes to MongoDB and vector store
            created_memory = await self._store_memory_parallel(
                memory=memory,
                embedding=embedding,
                sparse_vector=sparse_vector,
                memory_type=memory_type,
                importance=importance,
                tags=tags,
            )
        else:
            # Sequential writes (original behavior)
            created_memory = await self._repository.create(memory)

            # Phase 2: Write to outbox instead of direct Qdrant sync
            if embedding and self._outbox_repo:
                try:
                    await self._outbox_repo.create(
                        OutboxCreate(
                            operation=OutboxOperation.UPSERT,
                            collection_name="user_knowledge",
                            payload={
                                "memory_id": created_memory.id,
                                "user_id": created_memory.user_id,
                                "embedding": embedding,
                                "memory_type": memory_type.value,
                                "importance": importance.value,
                                "tags": tags or [],
                                "sparse_vector": sparse_vector,
                                "session_id": session_id,
                                "created_at": created_memory.created_at.isoformat(),
                            },
                        )
                    )
                    # Mark as pending sync
                    await self._repository.update(
                        created_memory.id,
                        MemoryUpdate(sync_state="pending"),
                    )
                except Exception as e:
                    # Broad catch justified: outbox write is non-critical and must
                    # not prevent the primary MongoDB write from succeeding. The
                    # outbox layer may raise driver errors (pymongo) or validation
                    # errors that we cannot enumerate exhaustively.
                    logger.error("Failed to create outbox entry for memory %s: %s", created_memory.id, e)
                    # Mark as failed
                    await self._repository.update(
                        created_memory.id,
                        MemoryUpdate(
                            sync_state="failed",
                            sync_attempts=1,
                            last_sync_attempt=datetime.now(UTC),
                            sync_error=str(e)[:500],
                        ),
                    )

        return created_memory

    async def _store_memory_parallel(
        self,
        memory: MemoryEntry,
        embedding: list[float],
        sparse_vector: dict[int, float] | None,
        memory_type: MemoryType,
        importance: MemoryImportance,
        tags: list[str] | None,
    ) -> MemoryEntry:
        """Store memory in parallel to MongoDB and vector store.

        Phase 5 Enhancement: MongoDB write must complete first (to get the ID),
        then vector store write runs. For true parallelism across multiple
        memories, use _store_many_parallel which uses gather_compat.

        Args:
            memory: Memory entry to store
            embedding: Dense embedding vector
            sparse_vector: BM25 sparse vector (Phase 1)
            memory_type: Type of memory
            importance: Importance level
            tags: Optional tags

        Returns:
            Created memory entry from MongoDB
        """
        # MongoDB write first to get the generated ID
        try:
            mongo_result = await self._repository.create(memory)
        except (OSError, ConnectionError) as e:
            logger.error("MongoDB connection failed during parallel store: %s", e)
            raise IntegrationException(f"MongoDB unavailable: {e}", service="mongodb") from e

        # Phase 2: Write to outbox for async sync
        if self._outbox_repo:
            try:
                await self._outbox_repo.create(
                    OutboxCreate(
                        operation=OutboxOperation.UPSERT,
                        collection_name="user_knowledge",
                        payload={
                            "memory_id": mongo_result.id,
                            "user_id": mongo_result.user_id,
                            "embedding": embedding,
                            "memory_type": memory_type.value,
                            "importance": importance.value,
                            "tags": tags or [],
                            "sparse_vector": sparse_vector,
                            "session_id": memory.session_id,
                            "created_at": mongo_result.created_at.isoformat(),
                        },
                    )
                )
                # Mark as pending sync
                await self._repository.update(
                    mongo_result.id,
                    MemoryUpdate(sync_state="pending"),
                )
            except Exception as e:
                # Broad catch justified: outbox write is non-critical and must
                # not roll back the successful MongoDB write. The outbox layer may
                # raise driver errors (pymongo) or validation errors.
                logger.error("Memory created in MongoDB but outbox write failed: %s", e)
                # Mark as failed
                await self._repository.update(
                    mongo_result.id,
                    MemoryUpdate(
                        sync_state="failed",
                        sync_attempts=1,
                        last_sync_attempt=datetime.now(UTC),
                        sync_error=str(e)[:500],
                    ),
                )

        return mongo_result

    async def store_many(
        self, user_id: str, memories: list[ExtractedMemory], session_id: str | None = None
    ) -> list[MemoryEntry]:
        """Store multiple extracted memories.

        Args:
            user_id: User who owns these memories
            memories: List of extracted memories
            session_id: Session where created

        Returns:
            List of created memories
        """
        # Phase 5: Check if parallel memory writes are enabled
        settings = self._get_settings()
        use_parallel = settings.feature_parallel_memory

        if use_parallel and len(memories) > 1:
            return await self._store_many_parallel(user_id, memories, session_id)

        # Sequential writes (original behavior)
        created = []
        for extracted in memories:
            try:
                memory = await self.store_memory(
                    user_id=user_id,
                    content=extracted.content,
                    memory_type=extracted.memory_type,
                    importance=extracted.importance,
                    source=MemorySource.USER_INFERRED,
                    session_id=session_id,
                    entities=extracted.entities,
                    tags=[],
                    metadata={
                        "source_text": extracted.source_text,
                        "extraction_reasoning": extracted.reasoning,
                        "confidence": extracted.confidence,
                    },
                )
                created.append(memory)
            except (IntegrationException, OSError, ValueError) as e:
                logger.warning("Failed to store extracted memory: %s", e)

        return created

    async def _store_many_parallel(
        self,
        user_id: str,
        memories: list[ExtractedMemory],
        session_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Store multiple memories in parallel.

        Phase 5 Enhancement: Uses TaskGroup for parallel memory creation.

        Args:
            user_id: User who owns these memories
            memories: List of extracted memories
            session_id: Session where created

        Returns:
            List of created memories
        """
        settings = self._get_settings()
        use_taskgroup = settings.feature_taskgroup_enabled

        async def store_single(extracted: ExtractedMemory) -> MemoryEntry | None:
            try:
                return await self.store_memory(
                    user_id=user_id,
                    content=extracted.content,
                    memory_type=extracted.memory_type,
                    importance=extracted.importance,
                    source=MemorySource.USER_INFERRED,
                    session_id=session_id,
                    entities=extracted.entities,
                    tags=[],
                    metadata={
                        "source_text": extracted.source_text,
                        "extraction_reasoning": extracted.reasoning,
                        "confidence": extracted.confidence,
                    },
                )
            except (IntegrationException, OSError, ValueError) as e:
                logger.warning("Failed to store extracted memory in parallel: %s", e)
                return None

        # Create tasks for all memories
        tasks = [store_single(mem) for mem in memories]

        # Execute in parallel
        results = await gather_compat(*tasks, return_exceptions=True, use_taskgroup=use_taskgroup)

        # Filter successful results
        created = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Memory store task failed: {result}")
            elif result is not None:
                created.append(result)

        logger.info(f"Stored {len(created)}/{len(memories)} memories in parallel")
        return created

    async def retrieve_relevant(
        self,
        user_id: str,
        context: str,
        limit: int = 10,
        memory_types: list[MemoryType] | None = None,
        min_relevance: float = 0.3,
        enable_reranking: bool = False,
        enable_mmr: bool = False,
        mmr_lambda: float = 0.7,
    ) -> list[MemorySearchResult]:
        """Retrieve memories relevant to a context.

        Uses vector store for fast vector search when available, with MongoDB fallback.
        This is a hybrid approach: vector store handles vector similarity, MongoDB stores
        full documents.

        Phase 3 enhancements:
        - Optional cross-encoder reranking for improved precision
        - Optional MMR diversification for result diversity

        Args:
            user_id: User to retrieve for
            context: Current context/query
            limit: Maximum memories to return
            memory_types: Optional type filter
            min_relevance: Minimum relevance score
            enable_reranking: Use cross-encoder reranking (Phase 3)
            enable_mmr: Use MMR diversification (Phase 3)
            mmr_lambda: MMR trade-off (1.0=relevance, 0.0=diversity)

        Returns:
            List of relevant memories with scores
        """
        # Fetch more candidates if reranking or MMR enabled
        fetch_limit = limit * 3 if (enable_reranking or enable_mmr) else limit

        # Try vector store-based semantic search first
        vector_repo = _get_vector_repo()
        embedding = None
        results = []

        if self._llm and vector_repo:
            try:
                embedding = await self._generate_embedding(context)

                # WP-1: Hybrid retrieval — generate sparse BM25 vector when enabled.
                # Falls back to dense-only when the encoder is unfitted or flag is off.
                from app.core.config import get_settings as _get_settings

                _settings = _get_settings()
                sparse_vector: dict[str, float] | None = None
                if _settings.qdrant_use_hybrid_search:
                    try:
                        sparse_vector = self._generate_sparse_vector(context)
                    except Exception as _se:
                        logger.debug("Sparse vector generation skipped: %s", _se)

                # Choose search strategy: hybrid when sparse vector available, dense otherwise
                if sparse_vector:
                    vector_results = await vector_repo.search_hybrid(
                        user_id=user_id,
                        query_text=context,
                        dense_vector=embedding,
                        sparse_vector=sparse_vector,
                        limit=fetch_limit,
                        min_score=min_relevance,
                        memory_types=memory_types,
                    )
                else:
                    vector_results = await vector_repo.search_similar(
                        user_id=user_id,
                        query_vector=embedding,
                        limit=fetch_limit,
                        min_score=min_relevance,
                        memory_types=memory_types,
                    )

                if vector_results:
                    # Fetch full documents from MongoDB
                    memory_ids = [r.memory_id for r in vector_results]
                    memories = await self._repository.get_by_ids(memory_ids)

                    # Build lookup for fast matching
                    memory_lookup = {m.id: m for m in memories}

                    # Combine scores with full documents
                    for vector_result in vector_results:
                        memory = memory_lookup.get(vector_result.memory_id)
                        if memory:
                            results.append(
                                MemorySearchResult(
                                    memory=memory, relevance_score=vector_result.relevance_score, match_type="semantic"
                                )
                            )

            except (IntegrationException, OpenAIAPIError, OpenAIConnectionError, OSError, ValueError) as e:
                logger.warning("Vector store search failed, falling back to MongoDB: %s", e)

        # Fallback to MongoDB vector search (limited to 500 candidates)
        if not results and self._llm:
            try:
                if embedding is None:
                    embedding = await self._generate_embedding(context)

                results = await self._repository.vector_search(
                    user_id=user_id,
                    embedding=embedding,
                    limit=fetch_limit,
                    min_score=min_relevance,
                    memory_types=memory_types,
                )

            except (IntegrationException, OpenAIAPIError, OpenAIConnectionError, OSError, ValueError) as e:
                logger.warning("MongoDB vector search failed, falling back to keyword: %s", e)

        # Final fallback to keyword search
        if not results:
            keywords = self._extract_keywords(context)

            query = MemoryQuery(
                user_id=user_id,
                keywords=keywords,
                memory_types=memory_types or [],
                min_relevance=min_relevance,
                limit=fetch_limit,
            )

            results = await self._repository.search(query)

        # Phase 3: Reranking with cross-encoder
        if enable_reranking and len(results) > limit:
            try:
                from app.domain.services.retrieval.reranker import get_reranker

                reranker = get_reranker()

                if reranker.is_available():
                    # Prepare candidates
                    candidates = [(r.memory.content, {"memory_id": r.memory.id}) for r in results]

                    # Rerank
                    reranked = reranker.rerank(context, candidates, top_k=limit)

                    # Rebuild results with rerank scores
                    memory_lookup = {r.memory.id: r.memory for r in results}
                    results = []
                    for _text, meta, rerank_score in reranked:
                        mem_id = meta["memory_id"]
                        memory = memory_lookup[mem_id]
                        results.append(
                            MemorySearchResult(
                                memory=memory, relevance_score=rerank_score, match_type="hybrid_reranked"
                            )
                        )

                    logger.debug(f"Reranked {len(results)} memories")
                else:
                    # Reranker not available, just truncate
                    results = results[:limit]

            except (ImportError, ValueError, RuntimeError) as e:
                logger.debug("Reranking failed, using original results: %s", e)
                results = results[:limit]
        else:
            results = results[:limit]

        # Phase 3: MMR diversification
        if enable_mmr and len(results) > 1:
            try:
                from app.domain.services.retrieval.mmr import mmr_rerank

                if embedding is None:
                    embedding = await self._generate_embedding(context)

                diversified = mmr_rerank(
                    query_embedding=embedding,
                    candidates=results,
                    embedding_fn=lambda r: r.memory.embedding or [],
                    lambda_param=mmr_lambda,
                    top_k=limit,
                )
                results = diversified
                logger.debug(f"Applied MMR diversification to {len(results)} memories")

            except (ImportError, ValueError, RuntimeError, OpenAIAPIError, OpenAIConnectionError) as e:
                logger.debug("MMR diversification failed, using original results: %s", e)

        # Record access for all retrieved memories
        for result in results:
            await self._repository.record_access(result.memory.id)

        return results

    async def retrieve_for_task(
        self,
        user_id: str,
        task_description: str,
        include_preferences: bool = True,
        include_procedures: bool = True,
        include_errors: bool = True,
        limit: int = 15,
    ) -> list[MemorySearchResult]:
        """Retrieve memories relevant to a task.

        Specialized retrieval that combines different memory types
        useful for task execution.

        Args:
            user_id: User ID
            task_description: Description of the task
            include_preferences: Include user preferences
            include_procedures: Include how-to knowledge
            include_errors: Include error patterns
            limit: Maximum total memories

        Returns:
            Relevant memories for task execution
        """
        results = []

        # Get task-relevant memories
        types_to_include = []
        if include_preferences:
            types_to_include.append(MemoryType.PREFERENCE)
        if include_procedures:
            types_to_include.append(MemoryType.PROCEDURE)
        if include_errors:
            types_to_include.append(MemoryType.ERROR_PATTERN)

        # Add general types
        types_to_include.extend([MemoryType.FACT, MemoryType.PROJECT_CONTEXT, MemoryType.ENTITY])

        # Semantic search with task description
        task_results = await self.retrieve_relevant(
            user_id=user_id, context=task_description, limit=limit, memory_types=types_to_include, min_relevance=0.25
        )
        results.extend(task_results)

        # Also get critical memories (always relevant)
        critical_query = MemoryQuery(user_id=user_id, min_importance=MemoryImportance.CRITICAL, limit=5)
        critical_results = await self._repository.search(critical_query)
        for result in critical_results:
            if result.memory.id not in {r.memory.id for r in results}:
                results.append(result)

        # Sort by relevance and importance
        def score_key(r: MemorySearchResult) -> float:
            importance_boost = {"critical": 0.3, "high": 0.2, "medium": 0.1, "low": 0}
            return r.relevance_score + importance_boost.get(r.memory.importance.value, 0)

        results.sort(key=score_key, reverse=True)
        return results[:limit]

    async def extract_incremental(
        self,
        user_id: str,
        turns_content: list[str],
        session_id: str | None = None,
    ) -> None:
        """Extract and persist memories mid-session using pattern matching only.

        Fast, non-blocking, no LLM call. Detects preferences, facts, and corrections
        from recent conversation turns and stores them immediately.

        Args:
            user_id: User ID
            turns_content: Recent turn content strings to scan
            session_id: Optional session ID for tagging
        """
        if not turns_content:
            return

        extracted: list[tuple[str, MemoryType]] = []

        for content in turns_content:
            # Check preference patterns
            for pattern in PREFERENCE_PATTERNS:
                match = re.search(pattern, content)
                if match:
                    extracted.append((content.strip()[:500], MemoryType.PREFERENCE))
                    break
            else:
                # Check fact patterns
                for pattern in FACT_PATTERNS:
                    match = re.search(pattern, content)
                    if match:
                        extracted.append((content.strip()[:500], MemoryType.FACT))
                        break

        if not extracted:
            return

        for content, mem_type in extracted:
            try:
                await self.store_memory(
                    user_id=user_id,
                    content=content,
                    memory_type=mem_type,
                    importance=MemoryImportance.MEDIUM,
                    source=MemorySource.USER_INFERRED,
                    session_id=session_id,
                    generate_embedding=True,
                )
                logger.debug("Incremental memory stored: %s", content[:80])
            except Exception:
                logger.debug("Failed to store incremental memory", exc_info=True)

    async def extract_from_conversation(
        self, user_id: str, conversation: list[dict[str, str]], session_id: str | None = None
    ) -> list[ExtractedMemory]:
        """Extract memorable content from a conversation.

        Uses pattern matching and optionally LLM to identify
        preferences, facts, and other memorable information.

        Args:
            user_id: User ID
            conversation: List of message dicts with 'role' and 'content'
            session_id: Optional session ID

        Returns:
            List of extracted memories (not yet stored)
        """
        extracted = []

        # Get user messages
        user_messages = [msg["content"] for msg in conversation if msg.get("role") == "user"]

        full_text = " ".join(user_messages)

        # Pattern-based extraction for preferences
        for pattern in PREFERENCE_PATTERNS:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                content = match if isinstance(match, str) else " ".join(match)
                extracted.append(
                    ExtractedMemory(
                        content=f"User prefers: {content.strip()}",
                        memory_type=MemoryType.PREFERENCE,
                        importance=MemoryImportance.MEDIUM,
                        confidence=0.7,
                        source_text=content,
                        reasoning="Matched preference pattern",
                    )
                )

        # Pattern-based extraction for facts
        for pattern in FACT_PATTERNS:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                content = match if isinstance(match, str) else " ".join(match)
                extracted.append(
                    ExtractedMemory(
                        content=content.strip(),
                        memory_type=MemoryType.FACT,
                        importance=MemoryImportance.MEDIUM,
                        confidence=0.7,
                        source_text=content,
                        reasoning="Matched fact pattern",
                    )
                )

        # LLM-based extraction for more nuanced memories
        if self._llm and len(full_text) > 100:
            try:
                llm_extracted = await self._llm_extract_memories(full_text)
                extracted.extend(llm_extracted)
            except (LLMException, IntegrationException, OpenAIAPIError, OpenAIConnectionError, ValueError) as e:
                logger.warning("LLM memory extraction failed: %s", e)

        # Deduplicate
        seen_content = set()
        unique_extracted = []
        for mem in extracted:
            content_key = mem.content.lower().strip()
            if content_key not in seen_content:
                seen_content.add(content_key)
                unique_extracted.append(mem)

        return unique_extracted

    async def extract_from_task_result(
        self, user_id: str, task_description: str, task_result: str, success: bool, session_id: str | None = None
    ) -> list[ExtractedMemory]:
        """Extract memories from completed task results.

        Args:
            user_id: User ID
            task_description: What was requested
            task_result: What was produced
            success: Whether task succeeded
            session_id: Optional session ID

        Returns:
            Extracted memories from task
        """
        extracted = []

        # Store task outcome
        outcome_content = f"Task: {task_description[:200]}\nOutcome: {'Success' if success else 'Failed'}\nResult: {task_result[:300]}"
        extracted.append(
            ExtractedMemory(
                content=outcome_content,
                memory_type=MemoryType.TASK_OUTCOME,
                importance=MemoryImportance.MEDIUM if success else MemoryImportance.HIGH,
                confidence=0.9,
                source_text=task_description,
                reasoning="Task completion record",
            )
        )

        # If failed, extract error pattern
        if not success:
            extracted.append(
                ExtractedMemory(
                    content=f"Error pattern: {task_description[:100]} - {task_result[:200]}",
                    memory_type=MemoryType.ERROR_PATTERN,
                    importance=MemoryImportance.HIGH,
                    confidence=0.8,
                    source_text=task_result,
                    reasoning="Failed task error pattern",
                )
            )

        return extracted

    async def consolidate_memories(
        self, user_id: str, memory_type: MemoryType | None = None, max_to_consolidate: int = 50
    ) -> int:
        """Consolidate similar memories to reduce redundancy.

        Finds similar memories and merges them.

        Args:
            user_id: User to consolidate for
            memory_type: Optional type filter
            max_to_consolidate: Maximum memories to process

        Returns:
            Number of memories consolidated
        """
        # Get recent memories
        query = MemoryQuery(
            user_id=user_id, memory_types=[memory_type] if memory_type else [], limit=max_to_consolidate
        )
        results = await self._repository.search(query)

        if len(results) < 2:
            return 0

        consolidated_count = 0
        processed_ids = set()

        for i, result in enumerate(results):
            if result.memory.id in processed_ids:
                continue

            similar = []

            # Find similar memories
            for _j, other in enumerate(results[i + 1 :], i + 1):
                if other.memory.id in processed_ids:
                    continue

                if other.memory.memory_type == result.memory.memory_type:
                    # Check content similarity
                    similarity = self._text_similarity(result.memory.content, other.memory.content)

                    if similarity >= self._consolidation_threshold:
                        similar.append(other.memory)

            if similar:
                # Merge memories
                all_to_merge = [result.memory, *similar]
                merged_content = self._merge_content(all_to_merge)

                await self._repository.merge_memories(
                    memory_ids=[m.id for m in all_to_merge], merged_content=merged_content, keep_original=False
                )

                processed_ids.update(m.id for m in all_to_merge)
                consolidated_count += len(all_to_merge) - 1

        logger.info(f"Consolidated {consolidated_count} memories for user {user_id}")
        return consolidated_count

    async def cleanup(
        self, user_id: str | None = None, remove_expired: bool = True, consolidate: bool = True
    ) -> dict[str, int]:
        """Perform memory cleanup operations.

        Args:
            user_id: Optional user filter
            remove_expired: Remove expired memories
            consolidate: Consolidate similar memories

        Returns:
            Counts of operations performed
        """
        counts = {}

        if remove_expired:
            counts["expired_removed"] = await self._repository.cleanup_expired(user_id)

        if consolidate and user_id:
            counts["consolidated"] = await self.consolidate_memories(user_id)

        return counts

    async def get_stats(self, user_id: str) -> MemoryStats:
        """Get memory statistics for a user."""
        return await self._repository.get_stats(user_id)

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory from both MongoDB and vector store.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted successfully
        """
        # Phase 2: Write delete to outbox instead of direct Qdrant call
        if self._outbox_repo:
            try:
                await self._outbox_repo.create(
                    OutboxCreate(
                        operation=OutboxOperation.DELETE,
                        collection_name="user_knowledge",
                        payload={"memory_id": memory_id},
                    )
                )
            except Exception as e:
                # Broad catch justified: outbox delete is non-critical; the
                # primary MongoDB delete must proceed regardless. Vector store
                # orphans are cleaned up by the reconciliation worker.
                logger.warning("Failed to create outbox delete entry for memory %s: %s", memory_id, e)

        # Delete from MongoDB
        return await self._repository.delete(memory_id)

    async def delete_user_memories(self, user_id: str) -> int:
        """Delete all memories for a user from both MongoDB and vector store.

        Args:
            user_id: User whose memories to delete

        Returns:
            Number of memories deleted from MongoDB
        """
        # Get all memory IDs for this user first
        from app.domain.models.long_term_memory import MemoryQuery

        query = MemoryQuery(user_id=user_id, limit=10000)
        results = await self._repository.search(query)
        memory_ids = [r.memory.id for r in results]

        # Phase 2: Write batch delete to outbox
        if memory_ids and self._outbox_repo:
            try:
                await self._outbox_repo.create(
                    OutboxCreate(
                        operation=OutboxOperation.BATCH_DELETE,
                        collection_name="user_knowledge",
                        payload={"memory_ids": memory_ids},
                    )
                )
            except Exception as e:
                # Broad catch justified: outbox batch delete is non-critical; the
                # primary MongoDB delete must proceed. Same rationale as single delete.
                logger.warning("Failed to create outbox batch delete entry for user %s: %s", user_id, e)

        # Delete from MongoDB
        return await self._repository.delete_by_user(user_id)

    async def format_memories_for_context(
        self,
        memories: list[MemorySearchResult],
        max_tokens: int = 500,
        enable_contradiction_detection: bool = True,
    ) -> str:
        """Format memories for inclusion in agent context.

        Phase 4: Enhanced with evidence-based formatting, confidence scoring,
        and contradiction detection to reduce hallucinations.

        Args:
            memories: List of memories to format
            max_tokens: Approximate token limit
            enable_contradiction_detection: Detect and mark contradictions

        Returns:
            Formatted string for context injection with evidence blocks
        """
        if not memories:
            return ""

        # Phase 4: Convert to evidence format
        from app.domain.models.memory_evidence import MemoryEvidence

        evidence_list = []
        for result in memories:
            mem = result.memory
            evidence = MemoryEvidence(
                memory_id=mem.id,
                content=mem.content,
                source_type="user_knowledge",  # Could derive from collection
                retrieval_score=result.relevance_score,
                embedding_quality=mem.embedding_quality
                if hasattr(mem, "embedding_quality") and mem.embedding_quality
                else 0.8,
                timestamp=mem.created_at,
                session_id=mem.session_id if hasattr(mem, "session_id") else None,
                memory_type=mem.memory_type.value,
                importance=mem.importance.value,
            )
            evidence_list.append(evidence)

        # Phase 4: Detect contradictions
        if enable_contradiction_detection:
            try:
                from app.domain.services.retrieval.contradiction_resolver import get_contradiction_resolver

                resolver = get_contradiction_resolver(llm=self._llm)
                evidence_list = await resolver.detect_contradictions(evidence_list)
            except (ImportError, LLMException, IntegrationException, ValueError) as e:
                logger.debug("Contradiction detection failed: %s", e)

        # Phase 4: Filter rejected evidence
        evidence_list = [ev for ev in evidence_list if not ev.should_reject]

        if not evidence_list:
            return ""

        # Phase 4: Format as evidence blocks
        lines = ["## Relevant Memories (Evidence-Based)\n"]
        current_length = 0
        char_limit = max_tokens * 4

        for evidence in evidence_list:
            block = evidence.to_prompt_block(include_metadata=True)
            if not block:
                continue

            if current_length + len(block) > char_limit:
                break

            lines.append(block)
            lines.append("")  # Blank line between evidence blocks
            current_length += len(block)

        return "\n".join(lines)

    # Cross-session intelligence methods (Phase 5)

    async def find_similar_tasks(
        self,
        user_id: str,
        task_description: str,
        limit: int = 5,
    ) -> list[dict]:
        """Find past tasks similar to the current one.

        Searches the task_artifacts Qdrant collection for semantically
        similar past tasks, returning their outcomes and lessons learned.

        Args:
            user_id: User to scope results to
            task_description: Current task description for similarity matching
            limit: Maximum results

        Returns:
            List of similar task dicts with content_summary, success, and relevance_score
        """
        try:
            from app.domain.repositories.vector_repos import get_task_artifact_repository

            task_repo = get_task_artifact_repository()
            if not task_repo:
                return []

            embedding = await self._generate_embedding(task_description)

            return await task_repo.find_similar_tasks(
                user_id=user_id,
                query_vector=embedding,
                limit=limit,
                artifact_types=["task_outcome", "procedure"],
            )
        except Exception as e:
            logger.warning("Similar task retrieval failed: %s", e)
            return []

    async def store_task_artifact(
        self,
        user_id: str,
        session_id: str,
        task_description: str,
        result: str,
        success: bool,
        agent_role: str = "executor",
    ) -> None:
        """Store a task artifact for cross-session retrieval.

        Args:
            user_id: User who owns this artifact
            session_id: Session where the task was executed
            task_description: Description of the task
            result: Task result/outcome
            success: Whether the task succeeded
            agent_role: Role of the agent that executed this
        """
        try:
            import uuid

            from app.domain.repositories.vector_repos import get_task_artifact_repository

            task_repo = get_task_artifact_repository()
            if not task_repo:
                return

            embedding = await self._generate_embedding(f"{task_description}\n{result}")

            await task_repo.store_task_artifact(
                artifact_id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                embedding=embedding,
                artifact_type="task_outcome",
                agent_role=agent_role,
                success=success,
                content_summary=f"{task_description[:200]} → {result[:300]}",
            )
            logger.debug(f"Stored task artifact for session {session_id}")
        except Exception as e:
            logger.debug("Task artifact storage failed (non-critical): %s", e)

    async def get_error_context(
        self,
        user_id: str,
        tool_name: str,
        context: str,
        limit: int = 3,
    ) -> str:
        """Get historical error context for a tool.

        Searches past tool execution failures to provide
        proactive error avoidance guidance.

        Args:
            user_id: User scope
            tool_name: Tool being used
            context: Current task/tool context
            limit: Max results

        Returns:
            Formatted error context string
        """
        try:
            from app.domain.repositories.vector_repos import get_tool_log_repository

            tool_repo = get_tool_log_repository()
            if not tool_repo:
                return ""

            embedding = await self._generate_embedding(f"{tool_name}: {context}")

            results = await tool_repo.find_similar_tool_executions(
                user_id=user_id,
                query_vector=embedding,
                tool_name=tool_name,
                outcome="failure",
                limit=limit,
            )

            if not results:
                return ""

            lines = [f"Past {tool_name} failures (avoid repeating):"]
            for r in results:
                summary = r.get("input_summary", "")
                error = r.get("error_type", "unknown")
                lines.append(f"- {summary[:100]} (error: {error})")

            return "\n".join(lines)
        except Exception as e:
            logger.debug("Error context retrieval failed: %s", e)
            return ""

    async def store_session_summary(
        self,
        user_id: str,
        session_id: str,
        conversation: list[dict],
        outcome: str,
        success: bool,
    ) -> MemoryEntry:
        """Store compacted session summary as critical memory.

        Phase 5: Session summaries preserve long-session context and prevent
        context loss by capturing key decisions, outcomes, and lessons learned.

        Args:
            user_id: User who owns the session
            session_id: Session ID
            conversation: Full conversation history
            outcome: Summary of what was accomplished
            success: Whether session goals were achieved

        Returns:
            Created memory entry
        """
        # Generate summary using LLM
        summary_text = await self._generate_session_summary(conversation, outcome)

        # Store as CRITICAL importance
        return await self.store_memory(
            user_id=user_id,
            content=f"Session {session_id[:8]} summary:\n{summary_text}",
            memory_type=MemoryType.PROJECT_CONTEXT,
            importance=MemoryImportance.CRITICAL,
            source=MemorySource.SYSTEM,
            session_id=session_id,
            tags=["session_summary", "success" if success else "failure"],
            metadata={
                "outcome": outcome,
                "success": success,
                "message_count": len(conversation),
                "summary_timestamp": datetime.now(UTC).isoformat(),
            },
            generate_embedding=True,
        )

    async def _generate_session_summary(
        self,
        conversation: list[dict],
        outcome: str,
    ) -> str:
        """Generate session summary using LLM.

        Phase 5: LLM-based summarization extracts key information from
        long sessions for future retrieval.

        Args:
            conversation: Full conversation history
            outcome: Final outcome description

        Returns:
            Concise session summary (max 200 words)
        """
        if not self._llm:
            # Fallback: simple concatenation if no LLM available
            return f"Outcome: {outcome}\nMessages: {len(conversation)}"

        # Format conversation (last 20 messages to avoid overwhelming LLM)
        formatted = "\n".join(
            [f"{msg.get('role', 'unknown')}: {str(msg.get('content', ''))[:200]}" for msg in conversation[-20:]]
        )

        prompt = f"""Summarize this session into 3-5 bullet points capturing:
1. What the user requested
2. Key decisions and actions taken
3. Final outcome
4. Any important context for future sessions

Conversation:
{formatted}

Outcome: {outcome}

Provide a concise summary (max 200 words)."""

        try:
            response = await self._llm.ask(messages=[{"role": "user", "content": prompt}])
            return response.get("content", outcome)
        except Exception as e:
            logger.warning("Session summary generation failed: %s", e)
            return f"Outcome: {outcome}\nMessages: {len(conversation)}"

    # Private helper methods

    def _compute_hash(self, content: str) -> str:
        """Compute content hash for deduplication."""
        import hashlib

        normalized = " ".join(content.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text."""
        # Simple keyword extraction - could be enhanced with NLP
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())

        # Remove common stop words
        stop_words = {
            "the",
            "and",
            "for",
            "are",
            "but",
            "not",
            "you",
            "all",
            "can",
            "had",
            "her",
            "was",
            "one",
            "our",
            "out",
            "has",
            "have",
            "been",
            "would",
            "could",
            "should",
            "will",
            "with",
            "this",
            "that",
            "from",
            "they",
            "what",
            "which",
            "their",
        }

        keywords = [w for w in words if w not in stop_words]

        # Return unique keywords, limited
        return list(dict.fromkeys(keywords))[:20]

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate dense embedding vector for text.

        Uses dedicated embedding client (OpenAI-compatible) if available.
        Falls back to simple TF-IDF-like vectors for basic functionality.

        This is independent of the chat model provider (OpenAI/Anthropic/DeepSeek),
        allowing embeddings to always use OpenAI's API.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as list of floats
        """
        # Try using dedicated embedding client
        if self._embedding_client:
            try:
                # Truncate text to avoid token limits
                truncated = text[:8000]

                response = await self._embedding_client.embeddings.create(
                    model=self._embedding_model, input=truncated, encoding_format="float"
                )

                if response.data and len(response.data) > 0:
                    return response.data[0].embedding

            except (OpenAIAPIError, OpenAIConnectionError) as e:
                logger.warning("Embedding API failed, using fallback: %s", e)

        # Fallback: Simple hash-based embedding
        # Note: Uses 1536 dimensions to match vector store collection config
        return self._compute_simple_embedding(text, dim=1536)

    def _generate_sparse_vector(self, text: str) -> dict[str, float]:
        """Generate BM25 sparse vector for text.

        Phase 1: Uses self-hosted BM25 encoder for keyword search.

        Args:
            text: Text to generate sparse vector for

        Returns:
            Sparse vector as {str_index: score} dict with string keys
            (MongoDB requires string keys in documents)
        """
        from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

        encoder = get_bm25_encoder()
        # encode() lazy-fits BM25 on a small seed corpus when unfitted.
        raw = encoder.encode(text)
        # MongoDB requires string keys in documents - convert int keys to strings
        return {str(k): v for k, v in raw.items()}

    def _compute_simple_embedding(self, text: str, dim: int = 256) -> list[float]:
        """Compute a simple hash-based embedding for fallback.

        Creates a deterministic vector based on word hashing.
        Not as good as neural embeddings but provides basic similarity.

        Args:
            text: Text to embed
            dim: Embedding dimension

        Returns:
            Embedding vector
        """
        import hashlib
        import math

        # Initialize vector
        vector = [0.0] * dim

        # Tokenize
        words = re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())

        if not words:
            return vector

        # Hash each word to vector positions
        for word in words:
            # Hash word to get position and value
            h = hashlib.md5(word.encode(), usedforsecurity=False).hexdigest()

            # Use first part of hash for position
            pos = int(h[:8], 16) % dim

            # Use second part for value contribution
            val = (int(h[8:16], 16) % 1000) / 1000.0

            # Add to vector with TF-like weighting
            vector[pos] += val

        # Normalize vector to unit length
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    async def _llm_extract_memories(self, text: str) -> list[ExtractedMemory]:
        """Use LLM to extract memories from text."""
        prompt = f"""Extract memorable information from this conversation that should be remembered for future interactions.

Text:
{text[:2000]}

Extract:
1. User preferences (likes, dislikes, preferred ways of working)
2. Important facts about the user (job, location, projects)
3. Named entities (people, companies, tools mentioned)

Return as JSON array with objects containing:
- content: the memorable information
- type: preference|fact|entity
- importance: low|medium|high
- confidence: 0.0-1.0

Only extract genuinely useful information. Return empty array if nothing notable."""

        try:
            response = await self._llm.ask(
                messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
            )

            content = response.get("content", "[]")
            items = json.loads(content)

            if not isinstance(items, list):
                items = items.get("memories", [])

            extracted = []
            for item in items:
                mem_type = {
                    "preference": MemoryType.PREFERENCE,
                    "fact": MemoryType.FACT,
                    "entity": MemoryType.ENTITY,
                }.get(item.get("type", "fact"), MemoryType.FACT)

                importance = {
                    "low": MemoryImportance.LOW,
                    "medium": MemoryImportance.MEDIUM,
                    "high": MemoryImportance.HIGH,
                }.get(item.get("importance", "medium"), MemoryImportance.MEDIUM)

                extracted.append(
                    ExtractedMemory(
                        content=item.get("content", ""),
                        memory_type=mem_type,
                        importance=importance,
                        confidence=float(item.get("confidence", 0.7)),
                        reasoning="LLM extraction",
                    )
                )

            return extracted

        except LLMException as e:
            # LLMKeysExhaustedError inherits from LLMException — quiet log for key exhaustion
            from app.domain.exceptions.base import LLMKeysExhaustedError

            if isinstance(e, LLMKeysExhaustedError):
                logger.debug("LLM extraction skipped (keys exhausted): %s", e)
            else:
                logger.warning("LLM extraction failed: %s", e)
            return []
        except (IntegrationException, OpenAIAPIError, OpenAIConnectionError, json.JSONDecodeError) as e:
            logger.warning("LLM extraction failed: %s", e)
            return []

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Compute simple text similarity (Jaccard)."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _merge_content(self, memories: list[MemoryEntry]) -> str:
        """Merge content from multiple memories."""
        # Simple merge - could be enhanced with LLM summarization
        contents = [m.content for m in memories]
        unique_contents = list(dict.fromkeys(contents))
        return " | ".join(unique_contents[:3])  # Limit to 3 unique items


# =============================================================================
# In-Session Context Engineering (Phase 4)
# =============================================================================

SUMMARIZE_CONTEXT_PROMPT = """Summarize the following conversation segment into concise context that preserves:
1. Key decisions made
2. Important results obtained
3. Current state of the task
4. Any critical information for continuing

Conversation segment:
{conversation}

Provide a concise summary (max 500 words) that captures essential context."""


RELEVANCE_PROMPT = """Given the upcoming task step and historical context chunks, identify which are most relevant.

## Upcoming Step:
{step_description}

## Context Chunks:
{chunks}

Return JSON: {{"relevant": [0, 2, ...]}} - indices of relevant chunks only."""


@dataclass
class ContextChunk:
    """A chunk of summarized context from conversation history."""

    id: str
    summary: str
    message_range: tuple  # (start_idx, end_idx)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    token_estimate: int = 0
    relevance_tags: list[str] = field(default_factory=list)


@dataclass
class ContextServiceConfig:
    """Configuration for in-session context service."""

    enabled: bool = True
    auto_summarize_threshold: int = 20  # Messages before summarization
    summarize_after_steps: int = 3  # Steps between summarizations
    max_injected_tokens: int = 2000  # Max tokens to inject
    max_chunks_to_retrieve: int = 3  # Max context chunks to retrieve
    use_semantic_retrieval: bool = True  # Use LLM for relevance
    fallback_to_recent: bool = True  # Fall back to recent context


class ContextEngineeringService:
    """Service for in-session context management and engineering.

    Provides within a single session:
    1. Automatic summarization of conversation history
    2. RAG-based retrieval of relevant past context
    3. Selective context injection for upcoming steps

    This is Phase 4: Dynamic Context Engineering for improved
    memory management in long-running tasks.
    """

    def __init__(self, llm: LLM | None = None, config: ContextServiceConfig | None = None):
        """Initialize the context engineering service.

        Args:
            llm: Language model for summarization and retrieval
            config: Service configuration
        """
        self._llm = llm
        self.config = config or ContextServiceConfig()

        # Context storage
        self._context_chunks: list[ContextChunk] = []
        self._chunk_counter = 0

        # Tracking
        self._messages_since_summary = 0
        self._steps_since_summary = 0

    def should_summarize(self, memory: "Memory") -> bool:
        """Check if memory should be summarized.

        Args:
            memory: Current memory state

        Returns:
            True if summarization should be triggered
        """
        if not self.config.enabled:
            return False

        if self._messages_since_summary >= self.config.auto_summarize_threshold:
            return True

        if self._steps_since_summary >= self.config.summarize_after_steps:
            return True

        # Check token pressure
        estimated_tokens = memory.estimate_tokens()
        return estimated_tokens > memory.config.auto_compact_token_threshold * 0.7

    async def summarize_and_store(self, memory: "Memory", preserve_recent: int = 10) -> ContextChunk | None:
        """Summarize older messages and store as context chunk.

        Args:
            memory: Memory to summarize from
            preserve_recent: Number of recent messages to preserve

        Returns:
            Created ContextChunk or None if summarization failed
        """

        messages = memory.get_messages()

        if len(messages) <= preserve_recent:
            return None

        # Get messages to summarize
        summarize_start = 1 if messages[0].get("role") == "system" else 0
        summarize_end = len(messages) - preserve_recent

        if summarize_end <= summarize_start:
            return None

        messages_to_summarize = messages[summarize_start:summarize_end]

        if not messages_to_summarize:
            return None

        # Format for summarization
        conversation_text = self._format_messages(messages_to_summarize)

        try:
            summary = await self._generate_summary(conversation_text)

            if not summary:
                return None

            chunk = ContextChunk(
                id=f"ctx_{self._chunk_counter}",
                summary=summary,
                message_range=(summarize_start, summarize_end),
                token_estimate=len(summary) // 4,
                relevance_tags=self._extract_tags(summary),
            )

            self._context_chunks.append(chunk)
            self._chunk_counter += 1

            # Reset tracking
            self._messages_since_summary = 0
            self._steps_since_summary = 0

            logger.info(f"Created context chunk {chunk.id} from messages {summarize_start}-{summarize_end}")

            return chunk

        except (LLMException, IntegrationException, OpenAIAPIError, OpenAIConnectionError) as e:
            logger.error("Summarization failed: %s", e)
            return None

    async def get_relevant_context(self, step_description: str, max_tokens: int | None = None) -> str:
        """Retrieve relevant context for an upcoming step.

        Args:
            step_description: Description of the upcoming step
            max_tokens: Maximum tokens to return

        Returns:
            Relevant context string
        """
        max_tokens = max_tokens or self.config.max_injected_tokens

        if not self._context_chunks:
            return ""

        if self.config.use_semantic_retrieval and self._llm:
            try:
                relevant_chunks = await self._semantic_retrieve(step_description, self.config.max_chunks_to_retrieve)
            except (
                LLMException,
                IntegrationException,
                OpenAIAPIError,
                OpenAIConnectionError,
                json.JSONDecodeError,
            ) as e:
                logger.warning("Semantic retrieval failed: %s", e)
                if self.config.fallback_to_recent:
                    relevant_chunks = self._get_recent_chunks(self.config.max_chunks_to_retrieve)
                else:
                    relevant_chunks = []
        else:
            relevant_chunks = self._get_recent_chunks(self.config.max_chunks_to_retrieve)

        if not relevant_chunks:
            return ""

        # Build context string within budget
        context_parts = []
        current_tokens = 0

        for chunk in relevant_chunks:
            if current_tokens + chunk.token_estimate > max_tokens:
                break
            context_parts.append(f"[Earlier context]\n{chunk.summary}")
            current_tokens += chunk.token_estimate

        return "\n\n".join(context_parts)

    def get_memory_budget(self, pressure_signal: float) -> int:
        """Compute memory token budget based on context pressure.

        Phase 5: Pressure-aware budgeting scales memory injection dynamically
        to prevent context window overflow in long sessions.

        Args:
            pressure_signal: 0.0-1.0, where 1.0 = at context limit

        Returns:
            Token budget for memory injection
        """
        base_budget = self.config.max_injected_tokens  # e.g., 2000

        if pressure_signal < 0.5:
            # Plenty of space: use full budget
            return base_budget
        if pressure_signal < 0.7:
            # Moderate pressure: reduce to 75%
            return int(base_budget * 0.75)
        if pressure_signal < 0.85:
            # High pressure: reduce to 50%
            return int(base_budget * 0.50)
        # Critical pressure: minimal memories only
        return int(base_budget * 0.25)

    async def inject_context_adaptive(
        self,
        memory: "Memory",
        step_description: str,
        pressure_signal: float,
    ) -> bool:
        """Inject context with pressure-aware budgeting.

        Phase 5: Adaptive injection scales memory budget based on token pressure
        to maintain coherence while preventing context overflow.

        Args:
            memory: Memory to inject into
            step_description: Description of the upcoming step
            pressure_signal: 0.0-1.0 context pressure (current_tokens / max_tokens)

        Returns:
            True if context was injected
        """
        if not self.config.enabled:
            return False

        # Compute dynamic budget
        budget = self.get_memory_budget(pressure_signal)

        # Retrieve relevant context within budget
        relevant_context = await self.get_relevant_context(
            step_description,
            max_tokens=budget,
        )

        if not relevant_context:
            return False

        # Inject into memory
        context_message = {
            "role": "system",
            "content": f"Relevant context (budget: {budget} tokens, pressure: {pressure_signal:.2f}):\n\n{relevant_context}",
        }

        messages = memory.get_messages()
        if messages and messages[0].get("role") == "system":
            memory.messages.insert(1, context_message)
        else:
            memory.messages.insert(0, context_message)

        logger.debug(f"Injected context with {budget} token budget (pressure: {pressure_signal:.2f})")
        return True

    async def inject_context(self, memory: "Memory", step_description: str) -> bool:
        """Inject relevant context into memory for upcoming step.

        Args:
            memory: Memory to inject into
            step_description: Description of the upcoming step

        Returns:
            True if context was injected
        """
        if not self.config.enabled:
            return False

        relevant_context = await self.get_relevant_context(step_description)

        if not relevant_context:
            return False

        context_message = {"role": "system", "content": f"Relevant context from earlier:\n\n{relevant_context}"}

        messages = memory.get_messages()
        if messages and messages[0].get("role") == "system":
            memory.messages.insert(1, context_message)
        else:
            memory.messages.insert(0, context_message)

        logger.debug("Injected relevant context into memory")
        return True

    def record_step_completed(self) -> None:
        """Record step completion for trigger tracking."""
        self._steps_since_summary += 1

    def record_messages_added(self, count: int) -> None:
        """Record messages added for trigger tracking."""
        self._messages_since_summary += count

    def _format_messages(self, messages: list[dict[str, Any]]) -> str:
        """Format messages for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role.upper()}: {content}")
        return "\n\n".join(lines)

    async def _generate_summary(self, conversation: str) -> str | None:
        """Generate summary using LLM."""
        if not self._llm:
            return None

        prompt = SUMMARIZE_CONTEXT_PROMPT.format(conversation=conversation)

        response = await self._llm.ask(messages=[{"role": "user", "content": prompt}])

        return response.get("content", "")

    async def _semantic_retrieve(self, step_description: str, max_chunks: int) -> list[ContextChunk]:
        """Retrieve chunks using semantic relevance."""
        if not self._context_chunks or not self._llm:
            return []

        chunk_summaries = []
        for i, chunk in enumerate(self._context_chunks):
            chunk_summaries.append(f"{i}. {chunk.summary[:200]}...")

        prompt = RELEVANCE_PROMPT.format(step_description=step_description, chunks="\n".join(chunk_summaries))

        response = await self._llm.ask(
            messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"}
        )

        content = response.get("content", "{}")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError, ValueError):
            return self._get_recent_chunks(max_chunks)

        relevant_indices = parsed.get("relevant", [])

        return [
            self._context_chunks[idx] for idx in relevant_indices[:max_chunks] if 0 <= idx < len(self._context_chunks)
        ]

    def _get_recent_chunks(self, count: int) -> list[ContextChunk]:
        """Get most recent context chunks."""
        return self._context_chunks[-count:] if self._context_chunks else []

    def _extract_tags(self, summary: str) -> list[str]:
        """Extract relevance tags from summary."""
        keywords = []
        common = [
            "search",
            "file",
            "browser",
            "create",
            "update",
            "delete",
            "error",
            "success",
            "result",
            "data",
            "api",
            "code",
        ]
        summary_lower = summary.lower()
        keywords = [kw for kw in common if kw in summary_lower]
        return keywords[:5]

    def get_stats(self) -> dict[str, Any]:
        """Get context engineering statistics."""
        return {
            "context_chunks": len(self._context_chunks),
            "total_chunk_tokens": sum(c.token_estimate for c in self._context_chunks),
            "messages_since_summary": self._messages_since_summary,
            "steps_since_summary": self._steps_since_summary,
        }

    def reset(self) -> None:
        """Reset service state."""
        self._context_chunks = []
        self._chunk_counter = 0
        self._messages_since_summary = 0
        self._steps_since_summary = 0
