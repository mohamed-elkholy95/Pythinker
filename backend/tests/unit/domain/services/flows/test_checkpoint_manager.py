"""Tests for CheckpointManager and WorkflowCheckpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.services.flows.checkpoint_manager import (
    CheckpointManager,
    CheckpointStatus,
    WorkflowCheckpoint,
    get_checkpoint_manager,
)


class TestWorkflowCheckpoint:
    """Tests for WorkflowCheckpoint dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        cp = WorkflowCheckpoint(
            workflow_id="wf-1",
            session_id="sess-1",
            stage_index=2,
            completed_steps=["s1", "s2"],
            step_results={"s1": "result1"},
            status=CheckpointStatus.ACTIVE,
            workflow_data={"key": "value"},
            context={"ctx": "data"},
        )
        d = cp.to_dict()
        restored = WorkflowCheckpoint.from_dict(d)
        assert restored.workflow_id == "wf-1"
        assert restored.session_id == "sess-1"
        assert restored.stage_index == 2
        assert restored.completed_steps == ["s1", "s2"]
        assert restored.status == CheckpointStatus.ACTIVE

    def test_from_dict_with_defaults(self) -> None:
        d = {
            "workflow_id": "wf-2",
            "session_id": "sess-2",
            "stage_index": 0,
        }
        cp = WorkflowCheckpoint.from_dict(d)
        assert cp.completed_steps == []
        assert cp.step_results == {}
        assert cp.status == CheckpointStatus.ACTIVE

    def test_is_expired_false_when_no_expiry(self) -> None:
        cp = WorkflowCheckpoint(
            workflow_id="wf",
            session_id="s",
            stage_index=0,
            completed_steps=[],
            step_results={},
            status=CheckpointStatus.ACTIVE,
            workflow_data={},
            context={},
            expires_at=None,
        )
        assert cp.is_expired() is False

    def test_is_expired_true_when_past(self) -> None:
        cp = WorkflowCheckpoint(
            workflow_id="wf",
            session_id="s",
            stage_index=0,
            completed_steps=[],
            step_results={},
            status=CheckpointStatus.ACTIVE,
            workflow_data={},
            context={},
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert cp.is_expired() is True

    def test_is_expired_false_when_future(self) -> None:
        cp = WorkflowCheckpoint(
            workflow_id="wf",
            session_id="s",
            stage_index=0,
            completed_steps=[],
            step_results={},
            status=CheckpointStatus.ACTIVE,
            workflow_data={},
            context={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert cp.is_expired() is False

    def test_to_dict_includes_all_fields(self) -> None:
        cp = WorkflowCheckpoint(
            workflow_id="wf",
            session_id="s",
            stage_index=1,
            completed_steps=["a"],
            step_results={"a": "r"},
            status=CheckpointStatus.PAUSED,
            workflow_data={"data": 1},
            context={"ctx": 2},
            metadata={"meta": 3},
        )
        d = cp.to_dict()
        assert d["status"] == "paused"
        assert d["metadata"] == {"meta": 3}
        assert "created_at" in d
        assert "updated_at" in d


class TestCheckpointStatus:
    """Tests for CheckpointStatus enum."""

    def test_values(self) -> None:
        assert CheckpointStatus.ACTIVE.value == "active"
        assert CheckpointStatus.PAUSED.value == "paused"
        assert CheckpointStatus.RESUMED.value == "resumed"
        assert CheckpointStatus.COMPLETED.value == "completed"
        assert CheckpointStatus.FAILED.value == "failed"
        assert CheckpointStatus.EXPIRED.value == "expired"


class TestCheckpointManagerMemory:
    """Tests for CheckpointManager with in-memory storage."""

    @pytest.mark.asyncio
    async def test_save_and_load_plan_checkpoint(self) -> None:
        mgr = CheckpointManager()
        cp = await mgr.save_plan_checkpoint(
            session_id="sess-1",
            plan_id="plan-1",
            completed_steps=["s1"],
            step_results={"s1": "done"},
            stage_index=1,
        )
        assert cp is not None
        assert cp.workflow_id == "plan-1"

        loaded = await mgr.load_checkpoint("plan-1", "sess-1")
        assert loaded is not None
        assert loaded.step_results == {"s1": "done"}

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self) -> None:
        mgr = CheckpointManager()
        assert await mgr.load_checkpoint("wf-x", "sess-x") is None

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)
        assert await mgr.delete_checkpoint("plan-1", "sess-1") is True
        assert await mgr.load_checkpoint("plan-1", "sess-1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self) -> None:
        mgr = CheckpointManager()
        assert await mgr.delete_checkpoint("wf-x", "sess-x") is False

    @pytest.mark.asyncio
    async def test_list_checkpoints_by_session(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)
        await mgr.save_plan_checkpoint("sess-1", "plan-2", [], {}, 0)
        await mgr.save_plan_checkpoint("sess-2", "plan-3", [], {}, 0)

        result = await mgr.list_checkpoints(session_id="sess-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_checkpoints_excludes_expired(self) -> None:
        mgr = CheckpointManager(ttl_hours=0)  # Immediate expiry
        # Save with 0 TTL — checkpoint expires immediately
        cp = await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)
        assert cp is not None
        # Force expiry
        cp.expires_at = datetime.now(UTC) - timedelta(hours=1)

        result = await mgr.list_checkpoints(session_id="sess-1")
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired(self) -> None:
        mgr = CheckpointManager()
        cp = await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)
        assert cp is not None
        cp.expires_at = datetime.now(UTC) - timedelta(hours=1)

        cleaned = await mgr.cleanup_expired()
        assert cleaned == 1
        assert await mgr.load_checkpoint("plan-1", "sess-1") is None

    @pytest.mark.asyncio
    async def test_has_resumable_checkpoint(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)

        wf_id = await mgr.has_resumable_checkpoint("sess-1")
        assert wf_id == "plan-1"

    @pytest.mark.asyncio
    async def test_has_no_resumable_checkpoint(self) -> None:
        mgr = CheckpointManager()
        assert await mgr.has_resumable_checkpoint("sess-x") is None

    @pytest.mark.asyncio
    async def test_get_step_result(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", ["s1"], {"s1": "result-data"}, 1)

        result = await mgr.get_step_result("plan-1", "sess-1", "s1")
        assert result == "result-data"

    @pytest.mark.asyncio
    async def test_get_step_result_missing(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)

        result = await mgr.get_step_result("plan-1", "sess-1", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_mark_completed(self) -> None:
        mgr = CheckpointManager()
        await mgr.save_plan_checkpoint("sess-1", "plan-1", [], {}, 0)

        success = await mgr.mark_completed("plan-1", "sess-1")
        assert success is True

        cp = await mgr.load_checkpoint("plan-1", "sess-1")
        assert cp is not None
        assert cp.status == CheckpointStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_mark_completed_nonexistent(self) -> None:
        mgr = CheckpointManager()
        assert await mgr.mark_completed("wf-x", "sess-x") is False


class TestGetCheckpointManager:
    """Tests for singleton accessor."""

    def test_returns_instance(self) -> None:
        mgr = get_checkpoint_manager()
        assert isinstance(mgr, CheckpointManager)
