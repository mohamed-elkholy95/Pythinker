"""Tests for the SessionReplay domain service."""

from datetime import UTC, datetime, timedelta

from app.domain.models.event import (
    ErrorEvent,
    MessageEvent,
    PhaseEvent,
    PhaseStatus,
    StepEvent,
    StepStatus,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.plan import Step
from app.domain.models.session import Session, SessionStatus
from app.domain.services.session_replay import (
    _compute_duration_ms,
    _truncate,
    build_session_replay,
)


def _make_session(events: list, status: SessionStatus = SessionStatus.COMPLETED) -> Session:
    """Helper to create a minimal Session with events."""
    return Session(
        id="test-session-123",
        user_id="user-1",
        agent_id="agent-1",
        title="Test Task",
        status=status,
        events=events,
        created_at=datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC),
    )


class TestTruncate:
    """Tests for the _truncate helper."""

    def test_none_returns_empty(self):
        assert _truncate(None, 100) == ""

    def test_empty_returns_empty(self):
        assert _truncate("", 100) == ""

    def test_short_string_unchanged(self):
        assert _truncate("hello", 100) == "hello"

    def test_exact_length_unchanged(self):
        text = "a" * 50
        assert _truncate(text, 50) == text

    def test_long_string_truncated_with_ellipsis(self):
        text = "a" * 100
        result = _truncate(text, 50)
        assert len(result) == 50
        assert result.endswith("...")


class TestComputeDuration:
    """Tests for the _compute_duration_ms helper."""

    def test_none_start(self):
        assert _compute_duration_ms(None, datetime.now(UTC)) is None

    def test_none_end(self):
        assert _compute_duration_ms(datetime.now(UTC), None) is None

    def test_both_none(self):
        assert _compute_duration_ms(None, None) is None

    def test_valid_duration(self):
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = start + timedelta(seconds=2.5)
        result = _compute_duration_ms(start, end)
        assert result == 2500.0

    def test_negative_duration_returns_none(self):
        start = datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC)
        end = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert _compute_duration_ms(start, end) is None


class TestBuildSessionReplay:
    """Tests for the build_session_replay function."""

    def test_empty_events(self):
        """Session with no events returns empty replay."""
        session = _make_session([])
        replay = build_session_replay(session)

        assert replay.session_id == "test-session-123"
        assert replay.status == "completed"
        assert replay.task == "Test Task"
        assert replay.total_steps == 0
        assert replay.total_tool_calls == 0
        assert replay.total_errors == 0
        assert replay.has_errors is False
        assert replay.steps == []
        assert replay.error_summary == []

    def test_single_step_with_tool(self):
        """Session with one step and one tool call."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        t1 = t0 + timedelta(seconds=1)
        t2 = t0 + timedelta(seconds=3)
        t3 = t0 + timedelta(seconds=5)

        step = Step(id="step-1", description="Search the web")
        events = [
            StepEvent(
                step=step,
                status=StepStatus.STARTED,
                timestamp=t1,
            ),
            ToolEvent(
                tool_call_id="tc-1",
                tool_name="search",
                function_name="web_search",
                function_args={"query": "python asyncio"},
                status=ToolStatus.CALLED,
                duration_ms=150.0,
                display_command="Searching 'python asyncio'",
                stdout="Found 10 results",
                timestamp=t2,
            ),
            StepEvent(
                step=step,
                status=StepStatus.COMPLETED,
                timestamp=t3,
                duration_ms=4000.0,
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert replay.total_steps == 1
        assert replay.total_tool_calls == 1
        assert replay.total_errors == 0

        step_replay = replay.steps[0]
        assert step_replay.step_number == 1
        assert step_replay.step_description == "Search the web"
        assert step_replay.step_status == "completed"
        assert step_replay.duration_ms == 4000.0

        assert len(step_replay.tool_calls) == 1
        tc = step_replay.tool_calls[0]
        assert tc.tool_name == "search"
        assert tc.duration_ms == 150.0
        assert "python asyncio" in tc.input_summary

    def test_error_events_captured(self):
        """Errors are captured in both step errors and error_summary."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step = Step(id="step-1", description="Do something")
        events = [
            StepEvent(step=step, status=StepStatus.STARTED, timestamp=t0),
            ErrorEvent(
                error="Token limit exceeded",
                error_type="token_limit",
                severity="error",
                recoverable=True,
                retry_hint="Try a simpler request",
                timestamp=t0 + timedelta(seconds=2),
            ),
            StepEvent(
                step=step,
                status=StepStatus.FAILED,
                timestamp=t0 + timedelta(seconds=3),
            ),
        ]

        session = _make_session(events, status=SessionStatus.FAILED)
        replay = build_session_replay(session)

        assert replay.total_errors == 1
        assert replay.has_errors is True
        assert replay.status == "failed"

        # Error in step
        assert len(replay.steps[0].errors) == 1
        err = replay.steps[0].errors[0]
        assert err.error_type == "token_limit"
        assert err.recoverable is True
        assert err.recovery_hint == "Try a simpler request"

        # Error in flat summary
        assert len(replay.error_summary) == 1
        assert replay.error_summary[0].error_type == "token_limit"

    def test_assistant_messages_captured(self):
        """Assistant messages are captured in step messages."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step = Step(id="step-1", description="Analyze data")
        events = [
            StepEvent(step=step, status=StepStatus.STARTED, timestamp=t0),
            MessageEvent(
                role="assistant",
                message="I found the relevant data about renewable energy.",
                timestamp=t0 + timedelta(seconds=1),
            ),
            StepEvent(
                step=step,
                status=StepStatus.COMPLETED,
                timestamp=t0 + timedelta(seconds=2),
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert len(replay.steps[0].messages) == 1
        assert "renewable energy" in replay.steps[0].messages[0]

    def test_user_messages_not_captured(self):
        """User messages are NOT included in replay messages."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step = Step(id="step-1", description="Process request")
        events = [
            StepEvent(step=step, status=StepStatus.STARTED, timestamp=t0),
            MessageEvent(
                role="user",
                message="Please search for Python tutorials",
                timestamp=t0 + timedelta(seconds=1),
            ),
            StepEvent(
                step=step,
                status=StepStatus.COMPLETED,
                timestamp=t0 + timedelta(seconds=2),
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert len(replay.steps[0].messages) == 0

    def test_multiple_steps(self):
        """Multiple steps are grouped correctly."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step1 = Step(id="s1", description="Step 1")
        step2 = Step(id="s2", description="Step 2")

        events = [
            StepEvent(step=step1, status=StepStatus.STARTED, timestamp=t0),
            ToolEvent(
                tool_call_id="tc-1",
                tool_name="search",
                function_name="web_search",
                function_args={"q": "test"},
                status=ToolStatus.CALLED,
                timestamp=t0 + timedelta(seconds=1),
            ),
            StepEvent(
                step=step1,
                status=StepStatus.COMPLETED,
                timestamp=t0 + timedelta(seconds=2),
            ),
            StepEvent(step=step2, status=StepStatus.STARTED, timestamp=t0 + timedelta(seconds=3)),
            ToolEvent(
                tool_call_id="tc-2",
                tool_name="browser",
                function_name="navigate",
                function_args={"url": "https://example.com"},
                status=ToolStatus.CALLED,
                timestamp=t0 + timedelta(seconds=4),
            ),
            StepEvent(
                step=step2,
                status=StepStatus.COMPLETED,
                timestamp=t0 + timedelta(seconds=5),
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert replay.total_steps == 2
        assert replay.total_tool_calls == 2
        assert replay.steps[0].step_number == 1
        assert replay.steps[1].step_number == 2
        assert len(replay.steps[0].tool_calls) == 1
        assert len(replay.steps[1].tool_calls) == 1
        assert replay.steps[0].tool_calls[0].tool_name == "search"
        assert replay.steps[1].tool_calls[0].tool_name == "browser"

    def test_phase_tracking(self):
        """Phase events update the current phase on steps."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step = Step(id="s1", description="Research step")

        events = [
            PhaseEvent(
                phase_id="p1",
                phase_type="research_foundation",
                label="Research",
                status=PhaseStatus.STARTED,
                timestamp=t0,
            ),
            StepEvent(step=step, status=StepStatus.STARTED, timestamp=t0 + timedelta(seconds=1)),
            StepEvent(
                step=step,
                status=StepStatus.COMPLETED,
                timestamp=t0 + timedelta(seconds=3),
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert replay.steps[0].phase == "research_foundation"

    def test_pre_step_events_go_to_step_zero(self):
        """Events before any StepEvent are assigned to step 0."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)

        events = [
            ErrorEvent(
                error="Connection timeout",
                error_type="timeout",
                severity="warning",
                recoverable=True,
                timestamp=t0,
            ),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        assert replay.total_errors == 1
        assert len(replay.steps) == 1
        assert replay.steps[0].step_number == 0
        assert replay.steps[0].step_description == "Pre-step events"

    def test_session_with_no_title_uses_latest_message(self):
        """Session without title falls back to latest_message."""
        session = Session(
            id="s1",
            user_id="u1",
            agent_id="a1",
            title=None,
            latest_message="Find me the best deals",
            status=SessionStatus.COMPLETED,
            events=[],
        )

        replay = build_session_replay(session)
        assert replay.task == "Find me the best deals"

    def test_tool_input_summary_from_function_args(self):
        """Tool input summary falls back to function_args when display_command is absent."""
        t0 = datetime(2026, 3, 26, 10, 0, 0, tzinfo=UTC)
        step = Step(id="s1", description="Execute")

        events = [
            StepEvent(step=step, status=StepStatus.STARTED, timestamp=t0),
            ToolEvent(
                tool_call_id="tc-1",
                tool_name="shell",
                function_name="execute",
                function_args={"command": "ls -la", "cwd": "/home"},
                status=ToolStatus.CALLED,
                timestamp=t0 + timedelta(seconds=1),
            ),
            StepEvent(step=step, status=StepStatus.COMPLETED, timestamp=t0 + timedelta(seconds=2)),
        ]

        session = _make_session(events)
        replay = build_session_replay(session)

        tc = replay.steps[0].tool_calls[0]
        assert "command=ls -la" in tc.input_summary
        assert "cwd=/home" in tc.input_summary

    def test_has_errors_property(self):
        """The has_errors property correctly reflects error state."""
        session_ok = _make_session([])
        assert build_session_replay(session_ok).has_errors is False

        session_err = _make_session(
            [
                ErrorEvent(
                    error="boom",
                    error_type="unknown",
                    timestamp=datetime.now(UTC),
                ),
            ]
        )
        assert build_session_replay(session_err).has_errors is True
