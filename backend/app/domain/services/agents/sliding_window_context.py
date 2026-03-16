"""Priority-based sliding window context manager.

Manages which messages are retained vs. dropped when assembling context
for LLM calls, using a priority system that preserves the most valuable
messages while staying within token budgets.

Usage:
    from app.domain.services.agents.sliding_window_context import (
        SlidingWindowContextManager,
        MessagePriority,
    )

    ctx_mgr = SlidingWindowContextManager(token_manager)
    messages = ctx_mgr.prepare_messages(
        messages=raw_messages,
        budget_tokens=50000,
        phase="execution",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domain.services.agents.token_manager import TokenManager

logger = logging.getLogger(__name__)


class MessagePriority(IntEnum):
    """Priority levels for message retention.

    Higher values = higher priority = retained longer.
    When context must be trimmed, lowest-priority messages are dropped first.
    """

    COMPACTED = 10  # Already-compacted summaries (can be re-compacted)
    TOOL_OLD = 30  # Tool results from early in the conversation
    ASSISTANT_OLD = 40  # Old assistant responses
    TOOL_RECENT = 70  # Recent tool results (last 4-6 calls)
    ASSISTANT_RECENT = 75  # Recent assistant responses
    USER_OLD = 80  # Old user messages (preserve intent history)
    USER_CURRENT = 90  # Current user message / most recent user input
    SYSTEM = 100  # System prompt (never drop)


@dataclass
class PrioritizedMessage:
    """A message annotated with its retention priority and token count."""

    message: dict[str, Any]
    priority: MessagePriority
    tokens: int = 0
    index: int = 0  # Original position in the message list
    is_tool_pair: bool = False  # Part of a tool_call/tool_result pair
    pair_id: str | None = None  # Group ID for tool call + result pairs

    @property
    def role(self) -> str:
        return self.message.get("role", "unknown")


@dataclass
class WindowResult:
    """Result of sliding window context preparation."""

    messages: list[dict[str, Any]]
    total_tokens: int
    dropped_count: int = 0
    dropped_tokens: int = 0
    compacted_count: int = 0


class SlidingWindowContextManager:
    """Priority-based message retention for LLM context windows.

    When the total token count exceeds the budget, messages are dropped
    in priority order (lowest first). Tool call/result pairs are treated
    atomically — if one is dropped, both are dropped.

    Key behaviors:
    - System messages are never dropped
    - The most recent user message is never dropped
    - Recent tool results (last N) are prioritized over older ones
    - Tool calls and their results are grouped as pairs
    - Already-compacted messages are dropped before raw messages
    """

    # How many recent tool interactions to prioritize
    RECENT_TOOL_WINDOW = 4

    # How many recent user/assistant turns to prioritize
    RECENT_TURN_WINDOW = 3

    def __init__(self, token_manager: TokenManager) -> None:
        self._token_manager = token_manager

    def prepare_messages(
        self,
        messages: list[dict[str, Any]],
        budget_tokens: int,
        phase: str | None = None,
    ) -> WindowResult:
        """Prepare messages to fit within a token budget.

        Args:
            messages: Raw message list from the conversation.
            budget_tokens: Maximum tokens allowed for this context.
            phase: Optional execution phase for priority adjustments.

        Returns:
            WindowResult with the retained messages, token counts,
            and statistics about what was dropped.
        """
        if not messages:
            return WindowResult(messages=[], total_tokens=0)

        # Step 1: Annotate messages with priorities and token counts
        prioritized = self._annotate_messages(messages)

        # Step 2: Check if we're within budget already
        total_tokens = sum(pm.tokens for pm in prioritized)
        if total_tokens <= budget_tokens:
            return WindowResult(
                messages=messages,
                total_tokens=total_tokens,
            )

        # Step 3: Drop messages by priority until we fit
        retained, dropped_count, dropped_tokens = self._fit_to_budget(prioritized, budget_tokens)

        # Reconstruct message list in original order
        retained.sort(key=lambda pm: pm.index)
        result_messages = [pm.message for pm in retained]
        result_tokens = sum(pm.tokens for pm in retained)

        logger.info(
            "Sliding window: %d→%d messages, %d→%d tokens (dropped %d msgs, %d tokens)",
            len(messages),
            len(result_messages),
            total_tokens,
            result_tokens,
            dropped_count,
            dropped_tokens,
        )

        return WindowResult(
            messages=result_messages,
            total_tokens=result_tokens,
            dropped_count=dropped_count,
            dropped_tokens=dropped_tokens,
        )

    def _annotate_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[PrioritizedMessage]:
        """Assign priority and token counts to each message."""
        prioritized: list[PrioritizedMessage] = []

        # Find the last user message index
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break

        # Count tool results from the end to identify "recent" ones
        tool_result_indices: list[int] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                tool_result_indices.append(i)
        recent_tool_set = set(tool_result_indices[-self.RECENT_TOOL_WINDOW :])

        # Count user/assistant turns from the end for recency
        turn_count_from_end: dict[int, int] = {}
        turn_counter = 0
        for i in range(len(messages) - 1, -1, -1):
            role = messages[i].get("role", "")
            if role in ("user", "assistant"):
                turn_count_from_end[i] = turn_counter
                turn_counter += 1

        # Build tool call → result pairing
        tool_call_pairs = self._build_tool_pairs(messages)

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            tokens = self._count_message_tokens(msg)

            # Determine priority
            if role == "system":
                priority = MessagePriority.SYSTEM
            elif role == "user" and i == last_user_idx:
                priority = MessagePriority.USER_CURRENT
            elif role == "user":
                turns_back = turn_count_from_end.get(i, 999)
                if turns_back < self.RECENT_TURN_WINDOW:
                    priority = MessagePriority.USER_CURRENT
                else:
                    priority = MessagePriority.USER_OLD
            elif role == "tool":
                if i in recent_tool_set:
                    priority = MessagePriority.TOOL_RECENT
                elif self._is_compacted(msg):
                    priority = MessagePriority.COMPACTED
                else:
                    priority = MessagePriority.TOOL_OLD
            elif role == "assistant":
                turns_back = turn_count_from_end.get(i, 999)
                if turns_back < self.RECENT_TURN_WINDOW:
                    priority = MessagePriority.ASSISTANT_RECENT
                else:
                    priority = MessagePriority.ASSISTANT_OLD
            else:
                priority = MessagePriority.TOOL_OLD

            pair_id = tool_call_pairs.get(i)
            prioritized.append(
                PrioritizedMessage(
                    message=msg,
                    priority=priority,
                    tokens=tokens,
                    index=i,
                    is_tool_pair=pair_id is not None,
                    pair_id=pair_id,
                )
            )

        return prioritized

    def _fit_to_budget(
        self,
        prioritized: list[PrioritizedMessage],
        budget_tokens: int,
    ) -> tuple[list[PrioritizedMessage], int, int]:
        """Drop lowest-priority messages until the total fits within budget.

        Tool call/result pairs are dropped atomically.

        Returns:
            Tuple of (retained messages, dropped count, dropped tokens).
        """
        # Sort by priority ascending (lowest priority first for dropping)
        candidates = sorted(prioritized, key=lambda pm: (pm.priority, pm.index))

        # Never drop system or current user messages
        undropable = {pm.index for pm in candidates if pm.priority >= MessagePriority.USER_CURRENT}

        total_tokens = sum(pm.tokens for pm in candidates)
        dropped_indices: set[int] = set()
        dropped_tokens = 0

        for pm in candidates:
            if total_tokens <= budget_tokens:
                break

            if pm.index in undropable or pm.index in dropped_indices:
                continue

            # If part of a tool pair, drop the entire pair
            if pm.pair_id is not None:
                pair_members = [p for p in candidates if p.pair_id == pm.pair_id and p.index not in dropped_indices]
                # Don't drop pairs if any member is undropable
                if any(p.index in undropable for p in pair_members):
                    continue
                for p in pair_members:
                    dropped_indices.add(p.index)
                    total_tokens -= p.tokens
                    dropped_tokens += p.tokens
            else:
                dropped_indices.add(pm.index)
                total_tokens -= pm.tokens
                dropped_tokens += pm.tokens

        retained = [pm for pm in prioritized if pm.index not in dropped_indices]
        return retained, len(dropped_indices), dropped_tokens

    def _build_tool_pairs(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[int, str]:
        """Map message indices to tool call pair IDs.

        Groups assistant messages containing tool_calls with their
        corresponding tool role result messages.

        Returns:
            Dict mapping message index → pair group ID.
        """
        pairs: dict[int, str] = {}
        pending_call_ids: dict[str, int] = {}  # tool_call_id → assistant message index

        for i, msg in enumerate(messages):
            role = msg.get("role", "")

            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    pair_id = f"pair_{i}"
                    pairs[i] = pair_id
                    for tc in tool_calls:
                        tc_id = tc.get("id", "")
                        if tc_id:
                            pending_call_ids[tc_id] = i

            elif role == "tool":
                tc_id = msg.get("tool_call_id", "")
                if tc_id in pending_call_ids:
                    assistant_idx = pending_call_ids[tc_id]
                    pair_id = pairs.get(assistant_idx)
                    if pair_id:
                        pairs[i] = pair_id

        return pairs

    def _count_message_tokens(self, msg: dict[str, Any]) -> int:
        """Count tokens in a single message."""
        result = self._token_manager.count_message_tokens(msg)
        return result.total

    @staticmethod
    def _is_compacted(msg: dict[str, Any]) -> bool:
        """Check if a message has already been compacted."""
        content = msg.get("content", "")
        if isinstance(content, str):
            return "[... truncated" in content or "[compacted]" in content
        return False
