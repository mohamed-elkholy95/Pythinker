"""Tests for Session model (app.domain.models.session).

Covers session enums, Session creation, field validators (mode, research_mode,
sandbox_lifecycle_mode, takeover_reason coercion), serializers, and defaults.
"""

from app.domain.models.session import (
    AgentMode,
    PendingAction,
    PendingActionStatus,
    ReasoningVisibility,
    ResearchMode,
    SandboxLifecycleMode,
    Session,
    SessionStatus,
    TakeoverReason,
    TakeoverState,
    ThinkingLevel,
)


# ── Enums ────────────────────────────────────────────────────────────


class TestSessionEnums:
    """Tests for session-related enums."""

    def test_session_status_values(self) -> None:
        assert SessionStatus.PENDING == "pending"
        assert SessionStatus.INITIALIZING == "initializing"
        assert SessionStatus.RUNNING == "running"
        assert SessionStatus.WAITING == "waiting"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"
        assert SessionStatus.CANCELLED == "cancelled"

    def test_takeover_state_values(self) -> None:
        assert TakeoverState.IDLE == "idle"
        assert TakeoverState.TAKEOVER_REQUESTED == "takeover_requested"
        assert TakeoverState.TAKEOVER_ACTIVE == "takeover_active"
        assert TakeoverState.RESUMING == "resuming"

    def test_agent_mode_values(self) -> None:
        assert AgentMode.DISCUSS == "discuss"
        assert AgentMode.AGENT == "agent"

    def test_research_mode_values(self) -> None:
        assert ResearchMode.FAST_SEARCH == "fast_search"
        assert ResearchMode.DEEP_RESEARCH == "deep_research"
        assert ResearchMode.DEAL_FINDING == "deal_finding"

    def test_sandbox_lifecycle_mode_values(self) -> None:
        assert SandboxLifecycleMode.STATIC == "static"
        assert SandboxLifecycleMode.EPHEMERAL == "ephemeral"

    def test_takeover_reason_values(self) -> None:
        assert TakeoverReason.MANUAL == "manual"
        assert TakeoverReason.CAPTCHA == "captcha"
        assert TakeoverReason.LOGIN == "login"
        assert TakeoverReason.TWO_FA == "2fa"
        assert TakeoverReason.PAYMENT == "payment"
        assert TakeoverReason.VERIFICATION == "verification"

    def test_reasoning_visibility_values(self) -> None:
        assert ReasoningVisibility.OFF == "off"
        assert ReasoningVisibility.ON == "on"
        assert ReasoningVisibility.STREAM == "stream"

    def test_thinking_level_values(self) -> None:
        assert ThinkingLevel.OFF == "off"
        assert ThinkingLevel.LOW == "low"
        assert ThinkingLevel.MEDIUM == "medium"
        assert ThinkingLevel.HIGH == "high"

    def test_pending_action_status_values(self) -> None:
        assert PendingActionStatus.AWAITING_CONFIRMATION == "awaiting_confirmation"
        assert PendingActionStatus.REJECTED == "rejected"


# ── PendingAction ────────────────────────────────────────────────────


class TestPendingAction:
    """Tests for PendingAction model."""

    def test_creation(self) -> None:
        action = PendingAction(
            tool_call_id="tc-1",
            tool_name="shell",
            function_name="execute",
            function_args={"command": "rm -rf /tmp/test"},
            security_risk="high",
            security_reason="Destructive command",
            security_suggestions=["Use trash instead"],
        )
        assert action.tool_call_id == "tc-1"
        assert action.function_args == {"command": "rm -rf /tmp/test"}
        assert action.security_risk == "high"

    def test_defaults(self) -> None:
        action = PendingAction(
            tool_call_id="tc-1",
            tool_name="shell",
            function_name="execute",
        )
        assert action.function_args == {}
        assert action.security_risk is None


# ── Session creation ─────────────────────────────────────────────────


class TestSessionCreation:
    """Tests for Session model creation and defaults."""

    def test_minimal_creation(self) -> None:
        session = Session(user_id="user-1", agent_id="agent-1")
        assert session.user_id == "user-1"
        assert session.agent_id == "agent-1"
        assert session.id is not None
        assert len(session.id) == 16
        assert session.status == SessionStatus.PENDING
        assert session.mode == AgentMode.AGENT
        assert session.research_mode == ResearchMode.DEEP_RESEARCH
        assert session.source == "web"
        assert session.takeover_state == TakeoverState.IDLE
        assert session.events == []
        assert session.files == []
        assert session.is_shared is False
        assert session.budget_paused is False
        assert session.budget_warning_threshold == 0.8

    def test_unique_ids(self) -> None:
        sessions = [Session(user_id="u", agent_id="a") for _ in range(10)]
        ids = [s.id for s in sessions]
        assert len(ids) == len(set(ids))


# ── Validators ───────────────────────────────────────────────────────


class TestSessionValidators:
    """Tests for Session field validators."""

    def test_mode_coercion_from_string(self) -> None:
        session = Session(user_id="u", agent_id="a", mode="discuss")
        assert session.mode == AgentMode.DISCUSS

    def test_mode_coercion_from_enum(self) -> None:
        session = Session(user_id="u", agent_id="a", mode=AgentMode.AGENT)
        assert session.mode == AgentMode.AGENT

    def test_mode_coercion_invalid_fallback(self) -> None:
        session = Session(user_id="u", agent_id="a", mode="invalid_mode")
        assert session.mode == AgentMode.AGENT  # fallback

    def test_mode_coercion_strips_whitespace(self) -> None:
        session = Session(user_id="u", agent_id="a", mode="  discuss  ")
        assert session.mode == AgentMode.DISCUSS

    def test_research_mode_coercion_from_string(self) -> None:
        session = Session(user_id="u", agent_id="a", research_mode="fast_search")
        assert session.research_mode == ResearchMode.FAST_SEARCH

    def test_research_mode_coercion_invalid_fallback(self) -> None:
        session = Session(user_id="u", agent_id="a", research_mode="bogus")
        assert session.research_mode == ResearchMode.DEEP_RESEARCH

    def test_sandbox_lifecycle_mode_from_string(self) -> None:
        session = Session(user_id="u", agent_id="a", sandbox_lifecycle_mode="ephemeral")
        assert session.sandbox_lifecycle_mode == SandboxLifecycleMode.EPHEMERAL

    def test_sandbox_lifecycle_mode_none(self) -> None:
        session = Session(user_id="u", agent_id="a", sandbox_lifecycle_mode=None)
        assert session.sandbox_lifecycle_mode is None

    def test_takeover_reason_coercion_from_string(self) -> None:
        session = Session(user_id="u", agent_id="a", takeover_reason="captcha")
        assert session.takeover_reason == TakeoverReason.CAPTCHA

    def test_takeover_reason_coercion_invalid_fallback(self) -> None:
        session = Session(user_id="u", agent_id="a", takeover_reason="unknown")
        assert session.takeover_reason == TakeoverReason.MANUAL

    def test_takeover_reason_none(self) -> None:
        session = Session(user_id="u", agent_id="a", takeover_reason=None)
        assert session.takeover_reason is None


# ── Serializers ──────────────────────────────────────────────────────


class TestSessionSerializers:
    """Tests for Session field serializers."""

    def test_sandbox_lifecycle_mode_serializes_enum(self) -> None:
        session = Session(user_id="u", agent_id="a", sandbox_lifecycle_mode=SandboxLifecycleMode.EPHEMERAL)
        data = session.model_dump()
        assert data["sandbox_lifecycle_mode"] == "ephemeral"

    def test_sandbox_lifecycle_mode_serializes_none(self) -> None:
        session = Session(user_id="u", agent_id="a", sandbox_lifecycle_mode=None)
        data = session.model_dump()
        assert data["sandbox_lifecycle_mode"] is None

    def test_takeover_reason_serializes_enum(self) -> None:
        session = Session(user_id="u", agent_id="a", takeover_reason=TakeoverReason.CAPTCHA)
        data = session.model_dump()
        assert data["takeover_reason"] == "captcha"

    def test_takeover_reason_serializes_none(self) -> None:
        session = Session(user_id="u", agent_id="a", takeover_reason=None)
        data = session.model_dump()
        assert data["takeover_reason"] is None


# ── get_last_plan ────────────────────────────────────────────────────


class TestSessionGetLastPlan:
    """Tests for Session.get_last_plan method."""

    def test_no_events(self) -> None:
        session = Session(user_id="u", agent_id="a")
        assert session.get_last_plan() is None
