"""Tests for long-term memory domain models."""

from datetime import UTC, datetime, timedelta

import pytest

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


@pytest.mark.unit
class TestSyncStateEnum:
    def test_all_values(self) -> None:
        expected = {"pending", "synced", "failed", "dead_letter"}
        assert {s.value for s in SyncState} == expected


@pytest.mark.unit
class TestMemoryTypeEnum:
    def test_all_values(self) -> None:
        expected = {
            "fact", "preference", "entity", "task_outcome",
            "conversation", "procedure", "error_pattern", "project",
        }
        assert {t.value for t in MemoryType} == expected


@pytest.mark.unit
class TestMemoryImportanceEnum:
    def test_all_values(self) -> None:
        expected = {"critical", "high", "medium", "low"}
        assert {i.value for i in MemoryImportance} == expected


@pytest.mark.unit
class TestMemorySourceEnum:
    def test_all_values(self) -> None:
        expected = {"user_explicit", "user_inferred", "task_result", "system", "external"}
        assert {s.value for s in MemorySource} == expected


@pytest.mark.unit
class TestMemoryEntry:
    def _make_entry(self, **kwargs) -> MemoryEntry:
        defaults = {
            "id": "mem1",
            "user_id": "user1",
            "content": "Python is a programming language",
            "memory_type": MemoryType.FACT,
        }
        defaults.update(kwargs)
        return MemoryEntry(**defaults)

    def test_basic_construction(self) -> None:
        entry = self._make_entry()
        assert entry.id == "mem1"
        assert entry.content == "Python is a programming language"
        assert entry.memory_type == MemoryType.FACT
        assert entry.importance == MemoryImportance.MEDIUM

    def test_none_importance_coerced_to_medium(self) -> None:
        entry = self._make_entry(importance=None)
        assert entry.importance == MemoryImportance.MEDIUM

    def test_content_hash_deterministic(self) -> None:
        entry = self._make_entry(content="Hello world")
        h1 = entry.content_hash()
        h2 = entry.content_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_content_hash_different_for_different_content(self) -> None:
        e1 = self._make_entry(content="Hello")
        e2 = self._make_entry(content="World")
        assert e1.content_hash() != e2.content_hash()

    def test_is_expired_no_expiry(self) -> None:
        entry = self._make_entry()
        assert entry.is_expired() is False

    def test_is_expired_past(self) -> None:
        entry = self._make_entry(expires_at=datetime.now(UTC) - timedelta(hours=1))
        assert entry.is_expired() is True

    def test_is_expired_future(self) -> None:
        entry = self._make_entry(expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert entry.is_expired() is False

    def test_record_access(self) -> None:
        entry = self._make_entry()
        assert entry.access_count == 0
        entry.record_access()
        assert entry.access_count == 1
        assert entry.last_accessed is not None

    def test_defaults(self) -> None:
        entry = self._make_entry()
        assert entry.is_active is True
        assert entry.confidence == 1.0
        assert entry.sync_state == SyncState.PENDING
        assert entry.embedding is None
        assert entry.keywords == []
        assert entry.entities == []
        assert entry.tags == []

    def test_sync_state_tracking(self) -> None:
        entry = self._make_entry(sync_state=SyncState.SYNCED)
        assert entry.sync_state == SyncState.SYNCED
        assert entry.sync_attempts == 0


@pytest.mark.unit
class TestMemoryQuery:
    def test_minimal_query(self) -> None:
        q = MemoryQuery(user_id="user1")
        assert q.user_id == "user1"
        assert q.limit == 10
        assert q.offset == 0
        assert q.include_expired is False

    def test_with_text_search(self) -> None:
        q = MemoryQuery(user_id="user1", query_text="Python programming")
        assert q.query_text == "Python programming"

    def test_with_filters(self) -> None:
        q = MemoryQuery(
            user_id="user1",
            memory_types=[MemoryType.FACT, MemoryType.PREFERENCE],
            min_importance=MemoryImportance.HIGH,
            tag_filter=["python"],
        )
        assert len(q.memory_types) == 2
        assert q.min_importance == MemoryImportance.HIGH


@pytest.mark.unit
class TestMemorySearchResult:
    def test_construction(self) -> None:
        entry = MemoryEntry(
            id="m1", user_id="u1", content="test",
            memory_type=MemoryType.FACT,
        )
        result = MemorySearchResult(
            memory=entry, relevance_score=0.95, match_type="semantic",
        )
        assert result.relevance_score == 0.95
        assert result.match_type == "semantic"


@pytest.mark.unit
class TestMemoryBatch:
    def test_empty_batch(self) -> None:
        batch = MemoryBatch()
        assert batch.memories == []
        assert batch.total_count == 0
        assert batch.has_more is False


@pytest.mark.unit
class TestMemoryStats:
    def test_construction(self) -> None:
        stats = MemoryStats(user_id="user1", total_memories=100, active_memories=90)
        assert stats.total_memories == 100
        assert stats.active_memories == 90


@pytest.mark.unit
class TestMemoryUpdate:
    def test_partial_update(self) -> None:
        update = MemoryUpdate(importance=MemoryImportance.HIGH)
        assert update.importance == MemoryImportance.HIGH
        assert update.content is None
        assert update.tags is None


@pytest.mark.unit
class TestExtractedMemory:
    def test_construction(self) -> None:
        mem = ExtractedMemory(
            content="User prefers dark mode",
            memory_type=MemoryType.PREFERENCE,
        )
        assert mem.confidence == 0.8
        assert mem.importance == MemoryImportance.MEDIUM
        assert mem.entities == []
