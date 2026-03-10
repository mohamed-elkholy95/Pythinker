"""Tests for background task drain before phase transition."""

from __future__ import annotations

import asyncio

import pytest


class TestBackgroundTaskDrain:
    """Verify background tasks are awaited before critical transitions."""

    @pytest.mark.asyncio
    async def test_drain_background_tasks_awaits_pending(self):
        """_drain_background_tasks should await all pending background tasks."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        completed = asyncio.Event()

        async def slow_save():
            await asyncio.sleep(0.05)
            completed.set()

        task = asyncio.create_task(slow_save())
        flow._background_tasks.add(task)
        task.add_done_callback(flow._background_tasks.discard)

        await flow._drain_background_tasks()

        assert completed.is_set()
        assert len(flow._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_drain_background_tasks_handles_empty_set(self):
        """_drain_background_tasks is a no-op when no tasks are pending."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        await flow._drain_background_tasks()

    @pytest.mark.asyncio
    async def test_drain_background_tasks_tolerates_failures(self):
        """Failed background tasks should not crash the drain."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        async def failing_save():
            raise RuntimeError("sandbox write failed")

        task = asyncio.create_task(failing_save())
        flow._background_tasks.add(task)
        task.add_done_callback(flow._background_tasks.discard)

        # Should not raise
        await flow._drain_background_tasks()

    @pytest.mark.asyncio
    async def test_drain_background_tasks_respects_timeout(self):
        """Tasks exceeding timeout should not block indefinitely."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        hung = asyncio.Event()

        async def hanging_task():
            await asyncio.sleep(60)  # Way longer than timeout
            hung.set()

        task = asyncio.create_task(hanging_task())
        flow._background_tasks.add(task)
        task.add_done_callback(flow._background_tasks.discard)

        # Should return within timeout, not hang for 60s
        await flow._drain_background_tasks(drain_timeout=0.1)

        assert not hung.is_set()  # Task didn't finish
        task.cancel()  # Clean up

    @pytest.mark.asyncio
    async def test_drain_multiple_tasks(self):
        """Multiple background tasks should all be awaited."""
        from app.domain.services.flows.plan_act import PlanActFlow

        flow = PlanActFlow.__new__(PlanActFlow)
        flow._background_tasks = set()
        flow._agent_id = "test-agent"

        results: list[int] = []

        async def save_task(n: int):
            await asyncio.sleep(0.01 * n)
            results.append(n)

        for i in range(1, 4):
            task = asyncio.create_task(save_task(i))
            flow._background_tasks.add(task)
            task.add_done_callback(flow._background_tasks.discard)

        await flow._drain_background_tasks()

        assert sorted(results) == [1, 2, 3]
        assert len(flow._background_tasks) == 0
