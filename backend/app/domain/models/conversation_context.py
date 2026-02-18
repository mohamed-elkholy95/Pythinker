"""Domain models for continuous conversational context storage.

These models represent conversation turns that are vectorized and stored
in Qdrant during active sessions for real-time semantic retrieval.

Python 3.12+: Uses StrEnum, dataclass, and modern type hints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TurnRole(StrEnum):
    """Role of the entity that produced a conversation turn."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_SUMMARY = "tool_summary"
    STEP_SUMMARY = "step_summary"


class TurnEventType(StrEnum):
    """Type of event that generated the conversation turn."""

    MESSAGE = "message"
    TOOL_RESULT = "tool_result"
    STEP_COMPLETION = "step_completion"
    REPORT = "report"
    ERROR = "error"


@dataclass(frozen=True)
class ConversationTurn:
    """A single conversation turn to be vectorized and stored."""

    point_id: str
    user_id: str
    session_id: str
    role: TurnRole
    event_type: TurnEventType
    content: str
    turn_number: int
    event_id: str
    created_at: int  # Unix timestamp
    content_hash: str  # SHA256[:16] for deduplication
    step_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class ConversationContextResult:
    """A single result from context retrieval."""

    point_id: str
    content: str
    role: str
    event_type: str
    session_id: str
    turn_number: int
    created_at: int  # Unix timestamp
    relevance_score: float
    source: str  # "sliding_window" | "intra_session" | "cross_session"


@dataclass
class ConversationContext:
    """Assembled conversation context for injection into agent step execution.

    Three-phase retrieval:
    1. sliding_window_turns: Recent N turns (always included, no embedding needed)
    2. semantic_turns: Semantically relevant older turns from current session
    3. cross_session_turns: Relevant turns from past sessions by same user
    """

    sliding_window_turns: list[ConversationContextResult] = field(default_factory=list)
    semantic_turns: list[ConversationContextResult] = field(default_factory=list)
    cross_session_turns: list[ConversationContextResult] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Check if all retrieval phases returned empty."""
        return not any([self.sliding_window_turns, self.semantic_turns, self.cross_session_turns])

    @property
    def total_turns(self) -> int:
        """Total number of retrieved turns across all phases."""
        return len(self.sliding_window_turns) + len(self.semantic_turns) + len(self.cross_session_turns)

    def format_for_injection(self, max_chars: int = 4000) -> str:
        """Format retrieved context for system message injection.

        Produces a structured text block suitable for prepending to step
        execution context. Prioritizes sliding window, then semantic, then
        cross-session. Truncates to max_chars to respect token budgets.
        """
        sections: list[str] = []
        chars_used = 0

        # Phase A: Recent conversation (sliding window)
        if self.sliding_window_turns:
            lines = ["### Recent Conversation"]
            for turn in self.sliding_window_turns:
                role_label = turn.role.replace("_", " ").title()
                line = f"[Turn {turn.turn_number}] {role_label}: {turn.content}"
                lines.append(line)
            section = "\n".join(lines)
            if chars_used + len(section) <= max_chars:
                sections.append(section)
                chars_used += len(section)

        # Phase B: Semantically relevant older turns (current session)
        if self.semantic_turns and chars_used < max_chars:
            lines = ["### Related Earlier Context (this session)"]
            for turn in self.semantic_turns:
                role_label = turn.role.replace("_", " ").title()
                line = f"[Turn {turn.turn_number}] {role_label}: {turn.content}"
                if chars_used + len(line) + 1 > max_chars:
                    break
                lines.append(line)
                chars_used += len(line) + 1
            if len(lines) > 1:  # Has content beyond header
                sections.append("\n".join(lines))

        # Phase C: Cross-session recall
        if self.cross_session_turns and chars_used < max_chars:
            lines = ["### Related Past Sessions"]
            for turn in self.cross_session_turns:
                role_label = turn.role.replace("_", " ").title()
                line = f"[Past session] {role_label}: {turn.content}"
                if chars_used + len(line) + 1 > max_chars:
                    break
                lines.append(line)
                chars_used += len(line) + 1
            if len(lines) > 1:
                sections.append("\n".join(lines))

        if not sections:
            return ""

        return "## Session Context\n\n" + "\n\n".join(sections)
