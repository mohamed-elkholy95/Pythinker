# backend/tests/domain/models/test_context_memory.py
"""Tests for ContextMemory model.

Tests the file-system-as-context pattern from Pythinker AI architecture.
"""

from datetime import datetime

from app.domain.models.context_memory import ContextMemory, ContextType


class TestContextType:
    """Tests for ContextType enum."""

    def test_context_type_values(self):
        """Test all context type values exist."""
        assert ContextType.GOAL.value == "goal"
        assert ContextType.TODO.value == "todo"
        assert ContextType.STATE.value == "state"
        assert ContextType.KNOWLEDGE.value == "knowledge"
        assert ContextType.RESEARCH.value == "research"


class TestContextMemoryCreation:
    """Tests for ContextMemory creation."""

    def test_context_memory_creation(self):
        """Test basic ContextMemory creation."""
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.GOAL,
            content="Complete the data analysis task",
            priority=1,
        )
        assert memory.session_id == "sess_123"
        assert memory.context_type == ContextType.GOAL
        assert memory.priority == 1
        assert memory.content == "Complete the data analysis task"

    def test_context_memory_default_priority(self):
        """Test default priority is 0."""
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.TODO,
            content="- [ ] Step 1",
        )
        assert memory.priority == 0

    def test_context_memory_default_file_path(self):
        """Test default file_path is None."""
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.STATE,
            content="Current state",
        )
        assert memory.file_path is None

    def test_context_memory_with_file_path(self):
        """Test ContextMemory with file_path specified."""
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.KNOWLEDGE,
            content="Learned facts",
            file_path="/workspace/knowledge.md",
        )
        assert memory.file_path == "/workspace/knowledge.md"

    def test_context_memory_timestamps(self):
        """Test timestamps are auto-generated."""
        before = datetime.utcnow()
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.RESEARCH,
            content="Research findings",
        )
        after = datetime.utcnow()

        assert before <= memory.created_at <= after
        assert before <= memory.updated_at <= after


class TestContextMemorySerialization:
    """Tests for ContextMemory serialization."""

    def test_context_memory_serialization(self):
        """Test serialization to dict."""
        memory = ContextMemory(
            session_id="sess_123",
            context_type=ContextType.TODO,
            content="- [ ] Step 1\n- [ ] Step 2",
        )
        data = memory.to_dict()
        assert data["context_type"] == "todo"
        assert "content" in data
        assert data["session_id"] == "sess_123"
        assert data["content"] == "- [ ] Step 1\n- [ ] Step 2"

    def test_context_memory_serialization_all_fields(self):
        """Test all fields are serialized correctly."""
        memory = ContextMemory(
            session_id="sess_456",
            context_type=ContextType.GOAL,
            content="Main objective",
            priority=5,
            file_path="/workspace/goal.md",
        )
        data = memory.to_dict()

        assert data["session_id"] == "sess_456"
        assert data["context_type"] == "goal"
        assert data["content"] == "Main objective"
        assert data["priority"] == 5
        assert data["file_path"] == "/workspace/goal.md"
        assert "created_at" in data
        assert "updated_at" in data

    def test_context_memory_deserialization(self):
        """Test deserialization from dict."""
        now = datetime.utcnow()
        data = {
            "session_id": "sess_789",
            "context_type": "knowledge",
            "content": "Important knowledge",
            "priority": 3,
            "file_path": "/workspace/knowledge.md",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        memory = ContextMemory.from_dict(data)

        assert memory.session_id == "sess_789"
        assert memory.context_type == ContextType.KNOWLEDGE
        assert memory.content == "Important knowledge"
        assert memory.priority == 3
        assert memory.file_path == "/workspace/knowledge.md"

    def test_context_memory_roundtrip(self):
        """Test serialization/deserialization roundtrip."""
        original = ContextMemory(
            session_id="sess_roundtrip",
            context_type=ContextType.STATE,
            content="Current execution state",
            priority=2,
            file_path="/workspace/state.json",
        )

        data = original.to_dict()
        restored = ContextMemory.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.context_type == original.context_type
        assert restored.content == original.content
        assert restored.priority == original.priority
        assert restored.file_path == original.file_path
