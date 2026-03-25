"""Tests for core configuration enums."""

import pytest

from app.core.config_enums import FlowMode, SandboxLifecycleMode, StreamingMode


@pytest.mark.unit
class TestStreamingMode:
    """Tests for StreamingMode enum."""

    def test_cdp_only_value(self) -> None:
        assert StreamingMode.CDP_ONLY == "cdp_only"

    def test_cdp_only_is_str(self) -> None:
        assert isinstance(StreamingMode.CDP_ONLY, str)

    def test_from_string(self) -> None:
        assert StreamingMode("cdp_only") is StreamingMode.CDP_ONLY

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            StreamingMode("invalid_mode")


@pytest.mark.unit
class TestSandboxLifecycleMode:
    """Tests for SandboxLifecycleMode enum."""

    def test_static_value(self) -> None:
        assert SandboxLifecycleMode.STATIC == "static"

    def test_ephemeral_value(self) -> None:
        assert SandboxLifecycleMode.EPHEMERAL == "ephemeral"

    def test_both_are_str(self) -> None:
        for mode in SandboxLifecycleMode:
            assert isinstance(mode, str)

    def test_from_string_static(self) -> None:
        assert SandboxLifecycleMode("static") is SandboxLifecycleMode.STATIC

    def test_from_string_ephemeral(self) -> None:
        assert SandboxLifecycleMode("ephemeral") is SandboxLifecycleMode.EPHEMERAL

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SandboxLifecycleMode("dynamic")

    def test_member_count(self) -> None:
        assert len(SandboxLifecycleMode) == 2


@pytest.mark.unit
class TestFlowMode:
    """Tests for FlowMode enum."""

    def test_plan_act_value(self) -> None:
        assert FlowMode.PLAN_ACT == "plan_act"

    def test_coordinator_value(self) -> None:
        assert FlowMode.COORDINATOR == "coordinator"

    def test_both_are_str(self) -> None:
        for mode in FlowMode:
            assert isinstance(mode, str)

    def test_from_string_plan_act(self) -> None:
        assert FlowMode("plan_act") is FlowMode.PLAN_ACT

    def test_from_string_coordinator(self) -> None:
        assert FlowMode("coordinator") is FlowMode.COORDINATOR

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            FlowMode("round_robin")

    def test_member_count(self) -> None:
        assert len(FlowMode) == 2
