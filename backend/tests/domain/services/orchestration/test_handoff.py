"""Tests for handoff module — HandoffContext, Handoff, HandoffResult, HandoffProtocol.

Covers:
  - HandoffReason / HandoffStatus enum members
  - HandoffContext: step results, shared resources, resource locking, progress,
    to_prompt, to_dict, from_dict round-trip
  - Handoff: accept, reject, complete, fail state transitions
  - HandoffResult Pydantic model
  - HandoffProtocol: create_handoff, create_parallel_handoffs, get_pending,
    get_handoff, complete_handoff, fail_handoff, aggregate_results, get_history,
    rollback_handoff, transfer_context, get_workflow_progress, build_handoff_prompt
  - Singleton: get_handoff_protocol
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.domain.exceptions.base import BusinessRuleViolation, HandoffNotFoundException
from app.domain.services.orchestration.agent_types import AgentCapability, AgentType
from app.domain.services.orchestration.handoff import (
    Handoff,
    HandoffContext,
    HandoffProtocol,
    HandoffReason,
    HandoffResult,
    HandoffStatus,
    get_handoff_protocol,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    """HandoffReason and HandoffStatus members."""

    def test_handoff_reasons(self) -> None:
        assert HandoffReason.SPECIALIZATION.value == "specialization"
        assert HandoffReason.PARALLEL_EXECUTION.value == "parallel"
        assert HandoffReason.USER_REQUEST.value == "user_request"

    def test_handoff_statuses(self) -> None:
        assert HandoffStatus.PENDING.value == "pending"
        assert HandoffStatus.COMPLETED.value == "completed"
        assert HandoffStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# HandoffContext
# ---------------------------------------------------------------------------


class TestHandoffContext:
    """HandoffContext dataclass logic."""

    def _make(self, **kwargs) -> HandoffContext:
        defaults = dict(task_description="T", original_request="R", current_progress="P")
        defaults.update(kwargs)
        return HandoffContext(**defaults)

    def test_add_and_get_step_result(self) -> None:
        ctx = self._make()
        ctx.add_step_result("s1", {"data": 42})
        assert ctx.get_step_result("s1") == {"data": 42}
        assert ctx.completed_steps == 1
        assert len(ctx.step_history) == 1

    def test_get_step_result_missing(self) -> None:
        ctx = self._make()
        assert ctx.get_step_result("missing") is None

    def test_shared_resources(self) -> None:
        ctx = self._make()
        ctx.set_shared_resource("db_conn", "sqlite://test")
        assert ctx.get_shared_resource("db_conn") == "sqlite://test"
        assert ctx.get_shared_resource("missing") is None

    def test_lock_resource(self) -> None:
        ctx = self._make()
        assert ctx.lock_resource("file.txt") is True
        assert ctx.lock_resource("file.txt") is False  # Already locked

    def test_unlock_resource(self) -> None:
        ctx = self._make()
        ctx.lock_resource("file.txt")
        ctx.unlock_resource("file.txt")
        assert ctx.lock_resource("file.txt") is True  # Can lock again

    def test_unlock_nonexistent(self) -> None:
        ctx = self._make()
        ctx.unlock_resource("nothing")  # Should not raise

    def test_progress_percent_zero(self) -> None:
        ctx = self._make(total_steps=0)
        assert ctx.get_progress_percent() == 0.0

    def test_progress_percent_midway(self) -> None:
        ctx = self._make(total_steps=10, completed_steps=5)
        assert ctx.get_progress_percent() == 50.0

    def test_to_prompt_includes_sections(self) -> None:
        ctx = self._make(
            relevant_files=["a.py"],
            key_findings=["key1"],
            decisions_made=["dec1"],
            memory_summary="summary",
            total_steps=5,
            completed_steps=2,
        )
        prompt = ctx.to_prompt()
        assert "a.py" in prompt
        assert "key1" in prompt
        assert "dec1" in prompt
        assert "summary" in prompt
        assert "2/5" in prompt

    def test_to_prompt_step_results(self) -> None:
        ctx = self._make()
        ctx.add_step_result("s1", "result1")
        prompt = ctx.to_prompt()
        assert "s1" in prompt

    def test_to_prompt_shared_resources(self) -> None:
        ctx = self._make()
        ctx.set_shared_resource("cache", "redis")
        prompt = ctx.to_prompt()
        assert "cache" in prompt

    def test_to_dict_from_dict_roundtrip(self) -> None:
        ctx = self._make(
            relevant_files=["x.py"],
            key_findings=["f1"],
            decisions_made=["d1"],
            memory_summary="mem",
            workflow_id="wf1",
            stage_id="st1",
            total_steps=10,
            completed_steps=3,
        )
        ctx.add_step_result("s1", "r1")
        ctx.set_shared_resource("rs", "val")
        ctx.lock_resource("lock1")
        d = ctx.to_dict()
        ctx2 = HandoffContext.from_dict(d)
        assert ctx2.task_description == "T"
        assert ctx2.original_request == "R"
        assert ctx2.workflow_id == "wf1"
        assert ctx2.completed_steps == 4  # from_dict gets 3 from dict but add_step_result incremented
        # from_dict actually takes completed_steps from data, which is 3+1=4 since add_step_result ran
        # Let's just verify roundtrip of key fields
        assert ctx2.relevant_files == ["x.py"]
        assert ctx2.key_findings == ["f1"]
        assert "lock1" in ctx2.resource_locks


# ---------------------------------------------------------------------------
# Handoff state transitions
# ---------------------------------------------------------------------------


class TestHandoff:
    """Handoff state transitions."""

    def test_defaults(self) -> None:
        h = Handoff()
        assert h.status == HandoffStatus.PENDING
        assert len(h.id) > 0

    def test_accept(self) -> None:
        h = Handoff(target_agent=AgentType.EXECUTOR)
        h.accept()
        assert h.status == HandoffStatus.ACCEPTED

    def test_reject(self) -> None:
        h = Handoff()
        h.reject("not available")
        assert h.status == HandoffStatus.REJECTED
        assert h.error == "not available"

    def test_complete(self) -> None:
        h = Handoff()
        h.complete("done")
        assert h.status == HandoffStatus.COMPLETED
        assert h.result == "done"

    def test_fail(self) -> None:
        h = Handoff()
        h.fail("crashed")
        assert h.status == HandoffStatus.FAILED
        assert h.error == "crashed"


# ---------------------------------------------------------------------------
# HandoffResult
# ---------------------------------------------------------------------------


class TestHandoffResult:
    """HandoffResult Pydantic model."""

    def test_success(self) -> None:
        r = HandoffResult(handoff_id="abc", success=True, output="data")
        assert r.success is True
        assert r.output == "data"
        assert r.artifacts == []

    def test_failure(self) -> None:
        r = HandoffResult(handoff_id="abc", success=False, summary="Handoff failed: timeout")
        assert r.success is False


# ---------------------------------------------------------------------------
# HandoffProtocol
# ---------------------------------------------------------------------------


class TestHandoffProtocol:
    """HandoffProtocol core operations."""

    def _ctx(self) -> HandoffContext:
        return HandoffContext(task_description="T", original_request="R", current_progress="P")

    def test_create_handoff(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        assert h.status == HandoffStatus.PENDING
        assert h.source_agent == AgentType.EXECUTOR
        assert h.target_agent == AgentType.PLANNER

    def test_create_handoff_by_capability(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.CAPABILITY_REQUIRED,
            context=self._ctx(),
            target_capability=AgentCapability.CODE_EXECUTION,
        )
        assert h.target_capability == AgentCapability.CODE_EXECUTION

    def test_create_handoff_requires_target(self) -> None:
        proto = HandoffProtocol()
        with pytest.raises(BusinessRuleViolation):
            proto.create_handoff(
                source_agent=AgentType.EXECUTOR,
                reason=HandoffReason.SPECIALIZATION,
                context=self._ctx(),
            )

    def test_get_pending(self) -> None:
        proto = HandoffProtocol()
        proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        pending = proto.get_pending()
        assert len(pending) == 1

    def test_get_pending_filtered(self) -> None:
        proto = HandoffProtocol()
        proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.VERIFICATION,
            context=self._ctx(),
            target_agent=AgentType.EXECUTOR,
        )
        assert len(proto.get_pending(target_agent=AgentType.PLANNER)) == 1

    def test_get_pending_sorted_by_priority(self) -> None:
        proto = HandoffProtocol()
        h1 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
            priority=1,
        )
        h2 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.STUCK,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
            priority=10,
        )
        pending = proto.get_pending()
        assert pending[0].id == h2.id

    def test_get_handoff_from_pending(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        assert proto.get_handoff(h.id) is h

    def test_get_handoff_from_history(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        proto.complete_handoff(h.id, "done")
        found = proto.get_handoff(h.id)
        assert found is not None

    def test_get_handoff_not_found(self) -> None:
        proto = HandoffProtocol()
        assert proto.get_handoff("nonexistent") is None

    def test_complete_handoff(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        result = proto.complete_handoff(h.id, "output", summary="all done")
        assert result.success is True
        assert result.output == "output"
        assert h.id not in proto._pending

    def test_complete_handoff_not_found(self) -> None:
        proto = HandoffProtocol()
        with pytest.raises(HandoffNotFoundException):
            proto.complete_handoff("nonexistent", "x")

    def test_fail_handoff(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        result = proto.fail_handoff(h.id, "crashed")
        assert result.success is False
        assert h.id not in proto._pending

    def test_fail_handoff_not_found(self) -> None:
        proto = HandoffProtocol()
        with pytest.raises(HandoffNotFoundException):
            proto.fail_handoff("nonexistent", "x")


class TestHandoffProtocolParallel:
    """HandoffProtocol.create_parallel_handoffs."""

    def _ctx(self) -> HandoffContext:
        return HandoffContext(task_description="T", original_request="R", current_progress="P")

    def test_creates_multiple(self) -> None:
        proto = HandoffProtocol()
        subtasks = [
            {"target_agent": AgentType.EXECUTOR, "instructions": "Do A"},
            {"target_agent": AgentType.PLANNER, "instructions": "Plan B"},
        ]
        handoffs = proto.create_parallel_handoffs(AgentType.EXECUTOR, subtasks, self._ctx())
        assert len(handoffs) == 2
        assert all(h.reason == HandoffReason.PARALLEL_EXECUTION for h in handoffs)


class TestHandoffProtocolAggregate:
    """HandoffProtocol.aggregate_results."""

    def _ctx(self) -> HandoffContext:
        return HandoffContext(task_description="T", original_request="R", current_progress="P")

    def test_aggregate(self) -> None:
        proto = HandoffProtocol()
        h1 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        h2 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        proto.complete_handoff(h1.id, "result1")
        proto.fail_handoff(h2.id, "err")
        agg = proto.aggregate_results([h1.id, h2.id])
        assert agg["total"] == 2
        assert agg["completed"] == 1
        assert agg["failed"] == 1
        assert len(agg["results"]) == 1


class TestHandoffProtocolHistory:
    """HandoffProtocol.get_history."""

    def _ctx(self) -> HandoffContext:
        return HandoffContext(task_description="T", original_request="R", current_progress="P")

    def test_history_records_on_create(self) -> None:
        proto = HandoffProtocol()
        proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        assert len(proto.get_history()) == 1

    def test_history_filter_by_source(self) -> None:
        proto = HandoffProtocol()
        proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        proto.create_handoff(
            source_agent=AgentType.PLANNER,
            reason=HandoffReason.TASK_COMPLETE,
            context=self._ctx(),
            target_agent=AgentType.EXECUTOR,
        )
        assert len(proto.get_history(source_agent=AgentType.EXECUTOR)) == 1

    def test_history_limit(self) -> None:
        proto = HandoffProtocol()
        for _ in range(5):
            proto.create_handoff(
                source_agent=AgentType.EXECUTOR,
                reason=HandoffReason.SPECIALIZATION,
                context=self._ctx(),
                target_agent=AgentType.PLANNER,
            )
        assert len(proto.get_history(limit=2)) == 2

    def test_history_max_size(self) -> None:
        proto = HandoffProtocol(max_history=3)
        for _ in range(5):
            proto.create_handoff(
                source_agent=AgentType.EXECUTOR,
                reason=HandoffReason.SPECIALIZATION,
                context=self._ctx(),
                target_agent=AgentType.PLANNER,
            )
        assert len(proto._history) == 3


class TestHandoffProtocolRollback:
    """HandoffProtocol.rollback_handoff."""

    def _ctx(self, **kwargs) -> HandoffContext:
        defaults = dict(task_description="T", original_request="R", current_progress="P")
        defaults.update(kwargs)
        return HandoffContext(**defaults)

    async def test_rollback_with_func(self) -> None:
        proto = HandoffProtocol()
        ctx = self._ctx(rollback_enabled=True, rollback_steps=["undo_a", "undo_b"])
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.ERROR_RECOVERY,
            context=ctx,
            target_agent=AgentType.PLANNER,
        )
        rollback_fn = AsyncMock(return_value=True)
        result = await proto.rollback_handoff(h.id, rollback_fn)
        assert result is True
        rollback_fn.assert_awaited_once_with(["undo_a", "undo_b"])

    async def test_rollback_disabled(self) -> None:
        proto = HandoffProtocol()
        ctx = self._ctx(rollback_enabled=False)
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.ERROR_RECOVERY,
            context=ctx,
            target_agent=AgentType.PLANNER,
        )
        result = await proto.rollback_handoff(h.id)
        assert result is False

    async def test_rollback_with_checkpoint(self) -> None:
        proto = HandoffProtocol()
        ctx = self._ctx(rollback_enabled=True, checkpoint_id="cp-123")
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.ERROR_RECOVERY,
            context=ctx,
            target_agent=AgentType.PLANNER,
        )
        result = await proto.rollback_handoff(h.id)
        assert result is True

    async def test_rollback_not_found(self) -> None:
        proto = HandoffProtocol()
        result = await proto.rollback_handoff("nonexistent")
        assert result is False

    async def test_rollback_no_context(self) -> None:
        proto = HandoffProtocol()
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.ERROR_RECOVERY,
            context=self._ctx(),
            target_agent=AgentType.PLANNER,
        )
        h.context = None
        result = await proto.rollback_handoff(h.id)
        assert result is False

    async def test_rollback_func_fails(self) -> None:
        proto = HandoffProtocol()
        ctx = self._ctx(rollback_enabled=True, rollback_steps=["step"])
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.ERROR_RECOVERY,
            context=ctx,
            target_agent=AgentType.PLANNER,
        )
        rollback_fn = AsyncMock(return_value=False)
        result = await proto.rollback_handoff(h.id, rollback_fn)
        assert result is False


class TestHandoffProtocolTransfer:
    """HandoffProtocol.transfer_context."""

    def _ctx(self, **kwargs) -> HandoffContext:
        defaults = dict(task_description="T", original_request="R", current_progress="P")
        defaults.update(kwargs)
        return HandoffContext(**defaults)

    def test_transfer_merge(self) -> None:
        proto = HandoffProtocol()
        src = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.TASK_COMPLETE,
            context=self._ctx(key_findings=["f1"]),
            target_agent=AgentType.PLANNER,
        )
        src.context.add_step_result("s1", "r1")
        tgt = proto.create_handoff(
            source_agent=AgentType.PLANNER,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(key_findings=["f2"]),
            target_agent=AgentType.EXECUTOR,
        )
        ok = proto.transfer_context(src.id, tgt, merge=True)
        assert ok is True
        assert "f1" in tgt.context.key_findings
        assert "f2" in tgt.context.key_findings
        assert tgt.context.get_step_result("s1") == "r1"

    def test_transfer_replace(self) -> None:
        proto = HandoffProtocol()
        src = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.TASK_COMPLETE,
            context=self._ctx(key_findings=["f1"], memory_summary="old_mem"),
            target_agent=AgentType.PLANNER,
        )
        tgt = proto.create_handoff(
            source_agent=AgentType.PLANNER,
            reason=HandoffReason.SPECIALIZATION,
            context=self._ctx(task_description="TargetTask", key_findings=["f2"]),
            target_agent=AgentType.EXECUTOR,
        )
        ok = proto.transfer_context(src.id, tgt, merge=False)
        assert ok is True
        assert tgt.context.memory_summary == "old_mem"
        assert tgt.context.task_description == "TargetTask"

    def test_transfer_source_not_found(self) -> None:
        proto = HandoffProtocol()
        tgt = Handoff(context=self._ctx())
        assert proto.transfer_context("missing", tgt) is False

    def test_transfer_target_no_context(self) -> None:
        proto = HandoffProtocol()
        src = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.TASK_COMPLETE,
            context=self._ctx(key_findings=["f1"]),
            target_agent=AgentType.PLANNER,
        )
        tgt = Handoff()
        tgt.context = None
        ok = proto.transfer_context(src.id, tgt, merge=True)
        assert ok is True
        assert tgt.context is not None


class TestHandoffProtocolWorkflow:
    """HandoffProtocol.get_workflow_progress."""

    def _ctx(self, **kwargs) -> HandoffContext:
        defaults = dict(task_description="T", original_request="R", current_progress="P")
        defaults.update(kwargs)
        return HandoffContext(**defaults)

    def test_workflow_progress(self) -> None:
        proto = HandoffProtocol()
        ctx1 = self._ctx(workflow_id="wf1", total_steps=10, completed_steps=5)
        ctx2 = self._ctx(workflow_id="wf1", total_steps=10, completed_steps=8)
        h1 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=ctx1,
            target_agent=AgentType.PLANNER,
        )
        h2 = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=ctx2,
            target_agent=AgentType.PLANNER,
        )
        proto.complete_handoff(h1.id, "ok")
        progress = proto.get_workflow_progress("wf1")
        assert progress["workflow_id"] == "wf1"
        assert progress["total_handoffs"] == 2
        assert progress["completed_handoffs"] == 1
        assert progress["completed_steps"] == 8


class TestBuildHandoffPrompt:
    """HandoffProtocol.build_handoff_prompt."""

    def test_includes_key_sections(self) -> None:
        proto = HandoffProtocol()
        ctx = HandoffContext(task_description="T", original_request="R", current_progress="P")
        h = proto.create_handoff(
            source_agent=AgentType.EXECUTOR,
            reason=HandoffReason.SPECIALIZATION,
            context=ctx,
            target_agent=AgentType.PLANNER,
            instructions="Do X",
            expected_output="Report",
        )
        prompt = proto.build_handoff_prompt(h)
        assert "Agent Handoff" in prompt
        assert "Do X" in prompt
        assert "Report" in prompt
        assert "executor" in prompt.lower()


class TestSingleton:
    """get_handoff_protocol singleton."""

    def test_returns_instance(self) -> None:
        proto = get_handoff_protocol()
        assert isinstance(proto, HandoffProtocol)
