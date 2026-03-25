"""Tests for BrowserLoginStateStore file-backed state storage."""

from pathlib import Path

import pytest

from app.domain.services.browser_login_state_store import BrowserLoginStateStore


@pytest.fixture()
def store(tmp_path: Path) -> BrowserLoginStateStore:
    return BrowserLoginStateStore(base_dir=tmp_path, ttl_days=7, max_states_per_user=3)


class TestBrowserLoginStateStore:
    def test_save_and_load(self, store: BrowserLoginStateStore) -> None:
        state = {"cookies": [{"name": "auth", "value": "token123"}]}
        store.save_state("user-1", "session-1", state)
        loaded = store.load_state("user-1", "session-1")
        assert loaded is not None
        assert loaded["cookies"][0]["value"] == "token123"

    def test_load_missing(self, store: BrowserLoginStateStore) -> None:
        assert store.load_state("user-1", "nonexistent") is None

    def test_delete_state(self, store: BrowserLoginStateStore) -> None:
        store.save_state("user-1", "session-1", {"key": "val"})
        store.delete_state("user-1", "session-1")
        assert store.load_state("user-1", "session-1") is None

    def test_delete_nonexistent(self, store: BrowserLoginStateStore) -> None:
        # Should not raise
        store.delete_state("user-1", "nonexistent")

    def test_safe_hash_deterministic(self) -> None:
        h1 = BrowserLoginStateStore._safe_hash("test")
        h2 = BrowserLoginStateStore._safe_hash("test")
        assert h1 == h2
        assert len(h1) == 24

    def test_safe_hash_different_inputs(self) -> None:
        h1 = BrowserLoginStateStore._safe_hash("alice")
        h2 = BrowserLoginStateStore._safe_hash("bob")
        assert h1 != h2

    def test_max_states_enforced(self, store: BrowserLoginStateStore) -> None:
        # Save 4 states (max is 3) — oldest should be evicted
        for i in range(4):
            store.save_state("user-1", f"session-{i}", {"idx": i})
        # Latest should be available
        assert store.load_state("user-1", "session-3") is not None

    def test_overwrite_existing(self, store: BrowserLoginStateStore) -> None:
        store.save_state("user-1", "s-1", {"v": 1})
        store.save_state("user-1", "s-1", {"v": 2})
        loaded = store.load_state("user-1", "s-1")
        assert loaded is not None
        assert loaded["v"] == 2
