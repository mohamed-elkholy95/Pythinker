"""Tests for FlowStatus enum and BaseFlow abstract class."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from app.domain.models.event import BaseEvent
from app.domain.services.flows.base import BaseFlow, FlowStatus


class TestFlowStatus:
    def test_all_values_exist(self) -> None:
        expected = {
            "idle",
            "planning",
            "executing",
            "verifying",
            "reflecting",
            "summarizing",
            "completed",
            "failed",
        }
        actual = {s.value for s in FlowStatus}
        assert actual == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(FlowStatus.IDLE, str)
        assert FlowStatus.IDLE == "idle"

    def test_enum_member_names(self) -> None:
        assert FlowStatus.IDLE.name == "IDLE"
        assert FlowStatus.PLANNING.name == "PLANNING"
        assert FlowStatus.EXECUTING.name == "EXECUTING"
        assert FlowStatus.VERIFYING.name == "VERIFYING"
        assert FlowStatus.REFLECTING.name == "REFLECTING"
        assert FlowStatus.SUMMARIZING.name == "SUMMARIZING"
        assert FlowStatus.COMPLETED.name == "COMPLETED"
        assert FlowStatus.FAILED.name == "FAILED"

    def test_total_count(self) -> None:
        assert len(FlowStatus) == 8


class _DoneFlow(BaseFlow):
    async def run(self) -> AsyncGenerator[BaseEvent, None]:
        return
        yield

    def is_done(self) -> bool:
        return True


class _NotDoneFlow(BaseFlow):
    async def run(self) -> AsyncGenerator[BaseEvent, None]:
        return
        yield

    def is_done(self) -> bool:
        return False


class TestBaseFlow:
    def test_get_status_when_done(self) -> None:
        flow = _DoneFlow()
        assert flow.get_status() == FlowStatus.COMPLETED

    def test_get_status_when_not_done(self) -> None:
        flow = _NotDoneFlow()
        assert flow.get_status() == FlowStatus.IDLE

    def test_get_status_returns_flow_status_type(self) -> None:
        flow = _DoneFlow()
        assert isinstance(flow.get_status(), FlowStatus)
