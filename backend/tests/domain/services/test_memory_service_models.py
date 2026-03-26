"""Tests for memory service data models, enums, pure functions, and constants.

Covers:
- SyncState, MemoryType, MemoryImportance, MemorySource enums
- MemoryEntry, MemoryQuery, MemorySearchResult, MemoryBatch,
  MemoryStats, MemoryUpdate, ExtractedMemory Pydantic models
- ContextChunk, ContextServiceConfig dataclasses
- PREFERENCE_PATTERNS and FACT_PATTERNS regex constants
- Pure helper methods: _compute_hash, _extract_keywords,
  _compute_simple_embedding, _text_similarity, _merge_content
"""

import math
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.domain.models.long_term_memory import (
    ExtractedMemory,
    MemoryBatch,
    MemoryEntry,
    MemoryImportance,
    MemoryQuery,
    MemorySearchResult,
    MemorySource,
    MemoryStats,
    MemoryType,
    MemoryUpdate,
    SyncState,
)
from app.domain.services.memory_service import (
    FACT_PATTERNS,
    PREFERENCE_PATTERNS,
    ContextChunk,
    ContextServiceConfig,
    MemoryService,
)

# ---------------------------------------------------------------------------
# SyncState enum
# ---------------------------------------------------------------------------


class TestSyncState:
    def test_all_members_exist(self):
        members = {s.value for s in SyncState}
        assert members == {"pending", "synced", "failed", "dead_letter"}

    def test_is_str_enum(self):
        assert isinstance(SyncState.PENDING, str)
        assert SyncState.PENDING == "pending"

    def test_pending_value(self):
        assert SyncState.PENDING.value == "pending"

    def test_synced_value(self):
        assert SyncState.SYNCED.value == "synced"

    def test_failed_value(self):
        assert SyncState.FAILED.value == "failed"

    def test_dead_letter_value(self):
        assert SyncState.DEAD_LETTER.value == "dead_letter"

    def test_equality_with_string(self):
        assert SyncState.SYNCED == "synced"

    def test_lookup_by_value(self):
        assert SyncState("pending") is SyncState.PENDING

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            SyncState("unknown")


# ---------------------------------------------------------------------------
# MemoryType enum
# ---------------------------------------------------------------------------


class TestMemoryType:
    def test_all_members_exist(self):
        expected = {
            "fact",
            "preference",
            "entity",
            "task_outcome",
            "conversation",
            "procedure",
            "error_pattern",
            "project",
        }
        assert {m.value for m in MemoryType} == expected

    def test_is_str_enum(self):
        assert isinstance(MemoryType.FACT, str)

    def test_fact_value(self):
        assert MemoryType.FACT.value == "fact"

    def test_preference_value(self):
        assert MemoryType.PREFERENCE.value == "preference"

    def test_entity_value(self):
        assert MemoryType.ENTITY.value == "entity"

    def test_task_outcome_value(self):
        assert MemoryType.TASK_OUTCOME.value == "task_outcome"

    def test_conversation_value(self):
        assert MemoryType.CONVERSATION.value == "conversation"

    def test_procedure_value(self):
        assert MemoryType.PROCEDURE.value == "procedure"

    def test_error_pattern_value(self):
        assert MemoryType.ERROR_PATTERN.value == "error_pattern"

    def test_project_context_value(self):
        assert MemoryType.PROJECT_CONTEXT.value == "project"

    def test_equality_with_string(self):
        assert MemoryType.FACT == "fact"

    def test_lookup_by_value(self):
        assert MemoryType("preference") is MemoryType.PREFERENCE


# ---------------------------------------------------------------------------
# MemoryImportance enum
# ---------------------------------------------------------------------------


class TestMemoryImportance:
    def test_all_members_exist(self):
        assert {m.value for m in MemoryImportance} == {"critical", "high", "medium", "low"}

    def test_is_str_enum(self):
        assert isinstance(MemoryImportance.HIGH, str)

    def test_critical_value(self):
        assert MemoryImportance.CRITICAL.value == "critical"

    def test_high_value(self):
        assert MemoryImportance.HIGH.value == "high"

    def test_medium_value(self):
        assert MemoryImportance.MEDIUM.value == "medium"

    def test_low_value(self):
        assert MemoryImportance.LOW.value == "low"

    def test_lookup_by_value(self):
        assert MemoryImportance("low") is MemoryImportance.LOW

    def test_equality_with_string(self):
        assert MemoryImportance.MEDIUM == "medium"


# ---------------------------------------------------------------------------
# MemorySource enum
# ---------------------------------------------------------------------------


class TestMemorySource:
    def test_all_members_exist(self):
        expected = {"user_explicit", "user_inferred", "task_result", "system", "external"}
        assert {m.value for m in MemorySource} == expected

    def test_is_str_enum(self):
        assert isinstance(MemorySource.SYSTEM, str)

    def test_user_explicit_value(self):
        assert MemorySource.USER_EXPLICIT.value == "user_explicit"

    def test_user_inferred_value(self):
        assert MemorySource.USER_INFERRED.value == "user_inferred"

    def test_task_result_value(self):
        assert MemorySource.TASK_RESULT.value == "task_result"

    def test_system_value(self):
        assert MemorySource.SYSTEM.value == "system"

    def test_external_value(self):
        assert MemorySource.EXTERNAL.value == "external"

    def test_lookup_by_value(self):
        assert MemorySource("system") is MemorySource.SYSTEM


# ---------------------------------------------------------------------------
# MemoryEntry model
# ---------------------------------------------------------------------------


def _make_entry(**overrides) -> MemoryEntry:
    """Return a minimal valid MemoryEntry."""
    defaults = {
        "id": "mem-001",
        "user_id": "user-abc",
        "content": "User prefers dark mode",
        "memory_type": MemoryType.PREFERENCE,
    }
    defaults.update(overrides)
    return MemoryEntry(**defaults)


class TestMemoryEntry:
    def test_minimal_construction(self):
        entry = _make_entry()
        assert entry.id == "mem-001"
        assert entry.user_id == "user-abc"
        assert entry.content == "User prefers dark mode"
        assert entry.memory_type == MemoryType.PREFERENCE

    def test_default_importance_is_medium(self):
        entry = _make_entry()
        assert entry.importance == MemoryImportance.MEDIUM

    def test_default_source_is_system(self):
        entry = _make_entry()
        assert entry.source == MemorySource.SYSTEM

    def test_default_embedding_is_none(self):
        entry = _make_entry()
        assert entry.embedding is None

    def test_default_keywords_empty(self):
        entry = _make_entry()
        assert entry.keywords == []

    def test_default_related_memories_empty(self):
        entry = _make_entry()
        assert entry.related_memories == []

    def test_default_entities_empty(self):
        entry = _make_entry()
        assert entry.entities == []

    def test_default_tags_empty(self):
        entry = _make_entry()
        assert entry.tags == []

    def test_default_metadata_empty(self):
        entry = _make_entry()
        assert entry.metadata == {}

    def test_default_is_active_true(self):
        entry = _make_entry()
        assert entry.is_active is True

    def test_default_confidence_is_one(self):
        entry = _make_entry()
        assert entry.confidence == 1.0

    def test_default_access_count_zero(self):
        entry = _make_entry()
        assert entry.access_count == 0

    def test_default_sync_state_pending(self):
        entry = _make_entry()
        assert entry.sync_state == SyncState.PENDING

    def test_default_sync_attempts_zero(self):
        entry = _make_entry()
        assert entry.sync_attempts == 0

    def test_default_embedding_quality_one(self):
        entry = _make_entry()
        assert entry.embedding_quality == 1.0

    def test_default_embedding_model_none(self):
        entry = _make_entry()
        assert entry.embedding_model is None

    def test_default_embedding_provider_none(self):
        entry = _make_entry()
        assert entry.embedding_provider is None

    def test_confidence_ge_zero(self):
        with pytest.raises(ValidationError):
            _make_entry(confidence=-0.1)

    def test_confidence_le_one(self):
        with pytest.raises(ValidationError):
            _make_entry(confidence=1.1)

    def test_embedding_quality_ge_zero(self):
        with pytest.raises(ValidationError):
            _make_entry(embedding_quality=-0.5)

    def test_embedding_quality_le_one(self):
        with pytest.raises(ValidationError):
            _make_entry(embedding_quality=2.0)

    # --- field_validator: None importance coercion ---

    def test_none_importance_coerced_to_medium(self):
        entry = _make_entry(importance=None)
        assert entry.importance == MemoryImportance.MEDIUM

    def test_importance_string_accepted(self):
        entry = _make_entry(importance="high")
        assert entry.importance == MemoryImportance.HIGH

    def test_importance_enum_accepted(self):
        entry = _make_entry(importance=MemoryImportance.CRITICAL)
        assert entry.importance == MemoryImportance.CRITICAL

    # --- content_hash() ---

    def test_content_hash_returns_16_chars(self):
        entry = _make_entry()
        assert len(entry.content_hash()) == 16

    def test_content_hash_is_deterministic(self):
        entry = _make_entry()
        assert entry.content_hash() == entry.content_hash()

    def test_content_hash_differs_for_different_content(self):
        e1 = _make_entry(content="hello world")
        e2 = _make_entry(content="goodbye world")
        assert e1.content_hash() != e2.content_hash()

    def test_content_hash_hex_string(self):
        entry = _make_entry(content="test")
        h = entry.content_hash()
        int(h, 16)  # must parse as hex without error

    # --- is_expired() ---

    def test_is_expired_none_expires_at(self):
        entry = _make_entry()
        assert entry.is_expired() is False

    def test_is_expired_future_expires_at(self):
        future = datetime.now(UTC) + timedelta(days=7)
        entry = _make_entry(expires_at=future)
        assert entry.is_expired() is False

    def test_is_expired_past_expires_at(self):
        past = datetime.now(UTC) - timedelta(seconds=1)
        entry = _make_entry(expires_at=past)
        assert entry.is_expired() is True

    # --- record_access() ---

    def test_record_access_increments_count(self):
        entry = _make_entry()
        assert entry.access_count == 0
        entry.record_access()
        assert entry.access_count == 1
        entry.record_access()
        assert entry.access_count == 2

    def test_record_access_sets_last_accessed(self):
        entry = _make_entry()
        assert entry.last_accessed is None
        before = datetime.now(UTC)
        entry.record_access()
        assert entry.last_accessed is not None
        assert entry.last_accessed >= before

    def test_record_access_multiple_times_updates_timestamp(self):
        entry = _make_entry()
        entry.record_access()
        first = entry.last_accessed
        entry.record_access()
        assert entry.last_accessed >= first

    # --- embedding field ---

    def test_embedding_stored_correctly(self):
        emb = [0.1, 0.2, 0.3]
        entry = _make_entry(embedding=emb)
        assert entry.embedding == emb

    # --- created_at / updated_at defaults ---

    def test_created_at_default_is_utc(self):
        entry = _make_entry()
        assert entry.created_at.tzinfo is not None

    def test_updated_at_default_is_utc(self):
        entry = _make_entry()
        assert entry.updated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# MemoryQuery model
# ---------------------------------------------------------------------------


class TestMemoryQuery:
    def test_minimal_construction(self):
        q = MemoryQuery(user_id="user-001")
        assert q.user_id == "user-001"

    def test_default_limit(self):
        q = MemoryQuery(user_id="u")
        assert q.limit == 10

    def test_default_offset(self):
        q = MemoryQuery(user_id="u")
        assert q.offset == 0

    def test_default_min_relevance(self):
        q = MemoryQuery(user_id="u")
        assert q.min_relevance == 0.0

    def test_default_include_expired_false(self):
        q = MemoryQuery(user_id="u")
        assert q.include_expired is False

    def test_default_keywords_empty(self):
        q = MemoryQuery(user_id="u")
        assert q.keywords == []

    def test_default_memory_types_empty(self):
        q = MemoryQuery(user_id="u")
        assert q.memory_types == []

    def test_limit_lower_bound(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u", limit=0)

    def test_limit_upper_bound(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u", limit=101)

    def test_offset_non_negative(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u", offset=-1)

    def test_min_relevance_lower_bound(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u", min_relevance=-0.1)

    def test_min_relevance_upper_bound(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u", min_relevance=1.1)

    def test_memory_types_filter(self):
        q = MemoryQuery(user_id="u", memory_types=[MemoryType.FACT, MemoryType.ENTITY])
        assert MemoryType.FACT in q.memory_types

    def test_query_text_set(self):
        q = MemoryQuery(user_id="u", query_text="dark mode")
        assert q.query_text == "dark mode"

    def test_time_filters_accepted(self):
        now = datetime.now(UTC)
        q = MemoryQuery(user_id="u", created_after=now - timedelta(days=1), created_before=now)
        assert q.created_after < q.created_before


# ---------------------------------------------------------------------------
# MemorySearchResult model
# ---------------------------------------------------------------------------


class TestMemorySearchResult:
    def test_construction(self):
        entry = _make_entry()
        result = MemorySearchResult(memory=entry, relevance_score=0.85, match_type="semantic")
        assert result.relevance_score == 0.85
        assert result.match_type == "semantic"
        assert result.memory.id == "mem-001"

    def test_relevance_score_lower_bound(self):
        entry = _make_entry()
        with pytest.raises(ValidationError):
            MemorySearchResult(memory=entry, relevance_score=-0.1, match_type="semantic")

    def test_relevance_score_upper_bound(self):
        entry = _make_entry()
        with pytest.raises(ValidationError):
            MemorySearchResult(memory=entry, relevance_score=1.1, match_type="semantic")

    def test_relevance_score_boundary_zero(self):
        entry = _make_entry()
        result = MemorySearchResult(memory=entry, relevance_score=0.0, match_type="keyword")
        assert result.relevance_score == 0.0

    def test_relevance_score_boundary_one(self):
        entry = _make_entry()
        result = MemorySearchResult(memory=entry, relevance_score=1.0, match_type="exact")
        assert result.relevance_score == 1.0

    def test_match_type_values(self):
        entry = _make_entry()
        for match_type in ("semantic", "keyword", "exact"):
            r = MemorySearchResult(memory=entry, relevance_score=0.5, match_type=match_type)
            assert r.match_type == match_type


# ---------------------------------------------------------------------------
# MemoryBatch model
# ---------------------------------------------------------------------------


class TestMemoryBatch:
    def test_default_empty(self):
        batch = MemoryBatch()
        assert batch.memories == []
        assert batch.total_count == 0
        assert batch.has_more is False

    def test_construction_with_values(self):
        entries = [_make_entry(id=f"mem-{i}") for i in range(3)]
        batch = MemoryBatch(memories=entries, total_count=10, has_more=True)
        assert len(batch.memories) == 3
        assert batch.total_count == 10
        assert batch.has_more is True


# ---------------------------------------------------------------------------
# MemoryStats model
# ---------------------------------------------------------------------------


class TestMemoryStats:
    def test_default_counts_zero(self):
        stats = MemoryStats(user_id="u")
        assert stats.total_memories == 0
        assert stats.active_memories == 0

    def test_default_dicts_empty(self):
        stats = MemoryStats(user_id="u")
        assert stats.by_type == {}
        assert stats.by_importance == {}

    def test_default_nulls(self):
        stats = MemoryStats(user_id="u")
        assert stats.oldest_memory is None
        assert stats.newest_memory is None
        assert stats.most_accessed is None

    def test_full_construction(self):
        now = datetime.now(UTC)
        stats = MemoryStats(
            user_id="user-x",
            total_memories=100,
            active_memories=95,
            by_type={"fact": 40, "preference": 55},
            by_importance={"high": 10, "medium": 85},
            oldest_memory=now - timedelta(days=30),
            newest_memory=now,
            most_accessed="mem-999",
        )
        assert stats.total_memories == 100
        assert stats.by_type["fact"] == 40
        assert stats.most_accessed == "mem-999"


# ---------------------------------------------------------------------------
# MemoryUpdate model
# ---------------------------------------------------------------------------


class TestMemoryUpdate:
    def test_all_fields_default_none(self):
        update = MemoryUpdate()
        assert update.content is None
        assert update.importance is None
        assert update.tags is None
        assert update.metadata is None
        assert update.is_active is None
        assert update.confidence is None
        assert update.expires_at is None
        assert update.sync_state is None
        assert update.sync_attempts is None
        assert update.last_sync_attempt is None
        assert update.sync_error is None

    def test_partial_update(self):
        update = MemoryUpdate(importance=MemoryImportance.HIGH, tags=["python", "async"])
        assert update.importance == MemoryImportance.HIGH
        assert update.tags == ["python", "async"]
        assert update.content is None

    def test_sync_state_update(self):
        now = datetime.now(UTC)
        update = MemoryUpdate(
            sync_state="synced",
            sync_attempts=2,
            last_sync_attempt=now,
            sync_error=None,
        )
        assert update.sync_state == "synced"
        assert update.sync_attempts == 2

    def test_is_active_update(self):
        update = MemoryUpdate(is_active=False)
        assert update.is_active is False


# ---------------------------------------------------------------------------
# ExtractedMemory model
# ---------------------------------------------------------------------------


class TestExtractedMemory:
    def test_minimal_construction(self):
        em = ExtractedMemory(content="User likes Python", memory_type=MemoryType.PREFERENCE)
        assert em.content == "User likes Python"
        assert em.memory_type == MemoryType.PREFERENCE

    def test_default_importance_medium(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.FACT)
        assert em.importance == MemoryImportance.MEDIUM

    def test_default_confidence(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.FACT)
        assert em.confidence == 0.8

    def test_default_entities_empty(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.ENTITY)
        assert em.entities == []

    def test_default_keywords_empty(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.FACT)
        assert em.keywords == []

    def test_default_source_text_none(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.FACT)
        assert em.source_text is None

    def test_default_reasoning_none(self):
        em = ExtractedMemory(content="x", memory_type=MemoryType.FACT)
        assert em.reasoning is None

    def test_full_construction(self):
        em = ExtractedMemory(
            content="User is a Python developer",
            memory_type=MemoryType.FACT,
            importance=MemoryImportance.HIGH,
            confidence=0.95,
            entities=["Python"],
            keywords=["developer"],
            source_text="I am a Python developer",
            reasoning="Fact extraction match",
        )
        assert em.importance == MemoryImportance.HIGH
        assert em.confidence == 0.95
        assert em.entities == ["Python"]
        assert em.reasoning == "Fact extraction match"


# ---------------------------------------------------------------------------
# ContextChunk dataclass
# ---------------------------------------------------------------------------


class TestContextChunk:
    def test_construction(self):
        chunk = ContextChunk(
            id="ctx_0",
            summary="User asked about Python async.",
            message_range=(0, 10),
        )
        assert chunk.id == "ctx_0"
        assert chunk.summary == "User asked about Python async."
        assert chunk.message_range == (0, 10)

    def test_default_token_estimate(self):
        chunk = ContextChunk(id="ctx_1", summary="s", message_range=(0, 5))
        assert chunk.token_estimate == 0

    def test_default_relevance_tags_empty(self):
        chunk = ContextChunk(id="ctx_1", summary="s", message_range=(0, 5))
        assert chunk.relevance_tags == []

    def test_created_at_auto_set(self):
        before = datetime.now(UTC)
        chunk = ContextChunk(id="ctx_2", summary="s", message_range=(0, 3))
        assert chunk.created_at >= before

    def test_relevance_tags_independent_across_instances(self):
        c1 = ContextChunk(id="a", summary="s", message_range=(0, 1))
        c2 = ContextChunk(id="b", summary="s", message_range=(0, 1))
        c1.relevance_tags.append("python")
        assert "python" not in c2.relevance_tags


# ---------------------------------------------------------------------------
# ContextServiceConfig dataclass
# ---------------------------------------------------------------------------


class TestContextServiceConfig:
    def test_defaults(self):
        cfg = ContextServiceConfig()
        assert cfg.enabled is True
        assert cfg.auto_summarize_threshold == 20
        assert cfg.summarize_after_steps == 3
        assert cfg.max_injected_tokens == 2000
        assert cfg.max_chunks_to_retrieve == 3
        assert cfg.use_semantic_retrieval is True
        assert cfg.fallback_to_recent is True

    def test_custom_values(self):
        cfg = ContextServiceConfig(
            enabled=False,
            auto_summarize_threshold=50,
            max_injected_tokens=4000,
        )
        assert cfg.enabled is False
        assert cfg.auto_summarize_threshold == 50
        assert cfg.max_injected_tokens == 4000

    def test_independent_instances(self):
        cfg1 = ContextServiceConfig()
        cfg2 = ContextServiceConfig(enabled=False)
        assert cfg1.enabled is True
        assert cfg2.enabled is False


# ---------------------------------------------------------------------------
# PREFERENCE_PATTERNS constant
# ---------------------------------------------------------------------------


class TestPreferencePatterns:
    def test_is_list(self):
        assert isinstance(PREFERENCE_PATTERNS, list)

    def test_non_empty(self):
        assert len(PREFERENCE_PATTERNS) > 0

    def test_all_items_are_strings(self):
        for p in PREFERENCE_PATTERNS:
            assert isinstance(p, str)

    def test_all_compile_as_regex(self):
        for p in PREFERENCE_PATTERNS:
            re.compile(p)  # must not raise

    def test_matches_prefer_sentence(self):
        text = "I prefer dark mode interfaces"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_matches_like_sentence(self):
        text = "I like Python for backend development"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_matches_love_sentence(self):
        text = "I love using async programming"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_matches_hate_sentence(self):
        text = "I hate JavaScript callback hell"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_matches_always_sentence(self):
        text = "always use type hints in Python"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_matches_never_sentence(self):
        text = "never use global variables"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert matched

    def test_no_match_neutral_sentence(self):
        text = "The weather is nice today"
        matched = any(re.search(p, text) for p in PREFERENCE_PATTERNS)
        assert not matched


# ---------------------------------------------------------------------------
# FACT_PATTERNS constant
# ---------------------------------------------------------------------------


class TestFactPatterns:
    def test_is_list(self):
        assert isinstance(FACT_PATTERNS, list)

    def test_non_empty(self):
        assert len(FACT_PATTERNS) > 0

    def test_all_items_are_strings(self):
        for p in FACT_PATTERNS:
            assert isinstance(p, str)

    def test_all_compile_as_regex(self):
        for p in FACT_PATTERNS:
            re.compile(p)

    def test_matches_i_am_sentence(self):
        text = "I am a software engineer"
        matched = any(re.search(p, text) for p in FACT_PATTERNS)
        assert matched

    def test_matches_i_work_sentence(self):
        text = "I work at Acme Corp"
        matched = any(re.search(p, text) for p in FACT_PATTERNS)
        assert matched

    def test_matches_my_x_is_y_sentence(self):
        text = "My email is user@example.com"
        matched = any(re.search(p, text) for p in FACT_PATTERNS)
        assert matched

    def test_no_match_neutral(self):
        text = "The quick brown fox"
        matched = any(re.search(p, text) for p in FACT_PATTERNS)
        assert not matched


# ---------------------------------------------------------------------------
# MemoryService pure helper methods
# (instantiated with mocks to avoid DB / LLM connections)
# ---------------------------------------------------------------------------


def _make_service() -> MemoryService:
    """Build a MemoryService with all external deps mocked."""
    mock_repo = MagicMock()
    mock_settings = MagicMock()
    mock_settings.embedding_model = "text-embedding-3-small"
    mock_settings.embedding_api_key = None
    mock_settings.api_key = None
    mock_settings.embedding_api_base = None

    # get_settings is lazily imported inside __init__ from app.core.config
    with patch("app.core.config.get_settings", return_value=mock_settings):
        return MemoryService(repository=mock_repo)


class TestComputeHash:
    def setup_method(self):
        self.svc = _make_service()

    def test_returns_16_char_string(self):
        result = self.svc._compute_hash("hello world")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_deterministic(self):
        h1 = self.svc._compute_hash("same text")
        h2 = self.svc._compute_hash("same text")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = self.svc._compute_hash("content A")
        h2 = self.svc._compute_hash("content B")
        assert h1 != h2

    def test_case_insensitive_normalization(self):
        # normalizes to lower then hashes
        h1 = self.svc._compute_hash("Hello World")
        h2 = self.svc._compute_hash("hello world")
        assert h1 == h2

    def test_whitespace_normalization(self):
        h1 = self.svc._compute_hash("hello  world")
        h2 = self.svc._compute_hash("hello world")
        assert h1 == h2

    def test_leading_trailing_whitespace_normalized(self):
        h1 = self.svc._compute_hash("  hello world  ")
        h2 = self.svc._compute_hash("hello world")
        assert h1 == h2

    def test_empty_string_does_not_crash(self):
        result = self.svc._compute_hash("")
        assert len(result) == 16

    def test_result_is_hex(self):
        result = self.svc._compute_hash("test input")
        int(result, 16)  # must not raise


class TestExtractKeywords:
    def setup_method(self):
        self.svc = _make_service()

    def test_returns_list(self):
        result = self.svc._extract_keywords("Python is great for async programming")
        assert isinstance(result, list)

    def test_removes_stop_words(self):
        result = self.svc._extract_keywords("the and for are but")
        assert "the" not in result
        assert "and" not in result
        assert "for" not in result

    def test_words_at_least_3_chars(self):
        result = self.svc._extract_keywords("I go to do it")
        for word in result:
            assert len(word) >= 3

    def test_returns_lowercase(self):
        result = self.svc._extract_keywords("Python Django FastAPI")
        for word in result:
            assert word == word.lower()

    def test_uniqueness_preserves_order(self):
        result = self.svc._extract_keywords("python python python")
        assert result.count("python") == 1

    def test_max_20_keywords(self):
        long_text = " ".join(f"word{i}" for i in range(100))
        result = self.svc._extract_keywords(long_text)
        assert len(result) <= 20

    def test_empty_string_returns_empty(self):
        result = self.svc._extract_keywords("")
        assert result == []

    def test_real_sentence(self):
        result = self.svc._extract_keywords("User prefers dark mode interfaces for long coding sessions")
        assert "dark" in result
        assert "mode" in result
        assert "coding" in result

    def test_numbers_not_extracted(self):
        result = self.svc._extract_keywords("version 3 has 42 new features")
        # digits are excluded by \b[a-zA-Z]{3,}\b
        for word in result:
            assert word.isalpha()


class TestComputeSimpleEmbedding:
    def setup_method(self):
        self.svc = _make_service()

    def test_returns_list_of_floats(self):
        result = self.svc._compute_simple_embedding("hello world")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_default_dim_256(self):
        result = self.svc._compute_simple_embedding("hello")
        assert len(result) == 256

    def test_custom_dim(self):
        result = self.svc._compute_simple_embedding("hello", dim=64)
        assert len(result) == 64

    def test_dim_1536(self):
        result = self.svc._compute_simple_embedding("hello", dim=1536)
        assert len(result) == 1536

    def test_unit_vector(self):
        result = self.svc._compute_simple_embedding("machine learning embeddings")
        magnitude = math.sqrt(sum(v * v for v in result))
        assert abs(magnitude - 1.0) < 1e-6

    def test_empty_string_returns_zero_vector(self):
        result = self.svc._compute_simple_embedding("")
        assert all(v == 0.0 for v in result)

    def test_deterministic(self):
        r1 = self.svc._compute_simple_embedding("consistent text")
        r2 = self.svc._compute_simple_embedding("consistent text")
        assert r1 == r2

    def test_different_texts_produce_different_vectors(self):
        r1 = self.svc._compute_simple_embedding("apple juice smoothie")
        r2 = self.svc._compute_simple_embedding("quantum physics mechanics")
        assert r1 != r2

    def test_no_nan_values(self):
        result = self.svc._compute_simple_embedding("test")
        for v in result:
            assert not math.isnan(v)

    def test_values_bounded(self):
        result = self.svc._compute_simple_embedding("boundary check")
        for v in result:
            assert -1.0 <= v <= 1.0


class TestTextSimilarity:
    def setup_method(self):
        self.svc = _make_service()

    def test_identical_texts_return_one(self):
        score = self.svc._text_similarity("hello world", "hello world")
        assert score == 1.0

    def test_completely_different_texts(self):
        score = self.svc._text_similarity("apple pie", "quantum physics")
        assert score == 0.0

    def test_partial_overlap(self):
        score = self.svc._text_similarity("I like Python", "I like JavaScript")
        assert 0.0 < score < 1.0

    def test_empty_first_returns_zero(self):
        score = self.svc._text_similarity("", "hello world")
        assert score == 0.0

    def test_empty_second_returns_zero(self):
        score = self.svc._text_similarity("hello world", "")
        assert score == 0.0

    def test_both_empty_returns_zero(self):
        score = self.svc._text_similarity("", "")
        assert score == 0.0

    def test_score_in_range(self):
        score = self.svc._text_similarity("Python async programming", "async programming patterns")
        assert 0.0 <= score <= 1.0

    def test_symmetric(self):
        a = "machine learning models"
        b = "deep learning frameworks"
        assert self.svc._text_similarity(a, b) == self.svc._text_similarity(b, a)

    def test_superset_similarity(self):
        # "cat" vs "cat sat on the mat" — "cat" is a subset
        s1 = self.svc._text_similarity("cat", "cat sat on the mat")
        assert 0.0 < s1 <= 1.0


class TestMergeContent:
    def setup_method(self):
        self.svc = _make_service()

    def test_single_memory(self):
        entry = _make_entry(content="Python is fast")
        result = self.svc._merge_content([entry])
        assert "Python is fast" in result

    def test_two_different_memories(self):
        e1 = _make_entry(id="1", content="Python is fast")
        e2 = _make_entry(id="2", content="Python is readable")
        result = self.svc._merge_content([e1, e2])
        assert "Python is fast" in result
        assert "Python is readable" in result

    def test_separator_pipe(self):
        e1 = _make_entry(id="1", content="A")
        e2 = _make_entry(id="2", content="B")
        result = self.svc._merge_content([e1, e2])
        assert " | " in result

    def test_max_three_unique_contents(self):
        entries = [_make_entry(id=str(i), content=f"Content {i}") for i in range(5)]
        result = self.svc._merge_content(entries)
        # at most 3 pipe-joined sections
        parts = result.split(" | ")
        assert len(parts) <= 3

    def test_deduplicates_content(self):
        e1 = _make_entry(id="1", content="same content")
        e2 = _make_entry(id="2", content="same content")
        result = self.svc._merge_content([e1, e2])
        # after dedup, only one occurrence
        assert result.count("same content") == 1

    def test_empty_list_returns_empty_string(self):
        result = self.svc._merge_content([])
        assert result == ""
