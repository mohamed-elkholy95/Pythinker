"""Context manager for file-system-as-context pattern (Manus-style).

This module implements the "File-System-as-Context" pattern from Manus AI architecture,
where the sandbox file system serves as externalized memory for the agent.

Key benefits:
- Bypasses LLM context window limits by storing context in files
- Persistent memory across conversation turns
- Attention manipulation via periodic goal/todo recitation
- Clear separation of different context types
"""

import json
from datetime import datetime
from typing import Any, Protocol

from app.domain.models.context_memory import ContextMemory, ContextType


class SandboxProtocol(Protocol):
    """Protocol for sandbox file operations.

    This protocol defines the file operations required by ContextManager.
    Any sandbox implementation that provides these methods can be used.
    """

    async def write_file(self, path: str, content: str) -> bool:
        """Write content to a file in the sandbox.

        Args:
            path: File path in the sandbox.
            content: Content to write.

        Returns:
            True if successful.
        """
        ...

    async def read_file(self, path: str) -> str:
        """Read content from a file in the sandbox.

        Args:
            path: File path in the sandbox.

        Returns:
            File contents as string.
        """
        ...

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in the sandbox.

        Args:
            path: File path to check.

        Returns:
            True if file exists.
        """
        ...


class SandboxContextManager:
    """Manages externalized context in sandbox file system.

    Implements Manus AI's "File-System-as-Context" pattern:
    - Uses sandbox storage as unlimited, persistent memory
    - Periodic "recitation" of goals prevents attention drift
    - todo.md pattern keeps current objectives in focus

    The core insight is that while LLM context windows are limited,
    file storage is virtually unlimited. By externalizing context to
    files and selectively loading it back, we can:
    1. Work with much larger contexts
    2. Maintain state across long conversations
    3. Manipulate the model's attention via what we load

    Attributes:
        session_id: The session this manager belongs to.
        sandbox: The sandbox instance for file operations.
        CONTEXT_DIR: Base directory for context files.
    """

    CONTEXT_DIR = "/workspace/.context"

    def __init__(self, session_id: str, sandbox: SandboxProtocol) -> None:
        """Initialize the context manager.

        Args:
            session_id: Unique identifier for the session.
            sandbox: Sandbox instance implementing SandboxProtocol.
        """
        self.session_id = session_id
        self.sandbox = sandbox
        self._cache: dict[ContextType, ContextMemory] = {}

    async def set_goal(self, goal: str, metadata: dict[str, Any] | None = None) -> None:
        """Set the high-level goal for attention manipulation.

        The goal is the most important piece of context. It should be
        recited periodically to keep the agent focused on the main objective.

        Args:
            goal: The high-level goal description.
            metadata: Optional metadata to include with the goal.
        """
        content = f"# Goal\n\n{goal}\n"
        if metadata:
            content += f"\n## Metadata\n```json\n{json.dumps(metadata, indent=2)}\n```\n"

        memory = ContextMemory(
            session_id=self.session_id,
            context_type=ContextType.GOAL,
            content=goal,
            priority=10,  # Highest priority
            file_path=f"{self.CONTEXT_DIR}/goal.md",
        )
        self._cache[ContextType.GOAL] = memory
        await self.sandbox.write_file(memory.file_path, content)

    async def update_todo(self, tasks: list[str], completed: list[int] | None = None) -> None:
        """Update todo.md with current task list.

        This is the core of attention manipulation - keeps current
        objectives in the model's recent attention span. The todo.md
        pattern is key to preventing "lost-in-the-middle" issues in
        long conversations.

        Args:
            tasks: List of task descriptions.
            completed: Indices of completed tasks (0-indexed).
        """
        completed = completed or []
        lines = ["# Todo\n"]
        for i, task in enumerate(tasks):
            checkbox = "[x]" if i in completed else "[ ]"
            lines.append(f"- {checkbox} {task}")

        content = "\n".join(lines)
        memory = ContextMemory(
            session_id=self.session_id,
            context_type=ContextType.TODO,
            content=content,
            priority=9,  # Second highest priority
            file_path=f"{self.CONTEXT_DIR}/todo.md",
        )
        self._cache[ContextType.TODO] = memory
        await self.sandbox.write_file(memory.file_path, content)

    async def add_knowledge(self, key: str, content: str) -> None:
        """Add to persistent knowledge base.

        Knowledge is stored in separate files by key, allowing for
        selective loading based on relevance.

        Args:
            key: Unique identifier for this knowledge piece.
            content: The knowledge content to store.
        """
        path = f"{self.CONTEXT_DIR}/knowledge/{key}.md"
        await self.sandbox.write_file(path, content)

    async def add_research(self, topic: str, findings: str) -> None:
        """Store research findings for later synthesis.

        Research findings are timestamped to preserve chronological order.

        Args:
            topic: The research topic.
            findings: The research findings/content.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_topic = topic.replace(" ", "_").replace("/", "_")
        path = f"{self.CONTEXT_DIR}/research/{timestamp}_{safe_topic}.md"
        await self.sandbox.write_file(path, findings)

    async def get_attention_context(self, max_tokens: int = 2000) -> str:
        """Get context for attention manipulation.

        Returns high-priority context items to inject into the prompt,
        preventing "lost-in-the-middle" issues in long conversations.

        This method retrieves cached context items and formats them
        for injection into the agent's prompt.

        Args:
            max_tokens: Maximum tokens to return (for future token counting).

        Returns:
            Formatted context string with goal, todos, and state.
        """
        parts = []

        # Always include goal if set (highest priority)
        if ContextType.GOAL in self._cache:
            goal = self._cache[ContextType.GOAL]
            parts.append(f"## Current Goal\n{goal.content}")

        # Include todo if set (second priority)
        if ContextType.TODO in self._cache:
            todo = self._cache[ContextType.TODO]
            parts.append(f"## Current Tasks\n{todo.content}")

        # Include recent state if available
        if ContextType.STATE in self._cache:
            state = self._cache[ContextType.STATE]
            parts.append(f"## Current State\n{state.content}")

        return "\n\n".join(parts)

    async def update_state(self, state: dict[str, Any]) -> None:
        """Update current execution state.

        State captures the current progress and context of execution.

        Args:
            state: Dictionary containing state information.
        """
        content = json.dumps(state, indent=2)
        memory = ContextMemory(
            session_id=self.session_id,
            context_type=ContextType.STATE,
            content=content,
            priority=8,  # Third priority
            file_path=f"{self.CONTEXT_DIR}/state.json",
        )
        self._cache[ContextType.STATE] = memory
        await self.sandbox.write_file(memory.file_path, content)

    async def clear_cache(self) -> None:
        """Clear the in-memory cache.

        Useful when reloading context from files.
        """
        self._cache.clear()

    def get_cached_context(self, context_type: ContextType) -> ContextMemory | None:
        """Get a cached context item by type.

        Args:
            context_type: The type of context to retrieve.

        Returns:
            The cached ContextMemory or None if not cached.
        """
        return self._cache.get(context_type)
