"""Tests for ResearchTask model for wide research pattern.

Phase 2 Enhancement: Tests for parallel research sub-tasks with isolated contexts.
"""

from datetime import datetime

from app.domain.models.research_task import ResearchStatus, ResearchTask


class TestResearchStatus:
    """Tests for ResearchStatus enum."""

    def test_status_values(self):
        """Test all research status values exist."""
        assert ResearchStatus.PENDING.value == "pending"
        assert ResearchStatus.IN_PROGRESS.value == "in_progress"
        assert ResearchStatus.COMPLETED.value == "completed"
        assert ResearchStatus.FAILED.value == "failed"
        assert ResearchStatus.SKIPPED.value == "skipped"


class TestResearchTaskCreation:
    """Tests for ResearchTask creation."""

    def test_research_task_creation(self):
        """Test basic research task creation."""
        task = ResearchTask(query="What is the capital of France?", parent_task_id="parent_123", index=0, total=10)
        assert task.status == ResearchStatus.PENDING
        assert task.index == 0
        assert task.total == 10
        assert task.query == "What is the capital of France?"
        assert task.parent_task_id == "parent_123"

    def test_research_task_default_values(self):
        """Test research task default values."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        assert task.id.startswith("research_")
        assert task.result is None
        assert task.sources == []
        assert task.error is None
        assert task.started_at is None
        assert task.completed_at is None

    def test_research_task_custom_id(self):
        """Test research task with custom ID."""
        task = ResearchTask(id="custom_research_id", query="Test query", parent_task_id="parent_123", index=0, total=1)
        assert task.id == "custom_research_id"


class TestResearchTaskLifecycle:
    """Tests for ResearchTask lifecycle methods."""

    def test_research_task_start(self):
        """Test starting a research task."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        task.start()
        assert task.status == ResearchStatus.IN_PROGRESS
        assert task.started_at is not None
        assert isinstance(task.started_at, datetime)

    def test_research_task_completion(self):
        """Test completing a research task."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        task.complete("Paris is the capital")
        assert task.status == ResearchStatus.COMPLETED
        assert task.result == "Paris is the capital"
        assert task.completed_at is not None

    def test_research_task_completion_with_sources(self):
        """Test completing a research task with sources."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        sources = ["https://example.com", "https://wikipedia.org"]
        task.complete("Paris is the capital", sources=sources)
        assert task.status == ResearchStatus.COMPLETED
        assert task.result == "Paris is the capital"
        assert task.sources == sources

    def test_research_task_failure(self):
        """Test failing a research task."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        task.fail("Network timeout")
        assert task.status == ResearchStatus.FAILED
        assert task.error == "Network timeout"
        assert task.completed_at is not None

    def test_research_task_skip(self):
        """Test skipping a research task."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        task.skip("Duplicate query")
        assert task.status == ResearchStatus.SKIPPED
        assert task.error == "Duplicate query"
        assert task.completed_at is not None

    def test_research_task_skip_default_reason(self):
        """Test skipping a research task with default reason."""
        task = ResearchTask(query="Test query", parent_task_id="parent_123", index=0, total=1)
        task.skip()
        assert task.status == ResearchStatus.SKIPPED
        assert task.error == "Skipped by user"


class TestResearchTaskSerialization:
    """Tests for ResearchTask serialization."""

    def test_to_dict(self):
        """Test research task dict serialization."""
        task = ResearchTask(id="research_123", query="Test query", parent_task_id="parent_123", index=0, total=5)
        data = task.model_dump()
        assert data["id"] == "research_123"
        assert data["query"] == "Test query"
        assert data["parent_task_id"] == "parent_123"
        assert data["index"] == 0
        assert data["total"] == 5
        assert data["status"] == ResearchStatus.PENDING

    def test_from_dict(self):
        """Test research task dict deserialization."""
        data = {
            "id": "research_123",
            "query": "Test query",
            "parent_task_id": "parent_123",
            "index": 2,
            "total": 5,
            "status": "completed",
            "result": "Test result",
            "sources": ["https://example.com"],
        }
        task = ResearchTask.model_validate(data)
        assert task.id == "research_123"
        assert task.status == ResearchStatus.COMPLETED
        assert task.result == "Test result"
        assert task.sources == ["https://example.com"]
