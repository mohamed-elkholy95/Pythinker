# backend/tests/domain/models/test_state_manifest.py
"""Tests for StateManifest model.

Tests the Blackboard Architecture pattern for inter-agent communication,
where agents post results to a shared state manifest.
"""

from datetime import UTC, datetime

from app.domain.models.state_manifest import StateEntry, StateManifest


class TestStateEntryCreation:
    """Tests for StateEntry creation."""

    def test_state_entry_creation(self):
        """Test basic StateEntry creation."""
        entry = StateEntry(
            key="research_findings",
            value={"topic": "AI", "summary": "Machine learning advances"},
            posted_by="research-agent-1",
        )
        assert entry.key == "research_findings"
        assert entry.value["topic"] == "AI"
        assert entry.posted_by == "research-agent-1"

    def test_state_entry_timestamp(self):
        """Test timestamp is auto-generated."""
        before = datetime.now(UTC)
        entry = StateEntry(
            key="test_key",
            value="test_value",
            posted_by="agent-1",
        )
        after = datetime.now(UTC)

        # Compare with timezone-aware timestamps
        assert before <= entry.timestamp <= after

    def test_state_entry_default_metadata(self):
        """Test default metadata is empty dict."""
        entry = StateEntry(
            key="test_key",
            value="test_value",
            posted_by="agent-1",
        )
        assert entry.metadata == {}

    def test_state_entry_with_metadata(self):
        """Test StateEntry with custom metadata."""
        entry = StateEntry(
            key="analysis_result",
            value={"score": 0.95},
            posted_by="analyzer-agent",
            metadata={"confidence": "high", "model": "gpt-4"},
        )
        assert entry.metadata["confidence"] == "high"
        assert entry.metadata["model"] == "gpt-4"


class TestStateManifestCreation:
    """Tests for StateManifest creation."""

    def test_state_manifest_creation(self):
        """Test basic StateManifest creation."""
        manifest = StateManifest(session_id="sess_123")
        assert manifest.session_id == "sess_123"
        assert len(manifest.entries) == 0

    def test_state_manifest_with_initial_entries(self):
        """Test StateManifest with pre-populated entries."""
        entries = [
            StateEntry(key="key1", value="value1", posted_by="agent-1"),
            StateEntry(key="key2", value="value2", posted_by="agent-2"),
        ]
        manifest = StateManifest(session_id="sess_123", entries=entries)
        assert len(manifest.entries) == 2


class TestStateManifestPost:
    """Tests for StateManifest.post() method."""

    def test_state_manifest_post_entry(self):
        """Test posting an entry to the blackboard."""
        manifest = StateManifest(session_id="sess_123")

        entry = StateEntry(
            key="research_findings",
            value={"topic": "AI", "summary": "..."},
            posted_by="research-agent-1",
        )

        manifest.post(entry)
        assert len(manifest.entries) == 1

        retrieved = manifest.get("research_findings")
        assert retrieved is not None
        assert retrieved.value["topic"] == "AI"

    def test_state_manifest_post_multiple_entries(self):
        """Test posting multiple entries."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(StateEntry(key="key1", value="value1", posted_by="agent-1"))
        manifest.post(StateEntry(key="key2", value="value2", posted_by="agent-2"))
        manifest.post(StateEntry(key="key3", value="value3", posted_by="agent-1"))

        assert len(manifest.entries) == 3


class TestStateManifestGet:
    """Tests for StateManifest.get() method."""

    def test_state_manifest_get_existing_key(self):
        """Test getting an existing key."""
        manifest = StateManifest(session_id="sess_123")
        manifest.post(StateEntry(key="test_key", value="test_value", posted_by="agent-1"))

        result = manifest.get("test_key")
        assert result is not None
        assert result.value == "test_value"

    def test_state_manifest_get_nonexistent_key(self):
        """Test getting a nonexistent key returns None."""
        manifest = StateManifest(session_id="sess_123")
        result = manifest.get("nonexistent")
        assert result is None

    def test_state_manifest_get_returns_latest(self):
        """Test get returns the latest entry for a key."""
        manifest = StateManifest(session_id="sess_123")
        manifest.post(StateEntry(key="counter", value=1, posted_by="agent-1"))
        manifest.post(StateEntry(key="counter", value=2, posted_by="agent-1"))
        manifest.post(StateEntry(key="counter", value=3, posted_by="agent-1"))

        result = manifest.get("counter")
        assert result is not None
        assert result.value == 3


class TestStateManifestHistory:
    """Tests for StateManifest.get_history() method."""

    def test_state_manifest_history(self):
        """Test getting history of entries for a key."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(StateEntry(key="count", value=1, posted_by="agent-1"))
        manifest.post(StateEntry(key="count", value=2, posted_by="agent-2"))

        history = manifest.get_history("count")
        assert len(history) == 2
        assert history[0].value == 1
        assert history[1].value == 2

    def test_state_manifest_history_empty(self):
        """Test getting history for nonexistent key returns empty list."""
        manifest = StateManifest(session_id="sess_123")
        history = manifest.get_history("nonexistent")
        assert history == []

    def test_state_manifest_history_chronological_order(self):
        """Test history is in chronological order."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(StateEntry(key="progress", value="started", posted_by="agent-1"))
        manifest.post(StateEntry(key="progress", value="in_progress", posted_by="agent-1"))
        manifest.post(StateEntry(key="progress", value="completed", posted_by="agent-1"))

        history = manifest.get_history("progress")
        assert len(history) == 3
        assert history[0].value == "started"
        assert history[1].value == "in_progress"
        assert history[2].value == "completed"


class TestStateManifestByAgent:
    """Tests for StateManifest.get_by_agent() method."""

    def test_state_manifest_get_by_agent(self):
        """Test getting all entries by a specific agent."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(StateEntry(key="key1", value="value1", posted_by="agent-1"))
        manifest.post(StateEntry(key="key2", value="value2", posted_by="agent-2"))
        manifest.post(StateEntry(key="key3", value="value3", posted_by="agent-1"))

        agent_1_entries = manifest.get_by_agent("agent-1")
        assert len(agent_1_entries) == 2
        assert all(e.posted_by == "agent-1" for e in agent_1_entries)

    def test_state_manifest_get_by_agent_empty(self):
        """Test getting entries for agent with no entries."""
        manifest = StateManifest(session_id="sess_123")
        manifest.post(StateEntry(key="key1", value="value1", posted_by="agent-1"))

        entries = manifest.get_by_agent("agent-2")
        assert entries == []


class TestStateManifestRecent:
    """Tests for StateManifest.get_recent() method."""

    def test_state_manifest_get_recent(self):
        """Test getting recent entries."""
        manifest = StateManifest(session_id="sess_123")

        for i in range(15):
            manifest.post(StateEntry(key=f"key_{i}", value=i, posted_by="agent-1"))

        recent = manifest.get_recent(limit=5)
        assert len(recent) == 5
        # Most recent should be last (index 14, 13, 12, 11, 10)
        assert recent[0].value == 14
        assert recent[4].value == 10

    def test_state_manifest_get_recent_default_limit(self):
        """Test default limit is 10."""
        manifest = StateManifest(session_id="sess_123")

        for i in range(15):
            manifest.post(StateEntry(key=f"key_{i}", value=i, posted_by="agent-1"))

        recent = manifest.get_recent()
        assert len(recent) == 10

    def test_state_manifest_get_recent_fewer_than_limit(self):
        """Test when there are fewer entries than the limit."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(StateEntry(key="key1", value=1, posted_by="agent-1"))
        manifest.post(StateEntry(key="key2", value=2, posted_by="agent-1"))

        recent = manifest.get_recent(limit=10)
        assert len(recent) == 2


class TestStateManifestContextString:
    """Tests for StateManifest.to_context_string() method."""

    def test_state_manifest_to_context_string(self):
        """Test converting manifest to context string."""
        manifest = StateManifest(session_id="sess_123")

        manifest.post(
            StateEntry(
                key="research_topic",
                value="AI safety",
                posted_by="planner-agent",
            )
        )
        manifest.post(
            StateEntry(
                key="findings",
                value={"count": 5, "sources": ["paper1", "paper2"]},
                posted_by="research-agent",
            )
        )

        context = manifest.to_context_string()
        assert "research_topic" in context
        assert "AI safety" in context
        assert "findings" in context
        assert "planner-agent" in context
        assert "research-agent" in context

    def test_state_manifest_to_context_string_empty(self):
        """Test context string for empty manifest."""
        manifest = StateManifest(session_id="sess_123")
        context = manifest.to_context_string()
        assert isinstance(context, str)

    def test_state_manifest_to_context_string_limit(self):
        """Test context string respects max_entries limit."""
        manifest = StateManifest(session_id="sess_123")

        for i in range(20):
            manifest.post(StateEntry(key=f"key_{i}", value=f"value_{i}", posted_by="agent-1"))

        context = manifest.to_context_string(max_entries=5)
        # Should only include recent 5 entries
        assert "key_19" in context
        assert "key_15" in context
        # Earlier entries should not be included
        assert "key_0" not in context


class TestStateManifestIndexRebuild:
    """Tests for StateManifest index rebuilding."""

    def test_state_manifest_index_rebuilt_on_init(self):
        """Test index is rebuilt when initializing with entries."""
        entries = [
            StateEntry(key="key1", value="v1", posted_by="agent-1"),
            StateEntry(key="key2", value="v2", posted_by="agent-2"),
            StateEntry(key="key1", value="v3", posted_by="agent-1"),
        ]
        manifest = StateManifest(session_id="sess_123", entries=entries)

        # Index should be rebuilt, allowing retrieval
        result = manifest.get("key1")
        assert result is not None
        assert result.value == "v3"  # Latest

        history = manifest.get_history("key1")
        assert len(history) == 2
