"""Tests for multi-task challenge domain models."""

from app.domain.models.multi_task import (
    Deliverable,
    DeliverableType,
    MultiTaskChallenge,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)


class TestTaskStatus:
    def test_values(self) -> None:
        expected = {"pending", "in_progress", "completed", "failed", "skipped"}
        assert {s.value for s in TaskStatus} == expected


class TestDeliverableType:
    def test_values(self) -> None:
        expected = {"file", "directory", "report", "data", "code", "artifact"}
        assert {t.value for t in DeliverableType} == expected


class TestDeliverable:
    def test_required_fields(self) -> None:
        d = Deliverable(
            name="report.pdf",
            type=DeliverableType.REPORT,
            path="/workspace/report.pdf",
            description="Final report",
        )
        assert d.required is True
        assert d.validation_criteria is None


class TestTaskDefinition:
    def test_defaults(self) -> None:
        t = TaskDefinition(title="Research", description="Find data")
        assert t.status == TaskStatus.PENDING
        assert t.deliverables == []
        assert t.estimated_complexity == 0.5
        assert t.depends_on == []
        assert t.started_at is None
        assert len(t.id) > 0

    def test_with_deliverables(self) -> None:
        t = TaskDefinition(
            title="Code",
            description="Write code",
            deliverables=[
                Deliverable(name="main.py", type=DeliverableType.CODE, path="/main.py", description="Entry point")
            ],
        )
        assert len(t.deliverables) == 1


class TestTaskResult:
    def test_minimal(self) -> None:
        r = TaskResult(
            task_id="t-1",
            status=TaskStatus.COMPLETED,
            duration_seconds=10.5,
            iterations_used=2,
        )
        assert r.validation_passed is False
        assert r.deliverables_created == []


class TestMultiTaskChallenge:
    def _make(self) -> MultiTaskChallenge:
        return MultiTaskChallenge(
            title="Challenge",
            description="Multi-step",
            tasks=[
                TaskDefinition(id="t-0", title="Task 0", description="First"),
                TaskDefinition(id="t-1", title="Task 1", description="Second"),
                TaskDefinition(id="t-2", title="Task 2", description="Third"),
            ],
        )

    def test_defaults(self) -> None:
        c = MultiTaskChallenge(title="X", description="Y")
        assert c.tasks == []
        assert c.current_task_index == 0
        assert c.overall_success is False

    def test_get_current_task(self) -> None:
        c = self._make()
        task = c.get_current_task()
        assert task is not None
        assert task.id == "t-0"

    def test_get_current_task_out_of_range(self) -> None:
        c = self._make()
        c.current_task_index = 10
        assert c.get_current_task() is None

    def test_get_progress_percentage_empty(self) -> None:
        c = MultiTaskChallenge(title="X", description="Y")
        assert c.get_progress_percentage() == 0.0

    def test_get_progress_percentage(self) -> None:
        c = self._make()
        c.completed_tasks = ["t-0", "t-1"]
        progress = c.get_progress_percentage()
        assert abs(progress - 66.67) < 1.0

    def test_get_progress_percentage_all_done(self) -> None:
        c = self._make()
        c.completed_tasks = ["t-0", "t-1", "t-2"]
        assert c.get_progress_percentage() == 100.0
