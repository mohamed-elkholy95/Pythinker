# backend/app/domain/services/attention_injector.py
"""Attention injector for goal recitation pattern.

This module implements Manus AI's attention manipulation pattern to prevent
"lost-in-the-middle" issues by periodically injecting goal context into
the conversation history.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AttentionInjector:
    """
    Injects attention context into message history.

    Implements Manus AI's attention manipulation pattern:
    - Periodically "recites" goals into the context
    - Prevents "lost-in-the-middle" issues
    - Keeps objectives in the model's recent attention span

    The attention context is injected as a system message before the last
    user message to ensure the model has fresh awareness of the current
    objective and progress.

    Attributes:
        injection_interval: Number of messages between attention injections.
        ATTENTION_TEMPLATE: Template for formatting the attention context.

    Example:
        >>> injector = AttentionInjector(injection_interval=5)
        >>> messages = [{"role": "user", "content": "Continue the task"}]
        >>> result = injector.inject(messages, goal="Complete analysis")
    """

    ATTENTION_TEMPLATE = """<attention-context>
## Current Objective
{goal}

## Progress
{todo}
</attention-context>"""

    def __init__(self, injection_interval: int = 5) -> None:
        """
        Initialize attention injector.

        Args:
            injection_interval: Inject attention context every N messages.
                Defaults to 5, meaning attention context is injected when
                the message count is a multiple of 5.
        """
        self.injection_interval = injection_interval
        self._injection_count = 0
        logger.debug("AttentionInjector initialized with interval=%d", injection_interval)

    def inject(
        self,
        messages: list[dict[str, Any]],
        goal: str | None = None,
        todo: list[str] | None = None,
        state: dict[str, Any] | None = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Inject attention context into message history.

        Inserts a system message with current goal and progress
        to keep the model focused on the task. The injection is placed
        before the last user message to ensure it's in the model's
        recent attention span.

        Args:
            messages: List of conversation messages with 'role' and 'content' keys.
            goal: The current objective or goal to reinforce. If None, no
                injection occurs.
            todo: List of pending tasks or steps to include in the context.
            state: Optional state dictionary with additional context info
                (e.g., current_step, total_steps).
            force: If True, inject regardless of the injection interval.

        Returns:
            A new list of messages with attention context injected if applicable.
            The original messages list is not modified.

        Example:
            >>> injector = AttentionInjector(injection_interval=1)
            >>> messages = [{"role": "user", "content": "Continue"}]
            >>> result = injector.inject(
            ...     messages, goal="Complete report", todo=["Gather data", "Write summary"], force=True
            ... )
            >>> len(result) > len(messages)
            True
        """
        # Return early if no messages or no goal
        if not messages:
            logger.debug("No messages provided, skipping injection")
            return messages

        if goal is None:
            logger.debug("No goal provided, skipping injection")
            return messages

        # Determine if injection should occur:
        # - Always inject if force=True
        # - Always inject if todo list is provided (indicates active task with progress)
        # - Otherwise, inject based on interval
        message_count = len(messages)
        has_todo = todo is not None and len(todo) > 0

        if not force and not has_todo and not self.should_inject(message_count):
            logger.debug(
                "Skipping injection: count=%d, interval=%d, force=%s, has_todo=%s",
                message_count,
                self.injection_interval,
                force,
                has_todo,
            )
            return messages

        # Format the attention context
        attention_content = self._format_attention_context(goal, todo, state)

        # Create the attention system message
        attention_message: dict[str, Any] = {
            "role": "system",
            "content": attention_content,
        }

        # Find the position to inject (before the last user message)
        result = list(messages)  # Create a copy to avoid mutation
        insertion_index = self._find_insertion_index(result)

        # Insert the attention context
        result.insert(insertion_index, attention_message)

        self._injection_count += 1
        logger.info(
            "Injected attention context at index %d (total injections: %d)",
            insertion_index,
            self._injection_count,
        )

        return result

    def should_inject(self, message_count: int) -> bool:
        """
        Check if attention should be injected based on message count.

        The injection occurs when the message count is a positive multiple
        of the injection interval.

        Args:
            message_count: The current number of messages in the conversation.

        Returns:
            True if attention context should be injected, False otherwise.

        Example:
            >>> injector = AttentionInjector(injection_interval=5)
            >>> injector.should_inject(0)
            False
            >>> injector.should_inject(5)
            True
            >>> injector.should_inject(10)
            True
        """
        return message_count > 0 and message_count % self.injection_interval == 0

    def _format_attention_context(
        self,
        goal: str,
        todo: list[str] | None = None,
        state: dict[str, Any] | None = None,
    ) -> str:
        """
        Format the attention context from goal, todo, and state.

        Args:
            goal: The current objective.
            todo: Optional list of pending tasks.
            state: Optional state dictionary with progress information.

        Returns:
            Formatted attention context string.
        """
        # Format todo items as a bulleted list or "No pending tasks"
        todo_formatted = "\n".join(f"- {item}" for item in todo) if todo else "No pending tasks listed"

        # Include state information if provided
        if state:
            state_info = "\n".join(f"- {k}: {v}" for k, v in state.items())
            todo_formatted = f"{todo_formatted}\n\n## State\n{state_info}"

        return self.ATTENTION_TEMPLATE.format(goal=goal, todo=todo_formatted)

    def _find_insertion_index(self, messages: list[dict[str, Any]]) -> int:
        """
        Find the index where attention context should be inserted.

        The context is inserted before the last user message to ensure
        it's in the model's recent attention span.

        Args:
            messages: List of conversation messages.

        Returns:
            Index where the attention context should be inserted.
        """
        # Find the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                logger.debug("Found last user message at index %d", i)
                return i

        # If no user message found, insert at the end
        logger.debug("No user message found, inserting at end")
        return len(messages)
