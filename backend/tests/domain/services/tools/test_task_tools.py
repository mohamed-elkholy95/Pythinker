"""Tests for TaskManagementTool."""

from __future__ import annotations

import pytest

from app.domain.services.agents.tool_result_store import ToolResultStore
from app.domain.services.tools.task_tools import ManagedTaskStatus, TaskManagementTool


def _tool(**kwargs) -> TaskManagementTool:
    return TaskManagementTool(**kwargs)


# ── task_create ───────────────────────────────────────────────────────────────


class TestTaskCreate:
    @pytest.mark.asyncio
    async def test_returns_task_id(self):
        t = _tool()
        r = await t.task_create(description="do something")
        assert r.success is True
        assert r.data["task_id"].startswith("tsk-")

    @pytest.mark.asyncio
    async def test_initial_status_pending(self):
        t = _tool()
        r = await t.task_create(description="x")
        assert r.data["status"] == ManagedTaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_empty_description_rejected(self):
        t = _tool()
        r = await t.task_create(description="")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_metadata_stored(self):
        t = _tool()
        r = await t.task_create(description="x", metadata={"priority": "high"})
        task_id = r.data["task_id"]
        assert t._store[task_id].metadata["priority"] == "high"

    @pytest.mark.asyncio
    async def test_multiple_tasks_get_unique_ids(self):
        t = _tool()
        ids = set()
        for _ in range(5):
            r = await t.task_create(description="x")
            ids.add(r.data["task_id"])
        assert len(ids) == 5


# ── task_update ───────────────────────────────────────────────────────────────


class TestTaskUpdate:
    @pytest.mark.asyncio
    async def test_update_status(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        r = await t.task_update(task_id=task_id, status="in_progress")
        assert r.success is True
        assert t._store[task_id].status == ManagedTaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_update_output(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, output="result text")
        assert t._store[task_id].output == "result text"

    @pytest.mark.asyncio
    async def test_update_unknown_task(self):
        t = _tool()
        r = await t.task_update(task_id="nonexistent", status="completed")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        r = await t.task_update(task_id=task_id, status="bogus_status")
        assert r.success is False
        assert "valid" in r.message.lower()

    @pytest.mark.asyncio
    async def test_update_touches_updated_at(self):
        import asyncio

        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        before = t._store[task_id].updated_at
        await asyncio.sleep(0.01)
        await t.task_update(task_id=task_id, status="in_progress")
        assert t._store[task_id].updated_at > before

    @pytest.mark.asyncio
    async def test_large_output_offloaded(self):
        store = ToolResultStore(offload_threshold=100, preview_chars=50)
        t = TaskManagementTool(result_store=store)
        task_id = (await t.task_create(description="x")).data["task_id"]
        big_output = "x" * 500
        await t.task_update(task_id=task_id, output=big_output)

        task = t._store[task_id]
        assert task.output_ref is not None
        assert "[ref:" in task.output

    @pytest.mark.asyncio
    async def test_small_output_not_offloaded(self):
        store = ToolResultStore(offload_threshold=4000)
        t = TaskManagementTool(result_store=store)
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, output="small")
        assert t._store[task_id].output_ref is None
        assert t._store[task_id].output == "small"


# ── task_list ─────────────────────────────────────────────────────────────────


class TestTaskList:
    @pytest.mark.asyncio
    async def test_list_all(self):
        t = _tool()
        await t.task_create(description="a")
        await t.task_create(description="b")
        r = await t.task_list()
        assert r.data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_empty(self):
        t = _tool()
        r = await t.task_list()
        assert r.data["total"] == 0

    @pytest.mark.asyncio
    async def test_filter_by_status(self):
        t = _tool()
        id1 = (await t.task_create(description="a")).data["task_id"]
        await t.task_create(description="b")
        await t.task_update(task_id=id1, status="completed")

        r = await t.task_list(status="completed")
        assert r.data["total"] == 1
        assert r.data["tasks"][0]["task_id"] == id1

    @pytest.mark.asyncio
    async def test_invalid_status_filter_rejected(self):
        t = _tool()
        r = await t.task_list(status="bad_status")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_pending_filter(self):
        t = _tool()
        await t.task_create(description="a")
        await t.task_create(description="b")
        id1 = (await t.task_create(description="c")).data["task_id"]
        await t.task_update(task_id=id1, status="completed")

        r = await t.task_list(status="pending")
        assert r.data["total"] == 2


# ── task_get ──────────────────────────────────────────────────────────────────


class TestTaskGet:
    @pytest.mark.asyncio
    async def test_get_known_task(self):
        t = _tool()
        task_id = (await t.task_create(description="my task")).data["task_id"]
        r = await t.task_get(task_id=task_id)
        assert r.success is True
        assert r.data["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_get_unknown_task(self):
        t = _tool()
        r = await t.task_get(task_id="nonexistent")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_get_includes_output_preview(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, output="some result")
        r = await t.task_get(task_id=task_id)
        assert r.data["output_preview"] == "some result"


# ── task_output ───────────────────────────────────────────────────────────────


class TestTaskOutput:
    @pytest.mark.asyncio
    async def test_output_unknown_task(self):
        t = _tool()
        r = await t.task_output(task_id="nonexistent")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_output_small_content(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, output="result")
        r = await t.task_output(task_id=task_id)
        assert r.success is True
        assert r.data["output"] == "result"
        assert r.data["offloaded"] is False

    @pytest.mark.asyncio
    async def test_output_offloaded_content_retrieved(self):
        store = ToolResultStore(offload_threshold=100, preview_chars=50)
        t = TaskManagementTool(result_store=store)
        task_id = (await t.task_create(description="x")).data["task_id"]
        big = "result " * 100
        await t.task_update(task_id=task_id, output=big)

        r = await t.task_output(task_id=task_id)
        assert r.success is True
        assert r.data["offloaded"] is True
        assert r.data["output"] == big  # full content recovered

    @pytest.mark.asyncio
    async def test_output_empty_task(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        r = await t.task_output(task_id=task_id)
        assert r.success is True
        assert "(no output)" in r.message


# ── task_stop ─────────────────────────────────────────────────────────────────


class TestTaskStop:
    @pytest.mark.asyncio
    async def test_stop_pending_task(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        r = await t.task_stop(task_id=task_id)
        assert r.success is True
        assert t._store[task_id].status == ManagedTaskStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_in_progress_task(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, status="in_progress")
        r = await t.task_stop(task_id=task_id)
        assert r.success is True
        assert t._store[task_id].status == ManagedTaskStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_completed_task_is_noop(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_update(task_id=task_id, status="completed")
        r = await t.task_stop(task_id=task_id)
        assert r.success is True
        assert "terminal state" in r.message
        assert t._store[task_id].status == ManagedTaskStatus.COMPLETED  # unchanged

    @pytest.mark.asyncio
    async def test_stop_unknown_task(self):
        t = _tool()
        r = await t.task_stop(task_id="nonexistent")
        assert r.success is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        t = _tool()
        task_id = (await t.task_create(description="x")).data["task_id"]
        await t.task_stop(task_id=task_id)
        r = await t.task_stop(task_id=task_id)  # second stop
        assert r.success is True
        assert t._store[task_id].status == ManagedTaskStatus.STOPPED
