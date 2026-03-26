"""Session replay service for debugging failed agent sessions.

Aggregates session events into a structured timeline grouped by step,
with error context and timing information for post-mortem analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime

import structlog

from app.domain.models.event import (
    ErrorEvent,
    MessageEvent,
    PhaseEvent,
    StepEvent,
    ToolEvent,
)
from app.domain.models.session import Session

logger = structlog.get_logger(__name__)

# Truncation limits to keep replay payloads reasonable
_TOOL_INPUT_TRUNCATE = 200
_TOOL_OUTPUT_TRUNCATE = 200
_MESSAGE_TRUNCATE = 300


def _truncate(text: str | None, max_len: int) -> str:
    """Truncate a string to max_len, appending ellipsis if trimmed."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _compute_duration_ms(start: datetime | None, end: datetime | None) -> float | None:
    """Compute duration in milliseconds between two datetimes."""
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    if delta < 0:
        return None
    return round(delta * 1000, 2)


@dataclass
class ReplayToolCall:
    """Single tool call in the replay."""

    tool_name: str
    status: str  # success, error, timeout, calling, called
    duration_ms: float | None
    error: str | None
    timestamp: datetime
    input_summary: str  # truncated tool input
    output_summary: str  # truncated tool output


@dataclass
class ReplayError:
    """Error event in the replay."""

    error_type: str
    message: str
    severity: str
    recoverable: bool
    timestamp: datetime
    recovery_hint: str | None


@dataclass
class ReplayStep:
    """Single agent step in the replay."""

    step_number: int
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: float | None
    tool_calls: list[ReplayToolCall] = field(default_factory=list)
    errors: list[ReplayError] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)  # LLM responses (truncated)
    phase: str | None = None
    step_description: str | None = None
    step_status: str | None = None


@dataclass
class SessionReplay:
    """Complete session replay for debugging."""

    session_id: str
    status: str
    task: str
    started_at: datetime | None
    ended_at: datetime | None
    total_duration_ms: float | None
    total_steps: int
    total_tool_calls: int
    total_errors: int
    steps: list[ReplayStep] = field(default_factory=list)
    error_summary: list[ReplayError] = field(default_factory=list)  # All errors, flattened

    @property
    def has_errors(self) -> bool:
        return self.total_errors > 0


def _extract_tool_input_summary(event: ToolEvent) -> str:
    """Extract a truncated summary of tool input from a ToolEvent."""
    # Prefer display_command for a human-readable summary
    if event.display_command:
        return _truncate(event.display_command, _TOOL_INPUT_TRUNCATE)

    # Fall back to function_args serialized
    if event.function_args:
        # Try to produce a compact representation
        parts: list[str] = []
        for key, value in event.function_args.items():
            val_str = str(value) if value is not None else ""
            parts.append(f"{key}={val_str}")
        return _truncate(", ".join(parts), _TOOL_INPUT_TRUNCATE)

    return ""


def _extract_tool_output_summary(event: ToolEvent) -> str:
    """Extract a truncated summary of tool output from a ToolEvent."""
    # Check stdout first (shell commands)
    if event.stdout:
        return _truncate(event.stdout, _TOOL_OUTPUT_TRUNCATE)

    # Check stderr for error context
    if event.stderr:
        return _truncate(event.stderr, _TOOL_OUTPUT_TRUNCATE)

    # Check function_result
    if event.function_result is not None:
        result_str = str(event.function_result)
        return _truncate(result_str, _TOOL_OUTPUT_TRUNCATE)

    # Check command_summary
    if event.command_summary:
        return _truncate(event.command_summary, _TOOL_OUTPUT_TRUNCATE)

    return ""


def _determine_tool_status(event: ToolEvent) -> str:
    """Determine a human-readable tool status string."""
    # Use the granular call_status if available
    if event.call_status is not None:
        return event.call_status.value

    # Fall back to ToolStatus enum
    return event.status.value if event.status else "unknown"


def build_session_replay(session: Session) -> SessionReplay:
    """Build a structured replay timeline from session events.

    Groups events by step, extracts tool calls, errors, and messages,
    calculates durations, and returns a structured replay object.
    """
    # Track steps indexed by step number (1-based from StepEvent ordering)
    steps_by_number: dict[int, ReplayStep] = {}
    all_errors: list[ReplayError] = []
    current_phase: str | None = None
    current_step_number: int = 0

    # We need to assign events to steps. StepEvent with status=STARTED marks
    # the beginning of a new step. Events between step boundaries belong to
    # the most recently started step. Events before any step go to step 0.

    # First pass: identify step boundaries and create ReplayStep objects
    step_event_order: list[int] = []  # step numbers in order of appearance
    step_counter = 0

    for event in session.events:
        # Track phase changes in the first pass too
        if isinstance(event, PhaseEvent):
            if event.status.value == "started":
                current_phase = event.phase_type or event.label or event.phase_id
            continue

        if isinstance(event, StepEvent):
            step_desc = event.step.description if event.step else None
            step_id_str = event.step.id if event.step else None

            if event.status.value == "started":
                step_counter += 1
                step = ReplayStep(
                    step_number=step_counter,
                    started_at=event.timestamp,
                    ended_at=None,
                    duration_ms=event.duration_ms,
                    phase=current_phase,
                    step_description=step_desc,
                    step_status="started",
                )
                steps_by_number[step_counter] = step
                step_event_order.append(step_counter)

            elif event.status.value in ("completed", "failed"):
                # Find the matching step (latest with same step.id or just the current)
                target_step_num: int | None = None
                if step_id_str:
                    for sn, _rs in reversed(list(steps_by_number.items())):
                        # Match by position — the most recent step
                        target_step_num = sn
                        break
                if target_step_num is None:
                    target_step_num = step_counter

                if target_step_num in steps_by_number:
                    existing = steps_by_number[target_step_num]
                    existing.ended_at = event.timestamp
                    existing.step_status = event.status.value
                    # Calculate duration if not already set
                    if existing.duration_ms is None and event.duration_ms is not None:
                        existing.duration_ms = event.duration_ms
                    elif existing.duration_ms is None:
                        existing.duration_ms = _compute_duration_ms(existing.started_at, existing.ended_at)

    # Second pass: assign tool calls, errors, messages to steps
    current_phase = None
    current_step_number = 0

    for event in session.events:
        # Track phase changes
        if isinstance(event, PhaseEvent):
            if event.status.value == "started":
                current_phase = event.phase_type or event.label or event.phase_id
            continue

        # Track step boundaries
        if isinstance(event, StepEvent):
            if event.status.value == "started":
                # Find the step_counter value for this StepEvent
                # We iterate step_event_order to advance
                for sn in step_event_order:
                    if sn > current_step_number:
                        current_step_number = sn
                        break
            continue

        # Update phase on existing steps
        if current_step_number in steps_by_number and current_phase:
            steps_by_number[current_step_number].phase = current_phase

        # Extract tool calls
        if isinstance(event, ToolEvent):
            tool_call = ReplayToolCall(
                tool_name=event.tool_name,
                status=_determine_tool_status(event),
                duration_ms=event.duration_ms,
                error=_truncate(event.stderr, _TOOL_OUTPUT_TRUNCATE) if event.stderr else None,
                timestamp=event.timestamp,
                input_summary=_extract_tool_input_summary(event),
                output_summary=_extract_tool_output_summary(event),
            )

            if current_step_number in steps_by_number:
                steps_by_number[current_step_number].tool_calls.append(tool_call)
            else:
                # Event before any step — create step 0
                if 0 not in steps_by_number:
                    steps_by_number[0] = ReplayStep(
                        step_number=0,
                        started_at=event.timestamp,
                        ended_at=None,
                        duration_ms=None,
                        phase=current_phase,
                        step_description="Pre-step events",
                        step_status="completed",
                    )
                steps_by_number[0].tool_calls.append(tool_call)

        # Extract errors
        elif isinstance(event, ErrorEvent):
            replay_error = ReplayError(
                error_type=event.error_type or "unknown",
                message=_truncate(event.error, _MESSAGE_TRUNCATE),
                severity=event.severity or "error",
                recoverable=event.recoverable,
                timestamp=event.timestamp,
                recovery_hint=event.retry_hint,
            )

            all_errors.append(replay_error)

            if current_step_number in steps_by_number:
                steps_by_number[current_step_number].errors.append(replay_error)
            else:
                if 0 not in steps_by_number:
                    steps_by_number[0] = ReplayStep(
                        step_number=0,
                        started_at=event.timestamp,
                        ended_at=None,
                        duration_ms=None,
                        phase=current_phase,
                        step_description="Pre-step events",
                        step_status="completed",
                    )
                steps_by_number[0].errors.append(replay_error)

        # Extract assistant messages
        elif isinstance(event, MessageEvent):
            if event.role == "assistant" and event.message:
                truncated = _truncate(event.message, _MESSAGE_TRUNCATE)
                if current_step_number in steps_by_number:
                    steps_by_number[current_step_number].messages.append(truncated)
                else:
                    if 0 not in steps_by_number:
                        steps_by_number[0] = ReplayStep(
                            step_number=0,
                            started_at=event.timestamp,
                            ended_at=None,
                            duration_ms=None,
                            phase=current_phase,
                            step_description="Pre-step events",
                            step_status="completed",
                        )
                    steps_by_number[0].messages.append(truncated)

    # Build sorted step list
    sorted_steps = sorted(steps_by_number.values(), key=lambda s: s.step_number)

    # Calculate totals
    total_tool_calls = sum(len(s.tool_calls) for s in sorted_steps)
    total_errors = len(all_errors)

    # Determine session timing
    session_started = session.created_at
    session_ended: datetime | None = None
    if sorted_steps:
        # Use the last step's end time, or the last event's timestamp
        last_step = sorted_steps[-1]
        session_ended = last_step.ended_at

    if session_ended is None and session.events:
        session_ended = session.events[-1].timestamp

    total_duration = _compute_duration_ms(session_started, session_ended)

    replay = SessionReplay(
        session_id=session.id,
        status=session.status.value if session.status else "unknown",
        task=session.title or session.latest_message or "Untitled session",
        started_at=session_started,
        ended_at=session_ended,
        total_duration_ms=total_duration,
        total_steps=len(sorted_steps),
        total_tool_calls=total_tool_calls,
        total_errors=total_errors,
        steps=sorted_steps,
        error_summary=all_errors,
    )

    logger.debug(
        "session_replay_built",
        session_id=session.id,
        total_steps=len(sorted_steps),
        total_tool_calls=total_tool_calls,
        total_errors=total_errors,
    )

    return replay
