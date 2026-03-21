"""Continuous Conversational Context Storage Service.

Real-time vectorization and retrieval of conversation turns during active sessions.
Stores each meaningful event (user message, assistant response, tool result, step
completion) in Qdrant with hybrid dense+sparse vectors for semantic retrieval.

Three-phase retrieval strategy:
1. Sliding window: Recent N turns (always included, no embedding needed)
2. Semantic intra-session: Top-K from older turns in current session (hybrid RRF)
3. Cross-session recall: Top-K from past sessions by same user

Architecture:
- Buffered batch flush: accumulate N turns, then one embed_batch() call
- Fire-and-forget writes: never block the SSE event stream
- Non-propagating errors: embedding/Qdrant failures are logged, never raised
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.prometheus_metrics import (
    conversation_context_embed_errors,
    conversation_context_flush_duration,
    conversation_context_retrieval_duration,
    conversation_context_turns_stored,
)
from app.domain.models.conversation_context import (
    ConversationContext,
    ConversationTurn,
    TurnEventType,
    TurnRole,
)

if TYPE_CHECKING:
    from app.domain.external.embedding import EmbeddingPort
    from app.domain.models.conversation_context import (
        ConversationContextResult,
    )
    from app.domain.models.event import (
        BaseEvent,
    )
    from app.domain.repositories.conversation_context_repository import (
        ConversationContextRepository,
    )

logger = logging.getLogger(__name__)

# Stop-words excluded from topic-coherence keyword extraction
_STOP_WORDS: frozenset[str] = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "and",
        "or",
        "but",
        "not",
        "no",
        "nor",
        "so",
        "yet",
        "for",
        "of",
        "in",
        "on",
        "at",
        "to",
        "from",
        "by",
        "with",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "it",
        "its",
        "they",
        "them",
        "their",
    ]
)


def _extract_keywords(text: str, min_length: int = 3) -> set[str]:
    """Extract meaningful lowercase keywords from text, excluding stop-words."""
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    return {t for t in tokens if len(t) >= min_length and t not in _STOP_WORDS}


def _filter_by_topic_coherence(
    query: str,
    turns: list[ConversationContextResult],
    min_overlap: int = 2,
) -> list[ConversationContextResult]:
    """Drop cross-session turns that share fewer than min_overlap keywords with query.

    This prevents embedding-similar but topically unrelated content (e.g., a discussion
    about 'qwen3 model benefits' appearing in a query about 'ashwagandha health benefits')
    from leaking across sessions. Embedding models measure structural similarity, not
    topical coherence — this keyword gate adds a lightweight topical filter.
    """
    if not turns:
        return turns

    query_keywords = _extract_keywords(query)
    if not query_keywords:
        return turns  # Can't filter if no keywords extracted

    filtered: list[ConversationContextResult] = []
    for turn in turns:
        turn_keywords = _extract_keywords(turn.content)
        overlap = query_keywords & turn_keywords
        if len(overlap) >= min_overlap:
            filtered.append(turn)
        else:
            logger.debug(
                "Cross-session turn dropped (low topic coherence): overlap=%d keywords=%s",
                len(overlap),
                overlap,
            )
    return filtered


def _content_hash(content: str) -> str:
    """Generate a short SHA256 hash for deduplication."""
    return hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]


class ConversationContextService:
    """Real-time conversation context vectorization and retrieval.

    Responsibilities:
    1. Buffer conversation turns from SSE events
    2. Batch-embed and store to Qdrant (non-blocking)
    3. Retrieve relevant context before each agent step
    """

    def __init__(
        self,
        repository: ConversationContextRepository,
        embedding_client: EmbeddingPort | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client
        self._settings = get_settings()

        # Buffer for accumulating turns before batch flush
        self._buffer: list[ConversationTurn] = []
        self._buffer_lock = asyncio.Lock()
        self._seen_hashes: set[str] = set()  # session-scoped dedup

        # Flush timer handle
        self._flush_timer: asyncio.TimerHandle | None = None

        # Session-scoped turn counter (set externally per session)
        self._turn_counter: int = 0

    @property
    def _buffer_size(self) -> int:
        return self._settings.conversation_context_buffer_size

    @property
    def _flush_interval(self) -> float:
        return self._settings.conversation_context_flush_interval_seconds

    @property
    def _min_content_length(self) -> int:
        return self._settings.conversation_context_min_content_length

    @property
    def _sliding_window_size(self) -> int:
        return self._settings.conversation_context_sliding_window

    @property
    def _semantic_top_k(self) -> int:
        return self._settings.conversation_context_semantic_top_k

    @property
    def _cross_session_top_k(self) -> int:
        return self._settings.conversation_context_cross_session_top_k

    @property
    def _cross_session_min_score(self) -> float:
        return self._settings.conversation_context_cross_session_min_score

    @property
    def _retrieval_timeout(self) -> float:
        return self._settings.conversation_context_retrieval_timeout_seconds

    # ------------------------------------------------------------------ #
    # Turn recording (non-blocking)
    # ------------------------------------------------------------------ #

    async def record_turn(self, turn: ConversationTurn) -> None:
        """Buffer a conversation turn for vectorization.

        Non-blocking: adds to internal buffer and triggers flush if threshold met.
        """
        # Content length filter
        if len(turn.content) < self._min_content_length:
            return

        # Deduplication (same content in same session)
        dedup_key = f"{turn.session_id}:{turn.content_hash}"
        if dedup_key in self._seen_hashes:
            logger.debug("Skipping duplicate turn: %s", dedup_key[:32])
            return
        self._seen_hashes.add(dedup_key)

        async with self._buffer_lock:
            self._buffer.append(turn)
            buffer_len = len(self._buffer)

        # Trigger flush if buffer threshold met
        if buffer_len >= self._buffer_size:
            _task = asyncio.create_task(self._flush_buffer())  # noqa: RUF006 — fire-and-forget by design
        else:
            # Reset flush timer
            self._reset_flush_timer()

    def _reset_flush_timer(self) -> None:
        """Reset the periodic flush timer."""
        if self._flush_timer is not None:
            self._flush_timer.cancel()

        loop = asyncio.get_event_loop()
        self._flush_timer = loop.call_later(
            self._flush_interval,
            lambda: asyncio.create_task(self._flush_buffer()),
        )

    async def _flush_buffer(self) -> None:
        """Embed and store buffered turns to Qdrant.

        Called when buffer_size reached or flush_interval elapsed.
        Uses embed_batch for efficiency. Errors are caught and metricked.
        """
        # Cancel pending timer
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

        # Take snapshot — keep buffer intact until success (atomic flush)
        async with self._buffer_lock:
            if not self._buffer:
                return
            turns = list(self._buffer)

        start_time = time.time()
        try:
            from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

            if self._embedding_client is None:
                logger.debug("No embedding client injected; skipping flush")
                return

            bm25_encoder = get_bm25_encoder()

            # Batch embed all turn contents
            contents = [t.content[:8000] for t in turns]  # Truncate for embedding
            dense_vectors = await self._embedding_client.embed_batch(contents)

            # Generate sparse vectors
            sparse_vectors: list[dict[int, float]] = []
            for content in contents:
                try:
                    sparse = bm25_encoder.encode(content)
                    sparse_vectors.append(sparse)
                except Exception:
                    sparse_vectors.append({})

            # Build upsert payload
            qdrant_turns: list[dict] = []
            for i, turn in enumerate(turns):
                qdrant_turns.append(
                    {
                        "point_id": turn.point_id,
                        "dense_vector": dense_vectors[i],
                        "sparse_vector": sparse_vectors[i] or None,
                        "payload": {
                            "user_id": turn.user_id,
                            "session_id": turn.session_id,
                            "role": turn.role.value,
                            "event_type": turn.event_type.value,
                            "content": turn.content[:2000],  # Compact payload storage
                            "content_hash": turn.content_hash,
                            "turn_number": turn.turn_number,
                            "event_id": turn.event_id,
                            "created_at": turn.created_at,
                            "step_id": turn.step_id,
                            "tool_name": turn.tool_name,
                        },
                    }
                )

            # Batch upsert to Qdrant
            await self._repository.upsert_batch(qdrant_turns)

            # Success — now clear the flushed turns from the buffer
            async with self._buffer_lock:
                # Only remove the turns we successfully flushed; new turns
                # may have been appended while we were awaiting the API.
                flushed_ids = {id(t) for t in turns}
                self._buffer = [t for t in self._buffer if id(t) not in flushed_ids]

            # Record metrics
            for turn in turns:
                conversation_context_turns_stored.inc(
                    {
                        "role": turn.role.value,
                        "event_type": turn.event_type.value,
                    }
                )

            duration = time.time() - start_time
            conversation_context_flush_duration.observe({}, duration)
            logger.debug("Flushed %d conversation turns to Qdrant in %.3fs", len(turns), duration)

            # Update BM25 corpus with flushed turn content (fire-and-forget)
            try:
                bm25_encoder.update_corpus(contents)
            except Exception:
                logger.debug("BM25 corpus update failed (non-critical)", exc_info=True)

        except Exception:
            conversation_context_embed_errors.inc({})
            logger.warning(
                "Failed to flush %d conversation turns (retained in buffer for retry)",
                len(turns),
                exc_info=True,
            )

    async def flush_remaining(self) -> None:
        """Force-flush any remaining buffered turns. Called on session end."""
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

        async with self._buffer_lock:
            has_items = bool(self._buffer)

        if has_items:
            await self._flush_buffer()

    # ------------------------------------------------------------------ #
    # Context retrieval (three-phase)
    # ------------------------------------------------------------------ #

    async def retrieve_context(
        self,
        user_id: str,
        session_id: str,
        query: str,
        current_turn_number: int,
    ) -> ConversationContext:
        """Retrieve relevant conversation context for step execution.

        Three-phase strategy:
        1. Sliding window: last N turns (no embedding, <5ms)
        2. Semantic intra-session: older turns with semantic match (~50-100ms)
        3. Cross-session recall: turns from past sessions (~20ms)

        Returns empty ConversationContext on timeout or error.
        """
        try:
            return await asyncio.wait_for(
                self._retrieve_context_impl(user_id, session_id, query, current_turn_number),
                timeout=self._retrieval_timeout,
            )
        except TimeoutError:
            logger.warning("Conversation context retrieval timed out (%.1fs)", self._retrieval_timeout)
            return ConversationContext()
        except Exception:
            logger.warning("Conversation context retrieval failed", exc_info=True)
            return ConversationContext()

    async def _retrieve_context_impl(
        self,
        user_id: str,
        session_id: str,
        query: str,
        current_turn_number: int,
    ) -> ConversationContext:
        """Internal retrieval implementation."""
        context = ConversationContext()

        # Phase A: Sliding window (no embedding needed, payload-only scroll)
        min_turn = max(0, current_turn_number - self._sliding_window_size)
        start_time = time.time()
        try:
            window_turns = await self._repository.get_recent_turns(
                session_id=session_id,
                min_turn_number=min_turn,
                limit=self._sliding_window_size,
            )
            context.sliding_window_turns = window_turns
        except Exception:
            logger.debug("Sliding window retrieval failed", exc_info=True)
        finally:
            conversation_context_retrieval_duration.observe(
                {"source": "sliding_window"},
                time.time() - start_time,
            )

        # Only do semantic search if there are older turns to search
        if current_turn_number <= self._sliding_window_size:
            return context

        # Generate embedding for semantic search (reused for both phases B and C)
        from app.domain.services.embeddings.bm25_encoder import get_bm25_encoder

        if self._embedding_client is None:
            logger.debug("No embedding client injected; skipping semantic search")
            return context

        dense_vector = await self._embedding_client.embed(query[:8000])

        sparse_vector: dict[int, float] = {}
        try:
            bm25_encoder = get_bm25_encoder()
            sparse_vector = bm25_encoder.encode(query)
        except Exception:
            logger.debug("BM25 sparse encoding failed, falling back to dense-only", exc_info=True)

        # Exclude sliding window turn numbers from semantic search
        exclude_turns = [t.turn_number for t in context.sliding_window_turns]

        # Phase B: Semantic intra-session search
        start_time = time.time()
        try:
            semantic_turns = await self._repository.search_session_turns(
                session_id=session_id,
                dense_vector=dense_vector,
                sparse_vector=sparse_vector or None,
                limit=self._semantic_top_k,
                min_score=0.3,
                exclude_turn_numbers=exclude_turns,
            )
            context.semantic_turns = semantic_turns
        except Exception:
            logger.debug("Intra-session semantic search failed", exc_info=True)
        finally:
            conversation_context_retrieval_duration.observe(
                {"source": "intra_session"},
                time.time() - start_time,
            )

        # Phase C: Cross-session recall (reuse same embedding)
        # NOTE: Disabled by default (cross_session_top_k=0) to prevent context
        # leakage between unrelated sessions. When enabled, a topic-coherence
        # filter ensures only genuinely related cross-session turns are injected.
        if self._cross_session_top_k > 0:
            start_time = time.time()
            try:
                cross_turns = await self._repository.search_cross_session(
                    user_id=user_id,
                    exclude_session_id=session_id,
                    dense_vector=dense_vector,
                    sparse_vector=sparse_vector or None,
                    limit=self._cross_session_top_k,
                    min_score=self._cross_session_min_score,
                )
                # Topic-coherence filter: drop results with no keyword overlap
                cross_turns = _filter_by_topic_coherence(query, cross_turns)
                context.cross_session_turns = cross_turns
            except Exception:
                logger.debug("Cross-session search failed", exc_info=True)
            finally:
                conversation_context_retrieval_duration.observe(
                    {"source": "cross_session"},
                    time.time() - start_time,
                )

        return context

    # ------------------------------------------------------------------ #
    # Event-to-turn extraction
    # ------------------------------------------------------------------ #

    def extract_turn_from_event(
        self,
        event: BaseEvent,
        session_id: str,
        user_id: str,
        turn_number: int,
    ) -> ConversationTurn | None:
        """Convert an AgentEvent to a ConversationTurn if it contains meaningful content.

        Returns None for events that should not be stored (partial streams, UI-only events).
        """
        from app.domain.models.event import (
            ComprehensionEvent,
            ErrorEvent,
            MessageEvent,
            ModeChangeEvent,
            PlanEvent,
            PlanStatus,
            ReflectionEvent,
            ReportEvent,
            StepEvent,
            StepStatus,
            TaskRecreationEvent,
            ThoughtEvent,
            ToolEvent,
            ToolStatus,
            VerificationEvent,
        )

        content: str | None = None
        role: TurnRole = TurnRole.ASSISTANT
        event_type: TurnEventType = TurnEventType.MESSAGE
        step_id: str | None = None
        tool_name: str | None = None

        match event:
            case MessageEvent():
                content = event.message
                role = TurnRole.USER if event.role == "user" else TurnRole.ASSISTANT
                event_type = TurnEventType.MESSAGE

            case ToolEvent():
                # Only store completed tool results, not invocations
                if event.status != ToolStatus.CALLED:
                    return None
                tool_name = getattr(event, "tool_name", None) or getattr(event, "function_name", None) or "unknown"
                result_str = str(getattr(event, "function_result", "") or "")[:500]
                content = f"{tool_name}: {result_str}"
                role = TurnRole.TOOL_SUMMARY
                event_type = TurnEventType.TOOL_RESULT

            case StepEvent():
                # Only store completed steps
                if event.status != StepStatus.COMPLETED:
                    return None
                step_desc = event.step.description if event.step else ""
                step_result = str(getattr(event.step, "result", "") or "")[:500]
                content = f"Step: {step_desc}. Result: {step_result}"
                role = TurnRole.STEP_SUMMARY
                event_type = TurnEventType.STEP_COMPLETION
                step_id = getattr(event, "step_id", None) or getattr(event, "id", None)

            case ReportEvent():
                title = getattr(event, "title", "") or ""
                report_content = getattr(event, "content", "") or ""
                content = f"{title}\n{report_content}"[:2000]
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.REPORT

            case ErrorEvent():
                error_msg = getattr(event, "error", "") or ""
                if error_msg:
                    content = f"Error: {error_msg}"
                    role = TurnRole.ASSISTANT
                    event_type = TurnEventType.ERROR

            case PlanEvent():
                # Only store the initial plan creation, not updates
                if event.status != PlanStatus.CREATED:
                    return None
                title = event.plan.title or ""
                steps = event.plan.steps or []
                step_lines = "\n".join(f"- {s.description}" for s in steps)
                content = f"Plan: {title}\nSteps:\n{step_lines}"
                role = TurnRole.PLAN_SUMMARY
                event_type = TurnEventType.PLAN

            case ThoughtEvent():
                # Only store the final thought in a chain
                if not event.is_final:
                    return None
                thought_content = event.content or ""
                thought_type = event.thought_type or "thought"
                content = f"Thought ({thought_type}): {thought_content}"
                role = TurnRole.THOUGHT
                event_type = TurnEventType.THOUGHT

            case ReflectionEvent():
                summary = event.summary or event.decision or ""
                content = f"Reflection: {summary}"
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.REFLECTION

            case VerificationEvent():
                summary = event.summary or ""
                status_val = event.status.value if event.status else ""
                content = f"Verification ({status_val}): {summary}"
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.VERIFICATION

            case ComprehensionEvent():
                summary = event.summary or ""
                content = f"Task comprehension: {summary}"
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.COMPREHENSION

            case ModeChangeEvent():
                reason = event.reason or ""
                content = f"Mode changed to {event.mode}: {reason}"
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.MODE_CHANGE

            case TaskRecreationEvent():
                content = f"Task recreated: {event.reason}"
                role = TurnRole.ASSISTANT
                event_type = TurnEventType.TASK_RECREATION

            case _:
                return None

        if not content or len(content.strip()) < self._min_content_length:
            return None

        event_id = getattr(event, "id", None) or str(uuid.uuid4())

        return ConversationTurn(
            point_id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            role=role,
            event_type=event_type,
            content=content.strip(),
            turn_number=turn_number,
            event_id=str(event_id),
            created_at=int(time.time()),
            content_hash=_content_hash(content),
            step_id=str(step_id) if step_id else None,
            tool_name=tool_name,
        )

    def reset_session_state(self) -> None:
        """Reset session-scoped state for a new session."""
        self._seen_hashes.clear()
        self._turn_counter = 0
        # Don't clear buffer — flush_remaining should have been called
