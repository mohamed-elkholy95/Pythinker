"""Tests for the agent runtime middleware pipeline."""

from __future__ import annotations

import pytest

from app.domain.services.runtime.middleware import (
    RuntimeContext,
    RuntimeHook,
    RuntimeMiddleware,
    RuntimePipeline,
)


class RecordingMiddleware(RuntimeMiddleware):
    """Middleware that records which hooks were called and in what order."""

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self._log = log

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:before_run")
        return ctx

    async def after_run(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:after_run")
        return ctx

    async def before_step(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:before_step")
        return ctx

    async def after_step(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:after_step")
        return ctx

    async def before_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:before_tool")
        return ctx

    async def after_tool(self, ctx: RuntimeContext) -> RuntimeContext:
        self._log.append(f"{self.name}:after_tool")
        return ctx


class TestRuntimePipeline:
    @pytest.mark.asyncio
    async def test_hooks_execute_in_order(self) -> None:
        """Two RecordingMiddleware instances fire before_run in construction order."""
        log: list[str] = []
        first = RecordingMiddleware("first", log)
        second = RecordingMiddleware("second", log)
        pipeline = RuntimePipeline(middlewares=[first, second])

        ctx = RuntimeContext(session_id="s1", agent_id="a1")
        await pipeline.run_hook(RuntimeHook.before_run, ctx)

        assert log == ["first:before_run", "second:before_run"]

    @pytest.mark.asyncio
    async def test_context_flows_through_chain(self) -> None:
        """Middleware that injects metadata; the mutation persists after the pipeline."""

        class InjectingMiddleware(RuntimeMiddleware):
            async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
                ctx.metadata["injected"] = True
                return ctx

        pipeline = RuntimePipeline(middlewares=[InjectingMiddleware()])
        ctx = RuntimeContext(session_id="s2", agent_id="a2")
        result = await pipeline.run_hook(RuntimeHook.before_run, ctx)

        assert result.metadata.get("injected") is True

    @pytest.mark.asyncio
    async def test_empty_pipeline_passes_through(self) -> None:
        """An empty middleware list returns the context unchanged."""
        pipeline = RuntimePipeline(middlewares=[])
        ctx = RuntimeContext(session_id="s3", agent_id="a3", metadata={"key": "value"})
        result = await pipeline.run_hook(RuntimeHook.after_step, ctx)

        assert result is ctx
        assert result.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_middleware_error_propagates(self) -> None:
        """A middleware that raises ValueError causes the pipeline to propagate it."""

        class BrokenMiddleware(RuntimeMiddleware):
            async def before_tool(self, ctx: RuntimeContext) -> RuntimeContext:
                raise ValueError("broken middleware")

        pipeline = RuntimePipeline(middlewares=[BrokenMiddleware()])
        ctx = RuntimeContext(session_id="s4", agent_id="a4")

        with pytest.raises(ValueError, match="broken middleware"):
            await pipeline.run_hook(RuntimeHook.before_tool, ctx)

    @pytest.mark.asyncio
    async def test_all_six_hooks_exist(self) -> None:
        """RuntimeHook has exactly the 6 expected values."""
        expected = {
            "before_run",
            "after_run",
            "before_step",
            "after_step",
            "before_tool",
            "after_tool",
        }
        actual = {hook.value for hook in RuntimeHook}
        assert actual == expected
        assert len(actual) == 6
