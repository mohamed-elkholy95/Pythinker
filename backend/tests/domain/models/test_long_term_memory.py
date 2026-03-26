"""Tests for app.domain.models.long_term_memory — long-term memory models.

Covers: SyncState, MemoryType, MemoryImportance, MemorySource, MemoryEntry,
MemoryQuery, MemorySearchResult, MemoryBatch, MemoryStats, MemoryUpdate,
ExtractedMemory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------
class TestEnums:
    def test_sync_state_values(self):
        assert SyncState.PENDING == "pending"
        assert SyncState.SYNCED == "synced"
        assert SyncState.FAILED == "failed"
        assert SyncState.DEAD_LETTER == "dead_letter"

    def test_memory_type_values(self):
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
        actual = {m.value for m in MemoryType}
        assert actual == expected

    def test_memory_importance_values(self):
        expected = {"critical", "high", "medium", "low"}
        actual = {m.value for m in MemoryImportance}
        assert actual == expected

    def test_memory_source_values(self):
        expected = {"user_explicit", "user_inferred", "task_result", "system", "external"}
        actual = {m.value for m in MemorySource}
        assert actual == expected


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------
class TestMemoryEntry:
    def _make_entry(self, **kwargs) -> MemoryEntry:
        defaults = {
            "id": "mem-001",
            "user_id": "user-1",
            "content": "The user prefers dark mode",
            "memory_type": MemoryType.PREFERENCE,
        }
        defaults.update(kwargs)
        return MemoryEntry(**defaults)

    def test_minimal_creation(self):
        entry = self._make_entry()
        assert entry.id == "mem-001"
        assert entry.content == "The user prefers dark mode"
        assert entry.memory_type == MemoryType.PREFERENCE

    def test_defaults(self):
        entry = self._make_entry()
        assert entry.importance == MemoryImportance.MEDIUM
        assert entry.source == MemorySource.SYSTEM
        assert entry.embedding is None
        assert entry.keywords == []
        assert entry.session_id is None
        assert entry.related_memories == []
        assert entry.entities == []
        assert entry.tags == []
        assert entry.metadata == {}
        assert entry.is_active is True
        assert entry.confidence == 1.0
        assert entry.sync_state == SyncState.PENDING
        assert entry.sync_attempts == 0

    def test_importance_none_coerced_to_medium(self):
        entry = self._make_entry(importance=None)
        assert entry.importance == MemoryImportance.MEDIUM

    def test_content_hash_deterministic(self):
        entry1 = self._make_entry(content="hello world")
        entry2 = self._make_entry(content="hello world")
        assert entry1.content_hash() == entry2.content_hash()

    def test_content_hash_different_for_different_content(self):
        entry1 = self._make_entry(content="hello")
        entry2 = self._make_entry(content="world")
        assert entry1.content_hash() != entry2.content_hash()

    def test_content_hash_length(self):
        entry = self._make_entry()
        assert len(entry.content_hash()) == 16

    def test_is_expired_false_when_no_expiry(self):
        entry = self._make_entry()
        assert entry.is_expired() is False

    def test_is_expired_false_when_future(self):
        entry = self._make_entry(expires_at=datetime.now(UTC) + timedelta(days=1))
        assert entry.is_expired() is False

    def test_is_expired_true_when_past(self):
        entry = self._make_entry(expires_at=datetime.now(UTC) - timedelta(days=1))
        assert entry.is_expired() is True

    def test_record_access_increments_count(self):
        entry = self._make_entry()
        assert entry.access_count == 0
        entry.record_access()
        assert entry.access_count == 1
        assert entry.last_accessed is not None

    def test_record_access_updates_timestamp(self):
        entry = self._make_entry()
        entry.record_access()
        first_access = entry.last_accessed
        entry.record_access()
        assert entry.access_count == 2
        assert entry.last_accessed >= first_access

    def test_confidence_bounded(self):
        entry = self._make_entry(confidence=0.5)
        assert entry.confidence == 0.5

    def test_confidence_min_bound(self):
        with pytest.raises(ValidationError):
            self._make_entry(confidence=-0.1)

    def test_confidence_max_bound(self):
        with pytest.raises(ValidationError):
            self._make_entry(confidence=1.1)

    def test_embedding_quality_default(self):
        entry = self._make_entry()
        assert entry.embedding_quality == 1.0

    def test_with_embedding(self):
        entry = self._make_entry(embedding=[0.1, 0.2, 0.3])
        assert entry.embedding == [0.1, 0.2, 0.3]

    def test_sync_state_transitions(self):
        entry = self._make_entry(sync_state=SyncState.SYNCED)
        assert entry.sync_state == SyncState.SYNCED

    def test_serialization_round_trip(self):
        entry = self._make_entry(
            keywords=["dark", "mode"],
            entities=["UI"],
            tags=["prefs"],
        )
        data = entry.model_dump()
        restored = MemoryEntry(**data)
        assert restored.content == entry.content
        assert restored.keywords == entry.keywords


# ---------------------------------------------------------------------------
# MemoryQuery
# ---------------------------------------------------------------------------
class TestMemoryQuery:
    def test_minimal_query(self):
        q = MemoryQuery(user_id="u1")
        assert q.user_id == "u1"
        assert q.query_text is None
        assert q.limit == 10
        assert q.offset == 0

    def test_with_filters(self):
        q = MemoryQuery(
            user_id="u1",
            query_text="dark mode",
            memory_types=[MemoryType.PREFERENCE],
            min_importance=MemoryImportance.HIGH,
            keywords=["dark"],
            tag_filter=["prefs"],
        )
        assert q.query_text == "dark mode"
        assert q.memory_types == [MemoryType.PREFERENCE]
        assert q.min_importance == MemoryImportance.HIGH

    def test_limit_bounds(self):
        q = MemoryQuery(user_id="u1", limit=100)
        assert q.limit == 100

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u1", limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            MemoryQuery(user_id="u1", limit=101)

    def test_min_relevance_bounds(self):
        q = MemoryQuery(user_id="u1", min_relevance=0.5)
        assert q.min_relevance == 0.5

    def test_include_expired_default_false(self):
        q = MemoryQuery(user_id="u1")
        assert q.include_expired is False


# ---------------------------------------------------------------------------
# MemorySearchResult
# ---------------------------------------------------------------------------
class TestMemorySearchResult:
    def test_creation(self):
        entry = MemoryEntry(
            id="mem-1",
            user_id="u1",
            content="test",
            memory_type=MemoryType.FACT,
        )
        result = MemorySearchResult(memory=entry, relevance_score=0.85, match_type="semantic")
        assert result.relevance_score == 0.85
        assert result.match_type == "semantic"

    def test_relevance_score_bounds(self):
        entry = MemoryEntry(id="m1", user_id="u1", content="x", memory_type=MemoryType.FACT)
        with pytest.raises(ValidationError):
            MemorySearchResult(memory=entry, relevance_score=1.5, match_type="keyword")


# ---------------------------------------------------------------------------
# MemoryBatch
# ---------------------------------------------------------------------------
class TestMemoryBatch:
    def test_empty_batch(self):
        batch = MemoryBatch()
        assert batch.memories == []
        assert batch.total_count == 0
        assert batch.has_more is False

    def test_with_memories(self):
        entry = MemoryEntry(id="m1", user_id="u1", content="x", memory_type=MemoryType.FACT)
        batch = MemoryBatch(memories=[entry], total_count=10, has_more=True)
        assert len(batch.memories) == 1
        assert batch.has_more is True


# ---------------------------------------------------------------------------
# MemoryStats
# ---------------------------------------------------------------------------
class TestMemoryStats:
    def test_defaults(self):
        stats = MemoryStats(user_id="u1")
        assert stats.total_memories == 0
        assert stats.active_memories == 0
        assert stats.by_type == {}
        assert stats.oldest_memory is None


# ---------------------------------------------------------------------------
# MemoryUpdate
# ---------------------------------------------------------------------------
class TestMemoryUpdate:
    def test_empty_update(self):
        update = MemoryUpdate()
        assert update.content is None
        assert update.importance is None
        assert update.is_active is None

    def test_partial_update(self):
        update = MemoryUpdate(content="new content", importance=MemoryImportance.HIGH)
        assert update.content == "new content"
        assert update.importance == MemoryImportance.HIGH

    def test_sync_state_update(self):
        update = MemoryUpdate(sync_state="synced", sync_attempts=3)
        assert update.sync_state == "synced"
        assert update.sync_attempts == 3


# ---------------------------------------------------------------------------
# ExtractedMemory
# ---------------------------------------------------------------------------
class TestExtractedMemory:
    def test_minimal(self):
        em = ExtractedMemory(content="user likes Python", memory_type=MemoryType.PREFERENCE)
        assert em.content == "user likes Python"
        assert em.importance == MemoryImportance.MEDIUM
        assert em.confidence == 0.8

    def test_with_all_fields(self):
        em = ExtractedMemory(
            content="project uses FastAPI",
            memory_type=MemoryType.FACT,
            importance=MemoryImportance.HIGH,
            confidence=0.95,
            entities=["FastAPI"],
            keywords=["framework", "api"],
            source_text="We use FastAPI for the backend",
            reasoning="Mentioned explicitly by user",
        )
        assert em.entities == ["FastAPI"]
        assert em.reasoning == "Mentioned explicitly by user"

    def test_defaults(self):
        em = ExtractedMemory(content="test", memory_type=MemoryType.FACT)
        assert em.entities == []
        assert em.keywords == []
        assert em.source_text is None
        assert em.reasoning is None
