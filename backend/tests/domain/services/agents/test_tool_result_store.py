"""Tests for ToolResultStore — external storage for large tool results."""

import pytest

from app.domain.services.agents.tool_result_store import StoredResult, ToolResultStore


class TestShouldOffload:
    """Threshold logic for deciding when to offload."""

    def test_below_threshold_returns_false(self):
        store = ToolResultStore(offload_threshold=4000)
        assert store.should_offload("x" * 3999) is False

    def test_at_threshold_returns_false(self):
        store = ToolResultStore(offload_threshold=4000)
        assert store.should_offload("x" * 4000) is False

    def test_above_threshold_returns_true(self):
        store = ToolResultStore(offload_threshold=4000)
        assert store.should_offload("x" * 4001) is True

    def test_custom_threshold(self):
        store = ToolResultStore(offload_threshold=100)
        assert store.should_offload("x" * 100) is False
        assert store.should_offload("x" * 101) is True

    def test_empty_string(self):
        store = ToolResultStore(offload_threshold=4000)
        assert store.should_offload("") is False


class TestStoreAndRetrieve:
    """Core store/retrieve round-trip."""

    def test_store_returns_id_and_preview(self):
        store = ToolResultStore(offload_threshold=100, preview_chars=50)
        content = "a" * 200
        result_id, preview = store.store(content, "shell_exec")

        assert result_id.startswith("trs-")
        assert len(result_id) > 4
        assert f"[ref:{result_id}]" in preview
        assert len(preview) <= 200  # preview should be much shorter than content

    def test_retrieve_returns_full_content(self):
        store = ToolResultStore(offload_threshold=100, preview_chars=50)
        content = "full content here " * 20
        result_id, _ = store.store(content, "file_read")

        retrieved = store.retrieve(result_id)
        assert retrieved == content

    def test_retrieve_nonexistent_returns_none(self):
        store = ToolResultStore()
        assert store.retrieve("trs-nonexistent") is None

    def test_custom_result_id(self):
        store = ToolResultStore(offload_threshold=10)
        content = "x" * 100
        result_id, preview = store.store(content, "shell_exec", result_id="custom-id-123")

        assert result_id == "custom-id-123"
        assert "[ref:custom-id-123]" in preview
        assert store.retrieve("custom-id-123") == content

    def test_store_same_id_updates(self):
        store = ToolResultStore(offload_threshold=10)
        store.store("first content here!", "shell_exec", result_id="same-id")
        store.store("updated content here!", "shell_exec", result_id="same-id")

        assert store.retrieve("same-id") == "updated content here!"
        assert store.get_stats()["current_entries"] == 1

    def test_small_content_still_stored(self):
        """Even small content can be explicitly stored (should_offload is advisory)."""
        store = ToolResultStore(offload_threshold=4000)
        content = "small"
        result_id, _preview = store.store(content, "shell_exec")

        assert store.retrieve(result_id) == content


class TestPreview:
    """Preview generation with line-boundary truncation."""

    def test_preview_contains_ref_marker(self):
        store = ToolResultStore(offload_threshold=10, preview_chars=100)
        content = "line 1\nline 2\nline 3\n" * 10
        result_id, preview = store.store(content, "file_read")

        assert f"[ref:{result_id}]" in preview

    def test_preview_respects_char_limit(self):
        store = ToolResultStore(offload_threshold=10, preview_chars=100)
        content = "x" * 500
        _, preview = store.store(content, "browser_view")

        # Preview should be roughly within the char limit (plus marker)
        assert len(preview) < 200  # generous upper bound

    def test_preview_truncates_at_newline(self):
        store = ToolResultStore(offload_threshold=10, preview_chars=80)
        content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\n" * 5
        _, preview = store.store(content, "file_read")

        # Should end at a clean line, not mid-word
        lines = preview.split("\n")
        # At least one complete line preserved
        assert any(line.startswith("line") for line in lines)

    def test_short_content_no_truncation(self):
        store = ToolResultStore(offload_threshold=10, preview_chars=500)
        content = "short content"
        result_id, preview = store.store(content, "test")

        assert content in preview
        assert f"[ref:{result_id}]" in preview
        assert "omitted" not in preview


class TestLRUEviction:
    """LRU eviction at max_entries."""

    def test_eviction_at_capacity(self):
        store = ToolResultStore(offload_threshold=10, max_entries=3)

        store.store("content-a" * 5, "tool_a", result_id="id-1")
        store.store("content-b" * 5, "tool_b", result_id="id-2")
        store.store("content-c" * 5, "tool_c", result_id="id-3")

        # Refresh id-1 so it's no longer the oldest
        store.retrieve("id-1")

        # Adding a 4th should evict id-2 from LRU (now oldest after id-1 was refreshed)
        store.store("content-d" * 5, "tool_d", result_id="id-4")

        assert "id-2" not in store._store  # evicted from in-memory LRU
        # But still retrievable via disk spillover
        assert store.retrieve("id-2") is not None
        assert store.retrieve("id-1") is not None
        assert store.retrieve("id-3") is not None
        assert store.retrieve("id-4") is not None
        store.cleanup_disk()

    def test_eviction_without_retrieves(self):
        """Without any retrieves to refresh, oldest insert is evicted from LRU."""
        store = ToolResultStore(offload_threshold=10, max_entries=2)

        store.store("aaa" * 10, "tool", result_id="first")
        store.store("bbb" * 10, "tool", result_id="second")
        store.store("ccc" * 10, "tool", result_id="third")

        assert "first" not in store._store  # evicted from in-memory LRU
        # Still retrievable via disk spillover
        assert store.retrieve("first") is not None
        assert store.retrieve("second") is not None
        assert store.retrieve("third") is not None
        store.cleanup_disk()

    def test_retrieve_refreshes_lru(self):
        store = ToolResultStore(offload_threshold=10, max_entries=2)

        store.store("aaa" * 10, "tool", result_id="first")
        store.store("bbb" * 10, "tool", result_id="second")

        # Access "first" to refresh its position
        store.retrieve("first")

        # Now "second" is oldest — evicted from LRU when third is added
        store.store("ccc" * 10, "tool", result_id="third")

        assert "first" in store._store  # refreshed, not evicted from LRU
        assert "second" not in store._store  # evicted from LRU
        # But still retrievable via disk spillover
        assert store.retrieve("first") is not None
        assert store.retrieve("second") is not None
        assert store.retrieve("third") is not None
        store.cleanup_disk()


class TestGetStats:
    """Statistics reporting."""

    def test_empty_stats(self):
        store = ToolResultStore()
        stats = store.get_stats()

        assert stats["current_entries"] == 0
        assert stats["total_stored"] == 0
        assert stats["total_evicted"] == 0
        assert stats["total_bytes_saved"] == 0
        assert stats["max_entries"] == 200

    def test_stats_after_stores(self):
        store = ToolResultStore(offload_threshold=10, preview_chars=50)
        store.store("x" * 200, "tool_a")
        store.store("y" * 300, "tool_b")

        stats = store.get_stats()
        assert stats["current_entries"] == 2
        assert stats["total_stored"] == 2
        assert stats["total_bytes_saved"] > 0  # previews are shorter than full content

    def test_stats_after_eviction(self):
        store = ToolResultStore(offload_threshold=10, max_entries=1)
        store.store("x" * 100, "tool_a")
        store.store("y" * 100, "tool_b")

        stats = store.get_stats()
        assert stats["current_entries"] == 1
        assert stats["total_stored"] == 2
        assert stats["total_evicted"] == 1


class TestStoredResult:
    """StoredResult dataclass."""

    def test_immutable(self):
        entry = StoredResult(
            result_id="test-id",
            function_name="shell_exec",
            full_content="content",
            original_size=7,
            preview="cont...",
        )
        with pytest.raises(AttributeError):
            entry.result_id = "new-id"  # type: ignore[misc]

    def test_stored_at_default(self):
        entry = StoredResult(
            result_id="test-id",
            function_name="shell_exec",
            full_content="content",
            original_size=7,
            preview="cont...",
        )
        assert entry.stored_at > 0


class TestFeatureFlagFallback:
    """When store is None, existing compaction should be used (integration pattern)."""

    def test_none_store_pattern(self):
        """Demonstrates the guard pattern used in base.py."""
        store: ToolResultStore | None = None
        content = "x" * 10000

        # When store is None, should_offload is never called
        if store and store.should_offload(content):
            pytest.fail("Should not reach here when store is None")

        # Existing compaction would handle this case
        assert True


# ── Phase 1C: Per-message budget ──────────────────────────────────────


class TestEnforceMessageBudget:
    """Per-message aggregate budget enforcement."""

    def test_within_budget_no_changes(self):
        store = ToolResultStore(per_message_budget_chars=1000)
        results = [("search", "x" * 200), ("file_read", "y" * 300)]
        enforced = store.enforce_message_budget(results)
        assert len(enforced) == 2
        assert enforced[0] == ("search", "x" * 200)
        assert enforced[1] == ("file_read", "y" * 300)

    def test_over_budget_offloads_largest(self):
        store = ToolResultStore(
            offload_threshold=100,
            preview_chars=50,
            per_message_budget_chars=500,
        )
        results = [
            ("small_tool", "a" * 50),
            ("big_tool", "b" * 5000),
            ("medium_tool", "c" * 200),
        ]
        enforced = store.enforce_message_budget(results)

        # Original order preserved
        assert enforced[0][0] == "small_tool"
        assert enforced[1][0] == "big_tool"
        assert enforced[2][0] == "medium_tool"

        # big_tool should have been offloaded (replaced with preview)
        assert len(enforced[1][1]) < 5000
        assert "[ref:" in enforced[1][1]

        # small_tool below offload_threshold, kept as-is
        assert enforced[0][1] == "a" * 50

    def test_over_budget_with_all_small_results_still_shrinks_context(self):
        store = ToolResultStore(
            offload_threshold=1000,
            preview_chars=50,
            per_message_budget_chars=100,
        )
        results = [("a", "x" * 50), ("b", "y" * 50), ("c", "z" * 50)]
        enforced = store.enforce_message_budget(results)

        assert sum(len(content) for _, content in enforced) <= 100
        assert any("[ref:" in content for _, content in enforced)

    def test_preserves_order(self):
        store = ToolResultStore(
            offload_threshold=10,
            per_message_budget_chars=100,
        )
        results = [("a", "x" * 80), ("b", "y" * 80), ("c", "z" * 80)]
        enforced = store.enforce_message_budget(results)
        assert [fn for fn, _ in enforced] == ["a", "b", "c"]

    def test_empty_results(self):
        store = ToolResultStore()
        assert store.enforce_message_budget([]) == []


# ── Phase 1C: Disk spillover ─────────────────────────────────────────


class TestDiskSpillover:
    """Disk-backed spillover on LRU eviction."""

    def test_evicted_entry_recoverable_from_disk(self):
        store = ToolResultStore(offload_threshold=10, max_entries=1)
        store.store("aaa" * 10, "tool_a", result_id="first")
        store.store("bbb" * 10, "tool_b", result_id="second")

        # "first" evicted from LRU
        assert "first" not in store._store
        # But recoverable from disk
        content = store.retrieve("first")
        assert content == "aaa" * 10
        store.cleanup_disk()

    def test_disk_file_created(self):
        store = ToolResultStore(offload_threshold=10, max_entries=1)
        store.store("aaa" * 10, "tool_a", result_id="first")
        store.store("bbb" * 10, "tool_b", result_id="second")

        disk_file = store.disk_dir / "first.json"
        assert disk_file.exists()
        store.cleanup_disk()

    def test_cleanup_removes_directory(self):
        store = ToolResultStore(offload_threshold=10, max_entries=1)
        store.store("aaa" * 10, "tool_a", result_id="first")
        store.store("bbb" * 10, "tool_b", result_id="second")

        assert store.disk_dir.exists()
        store.cleanup_disk()
        assert not store.disk_dir.exists()

    def test_retrieve_nonexistent_returns_none(self):
        store = ToolResultStore()
        assert store.retrieve("nonexistent-id") is None

    def test_stats_include_spilled_count(self):
        store = ToolResultStore(offload_threshold=10, max_entries=1)
        store.store("aaa" * 10, "tool_a", result_id="first")
        store.store("bbb" * 10, "tool_b", result_id="second")

        stats = store.get_stats()
        assert stats["total_spilled_to_disk"] == 1
        store.cleanup_disk()
