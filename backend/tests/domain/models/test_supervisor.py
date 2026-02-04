"""Tests for Supervisor model in hierarchical multi-agent system (HMAS).

Tests the Supervisor model that implements Manus AI's HMAS pattern,
including domain management, task assignment, dependency resolution,
and task completion tracking.
"""

from datetime import UTC, datetime

from app.domain.models.supervisor import (
    SubTask,
    SubTaskStatus,
    Supervisor,
    SupervisorDomain,
)


class TestSupervisorDomain:
    """Tests for SupervisorDomain enum."""

    def test_supervisor_domain_values(self):
        """Test SupervisorDomain enum has expected values."""
        assert SupervisorDomain.RESEARCH == "research"
        assert SupervisorDomain.CODE == "code"
        assert SupervisorDomain.DATA == "data"
        assert SupervisorDomain.BROWSER == "browser"
        assert SupervisorDomain.GENERAL == "general"

    def test_supervisor_domain_is_string_enum(self):
        """Test SupervisorDomain can be compared to string values."""
        assert SupervisorDomain.RESEARCH == "research"
        assert SupervisorDomain.CODE.value == "code"


class TestSubTaskStatus:
    """Tests for SubTaskStatus enum."""

    def test_subtask_status_values(self):
        """Test SubTaskStatus enum has expected values."""
        assert SubTaskStatus.PENDING == "pending"
        assert SubTaskStatus.ASSIGNED == "assigned"
        assert SubTaskStatus.IN_PROGRESS == "in_progress"
        assert SubTaskStatus.COMPLETED == "completed"
        assert SubTaskStatus.FAILED == "failed"


class TestSubTask:
    """Tests for SubTask model."""

    def test_subtask_creation_minimal(self):
        """Test creating a SubTask with minimal fields."""
        task = SubTask(
            id="task_1",
            description="Write the function",
        )
        assert task.id == "task_1"
        assert task.description == "Write the function"
        assert task.assigned_agent is None
        assert task.status == SubTaskStatus.PENDING
        assert task.result is None
        assert task.dependencies == []
        assert task.created_at is not None

    def test_subtask_creation_full(self):
        """Test creating a SubTask with all fields."""
        task = SubTask(
            id="task_2",
            description="Implement the feature",
            assigned_agent="code-agent-1",
            status=SubTaskStatus.IN_PROGRESS,
            result={"output": "partial"},
            dependencies=["task_1"],
        )
        assert task.id == "task_2"
        assert task.assigned_agent == "code-agent-1"
        assert task.status == SubTaskStatus.IN_PROGRESS
        assert task.result == {"output": "partial"}
        assert task.dependencies == ["task_1"]

    def test_subtask_created_at_uses_utc(self):
        """Test that created_at timestamp uses UTC."""
        before = datetime.now(UTC)
        task = SubTask(id="task_1", description="Test task")
        after = datetime.now(UTC)

        # Verify the timestamp is within our bounds
        assert before <= task.created_at <= after


class TestSupervisor:
    """Tests for Supervisor model."""

    def test_supervisor_creation(self):
        """Test creating a Supervisor with basic fields."""
        supervisor = Supervisor(
            name="research-supervisor",
            domain=SupervisorDomain.RESEARCH,
            description="Manages research sub-tasks",
        )
        assert supervisor.name == "research-supervisor"
        assert supervisor.domain == SupervisorDomain.RESEARCH
        assert supervisor.description == "Manages research sub-tasks"
        assert supervisor.tasks == []
        assert supervisor.worker_agents == []

    def test_supervisor_creation_minimal(self):
        """Test creating a Supervisor with minimal fields."""
        supervisor = Supervisor(
            name="code-supervisor",
            domain=SupervisorDomain.CODE,
        )
        assert supervisor.name == "code-supervisor"
        assert supervisor.domain == SupervisorDomain.CODE
        assert supervisor.description == ""

    def test_supervisor_task_assignment(self):
        """Test assigning tasks to a supervisor."""
        supervisor = Supervisor(
            name="code-supervisor",
            domain=SupervisorDomain.CODE,
        )

        task = SubTask(
            id="task_1",
            description="Write the function",
            assigned_agent="code-agent-1",
        )

        supervisor.assign_task(task)
        assert len(supervisor.tasks) == 1
        assert supervisor.tasks[0].assigned_agent == "code-agent-1"

    def test_supervisor_multiple_task_assignment(self):
        """Test assigning multiple tasks to a supervisor."""
        supervisor = Supervisor(
            name="data-supervisor",
            domain=SupervisorDomain.DATA,
        )

        task1 = SubTask(id="task_1", description="Extract data")
        task2 = SubTask(id="task_2", description="Transform data", dependencies=["task_1"])
        task3 = SubTask(id="task_3", description="Load data", dependencies=["task_2"])

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)
        supervisor.assign_task(task3)

        assert len(supervisor.tasks) == 3
        assert supervisor.tasks[1].dependencies == ["task_1"]

    def test_supervisor_with_worker_agents(self):
        """Test supervisor with assigned worker agents."""
        supervisor = Supervisor(
            name="browser-supervisor",
            domain=SupervisorDomain.BROWSER,
            worker_agents=["browser-agent-1", "browser-agent-2"],
        )
        assert len(supervisor.worker_agents) == 2
        assert "browser-agent-1" in supervisor.worker_agents


class TestSupervisorGetReadyTasks:
    """Tests for Supervisor.get_ready_tasks method."""

    def test_get_ready_tasks_no_dependencies(self):
        """Test getting ready tasks when no dependencies exist."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task1 = SubTask(id="task_1", description="Task 1")
        task2 = SubTask(id="task_2", description="Task 2")

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)

        ready = supervisor.get_ready_tasks()
        assert len(ready) == 2

    def test_get_ready_tasks_with_dependencies(self):
        """Test getting ready tasks respects dependencies."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task1 = SubTask(id="task_1", description="First task")
        task2 = SubTask(id="task_2", description="Second task", dependencies=["task_1"])

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)

        ready = supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_1"

    def test_get_ready_tasks_after_completion(self):
        """Test that completing a task unblocks dependent tasks."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task1 = SubTask(id="task_1", description="First task")
        task2 = SubTask(id="task_2", description="Second task", dependencies=["task_1"])

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)

        # Initially only task_1 is ready
        assert len(supervisor.get_ready_tasks()) == 1

        # Complete task_1
        supervisor.complete_task("task_1", result="Done")

        # Now task_2 should be ready
        ready = supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_2"

    def test_get_ready_tasks_excludes_non_pending(self):
        """Test that only pending tasks are returned as ready."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task1 = SubTask(id="task_1", description="Task 1")
        task2 = SubTask(id="task_2", description="Task 2", status=SubTaskStatus.IN_PROGRESS)
        task3 = SubTask(id="task_3", description="Task 3", status=SubTaskStatus.COMPLETED)

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)
        supervisor.assign_task(task3)

        ready = supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_1"

    def test_get_ready_tasks_multiple_dependencies(self):
        """Test task with multiple dependencies only becomes ready when all are done."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task1 = SubTask(id="task_1", description="Task 1")
        task2 = SubTask(id="task_2", description="Task 2")
        task3 = SubTask(id="task_3", description="Task 3", dependencies=["task_1", "task_2"])

        supervisor.assign_task(task1)
        supervisor.assign_task(task2)
        supervisor.assign_task(task3)

        # task_1 and task_2 are ready, task_3 is blocked
        ready = supervisor.get_ready_tasks()
        assert len(ready) == 2
        ready_ids = {t.id for t in ready}
        assert "task_1" in ready_ids
        assert "task_2" in ready_ids
        assert "task_3" not in ready_ids

        # Complete task_1 only - task_3 still blocked
        supervisor.complete_task("task_1", "Done 1")
        ready = supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_2"

        # Complete task_2 - now task_3 is ready
        supervisor.complete_task("task_2", "Done 2")
        ready = supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "task_3"


class TestSupervisorCompleteTask:
    """Tests for Supervisor.complete_task method."""

    def test_complete_task_updates_status(self):
        """Test that completing a task updates its status."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task = SubTask(id="task_1", description="Test task")
        supervisor.assign_task(task)

        supervisor.complete_task("task_1", result="Success")

        assert supervisor.tasks[0].status == SubTaskStatus.COMPLETED

    def test_complete_task_stores_result(self):
        """Test that completing a task stores its result."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task = SubTask(id="task_1", description="Test task")
        supervisor.assign_task(task)

        result_data = {"output": "Generated content", "tokens": 1500}
        supervisor.complete_task("task_1", result=result_data)

        assert supervisor.tasks[0].result == result_data

    def test_complete_task_nonexistent_id(self):
        """Test completing a non-existent task does not raise error."""
        supervisor = Supervisor(
            name="test-supervisor",
            domain=SupervisorDomain.GENERAL,
        )

        task = SubTask(id="task_1", description="Test task")
        supervisor.assign_task(task)

        # Should not raise, just silently do nothing
        supervisor.complete_task("nonexistent_task", result="Nothing")

        # Original task unchanged
        assert supervisor.tasks[0].status == SubTaskStatus.PENDING
