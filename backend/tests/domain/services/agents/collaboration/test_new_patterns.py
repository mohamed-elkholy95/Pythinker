"""Tests for MapReducePattern and PipelinePattern."""

from __future__ import annotations

import pytest

from app.domain.services.agents.collaboration.patterns import (
    CollaborationContext,
    MapReducePattern,
    PatternExecutor,
    PatternType,
    PipelinePattern,
)
from app.domain.services.agents.communication.protocol import CommunicationProtocol
from app.domain.services.agents.registry.capability_registry import AgentRegistry


def _make_context(
    pattern_type: PatternType,
    participants: list[str] | None = None,
    task: str = "test task",
) -> CollaborationContext:
    return CollaborationContext(
        session_id="test-session",
        pattern_type=pattern_type,
        task_description=task,
        participants=participants or ["worker-a", "worker-b"],
    )


def _make_pattern(cls):
    registry = AgentRegistry()
    protocol = CommunicationProtocol()
    for agent_id in ["coordinator", "worker-a", "worker-b"]:
        protocol.register_agent(agent_id)
    return cls(registry=registry, protocol=protocol)


# ── MapReducePattern ─────────────────────────────────────────────────────────


class TestMapReducePattern:
    @pytest.mark.asyncio
    async def test_pattern_type(self):
        p = _make_pattern(MapReducePattern)
        assert p.pattern_type == PatternType.MAP_REDUCE

    @pytest.mark.asyncio
    async def test_returns_result(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE)
        result = await p.execute(ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_result_has_output(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE)
        result = await p.execute(ctx)
        assert result.final_output is not None
        assert len(result.final_output) > 0

    @pytest.mark.asyncio
    async def test_result_session_id_matches_context(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE)
        result = await p.execute(ctx)
        assert result.session_id == ctx.session_id

    @pytest.mark.asyncio
    async def test_participant_contributions_populated(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE, participants=["w1", "w2"])
        result = await p.execute(ctx)
        assert len(result.participant_contributions) > 0

    @pytest.mark.asyncio
    async def test_custom_subtasks_respected(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE)
        subtasks = ["subtask A", "subtask B", "subtask C"]
        result = await p.execute(ctx, subtasks=subtasks)
        assert result.metadata["subtasks_mapped"] == 3

    @pytest.mark.asyncio
    async def test_explicit_reducer_in_metadata(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE, participants=["reducer", "mapper"])
        result = await p.execute(ctx, reducer_id="reducer")
        assert result.metadata["reducer"] == "reducer"

    @pytest.mark.asyncio
    async def test_no_participants_still_produces_output(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE, participants=[])
        result = await p.execute(ctx, subtasks=["only task"])
        assert result.success is True

    @pytest.mark.asyncio
    async def test_pattern_type_in_result(self):
        p = _make_pattern(MapReducePattern)
        ctx = _make_context(PatternType.MAP_REDUCE)
        result = await p.execute(ctx)
        assert result.pattern_type == PatternType.MAP_REDUCE


# ── PipelinePattern ──────────────────────────────────────────────────────────


class TestPipelinePattern:
    @pytest.mark.asyncio
    async def test_pattern_type(self):
        p = _make_pattern(PipelinePattern)
        assert p.pattern_type == PatternType.PIPELINE

    @pytest.mark.asyncio
    async def test_returns_result(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE)
        result = await p.execute(ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_result_has_output(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE)
        result = await p.execute(ctx)
        assert result.final_output is not None
        assert len(result.final_output) > 0

    @pytest.mark.asyncio
    async def test_default_stages_count(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE)
        result = await p.execute(ctx)
        # Default: plan, execute, verify
        assert result.metadata["stages_completed"] == 3

    @pytest.mark.asyncio
    async def test_custom_stages_respected(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE)
        stages = ["ingest", "transform", "validate", "export"]
        result = await p.execute(ctx, stages=stages)
        assert result.metadata["stages_completed"] == 4
        assert result.metadata["stages"] == stages

    @pytest.mark.asyncio
    async def test_output_chains_through_stages(self):
        """Each stage name should appear in the final chained output."""
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE, participants=["agent-x"])
        stages = ["alpha", "beta"]
        result = await p.execute(ctx, stages=stages)
        # The final output should include "beta" as the last stage label
        assert "beta" in result.final_output

    @pytest.mark.asyncio
    async def test_contributions_include_participants(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE, participants=["agent-1", "agent-2"])
        result = await p.execute(ctx, stages=["s1", "s2"])
        assert len(result.participant_contributions) > 0

    @pytest.mark.asyncio
    async def test_single_stage_pipeline(self):
        p = _make_pattern(PipelinePattern)
        ctx = _make_context(PatternType.PIPELINE, participants=["solo"])
        result = await p.execute(ctx, stages=["only"])
        assert result.success is True
        assert result.metadata["stages_completed"] == 1


# ── PatternExecutor integration ──────────────────────────────────────────────


class TestPatternExecutorNewTypes:
    def test_map_reduce_registered(self):
        executor = PatternExecutor()
        pattern = executor.get_pattern(PatternType.MAP_REDUCE)
        assert isinstance(pattern, MapReducePattern)

    def test_pipeline_registered(self):
        executor = PatternExecutor()
        pattern = executor.get_pattern(PatternType.PIPELINE)
        assert isinstance(pattern, PipelinePattern)

    @pytest.mark.asyncio
    async def test_execute_map_reduce(self):
        executor = PatternExecutor()
        result = await executor.execute_pattern(
            PatternType.MAP_REDUCE,
            task_description="analyse code",
            participants=["w1", "w2"],
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_pipeline(self):
        executor = PatternExecutor()
        result = await executor.execute_pattern(
            PatternType.PIPELINE,
            task_description="process data",
            participants=["agent-1", "agent-2"],
        )
        assert result.success is True

    def test_suggest_pipeline_for_sequential_task(self):
        executor = PatternExecutor()
        suggestion = executor.suggest_pattern("step by step build", num_participants=2, task_complexity=0.5)
        assert suggestion == PatternType.PIPELINE

    def test_suggest_map_reduce_for_aggregate_task(self):
        executor = PatternExecutor()
        suggestion = executor.suggest_pattern("aggregate all results", num_participants=3, task_complexity=0.5)
        assert suggestion == PatternType.MAP_REDUCE
