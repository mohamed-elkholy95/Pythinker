"""State manifest for blackboard architecture.

This module implements Pythinker AI's Blackboard Architecture pattern, where agents
post results to a shared state manifest enabling asynchronous collaboration
and "serendipitous" discovery during research.

The blackboard architecture allows:
- Agents to post intermediate results and findings
- Other agents to discover and build upon those findings
- Historical tracking of how state evolved over time
- Efficient retrieval of state by key, agent, or recency
"""

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger(__name__)


class StateEntry(BaseModel):
    """An entry in the state manifest.

    Represents a single piece of state posted by an agent to the shared
    blackboard. Each entry is immutable once posted - updates are made
    by posting new entries with the same key.

    Attributes:
        key: Unique identifier for this piece of state (e.g., "research_findings")
        value: The actual state value (can be any JSON-serializable type)
        posted_by: ID of the agent that posted this entry
        timestamp: When the entry was posted (UTC)
        metadata: Additional context about the entry (e.g., confidence, model used)
    """

    key: str
    value: Any
    posted_by: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateManifest(BaseModel):
    """Shared state manifest for inter-agent communication.

    Implements Pythinker AI's Blackboard Architecture pattern, providing a
    centralized place where agents can:
    - Post results and findings for other agents to discover
    - Query the current state of any key
    - Access the history of how state evolved
    - Find all contributions by a specific agent

    The blackboard pattern enables asynchronous collaboration where agents
    don't need to directly communicate - they simply read and write to the
    shared state manifest.

    Attributes:
        session_id: The session this manifest belongs to
        entries: List of all state entries in chronological order

    Example:
        ```python
        manifest = StateManifest(session_id="sess_123")

        # Research agent posts findings
        manifest.post(
            StateEntry(
                key="research_findings",
                value={"topic": "AI safety", "sources": ["paper1", "paper2"]},
                posted_by="research-agent",
            )
        )

        # Synthesis agent retrieves findings
        findings = manifest.get("research_findings")
        ```
    """

    session_id: str
    entries: list[StateEntry] = Field(default_factory=list)

    # Private attribute for key -> list of entry indices mapping
    _index: dict[str, list[int]] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Build index after initialization."""
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the key index from entries.

        Creates a mapping from each key to the indices of entries
        that have that key, enabling efficient lookups.
        """
        self._index = {}
        for i, entry in enumerate(self.entries):
            if entry.key not in self._index:
                self._index[entry.key] = []
            self._index[entry.key].append(i)

    def post(self, entry: StateEntry) -> None:
        """Post an entry to the blackboard.

        Appends the entry to the manifest and updates the index.
        Does not replace existing entries - the history is preserved.

        Args:
            entry: The state entry to post

        Example:
            ```python
            manifest.post(StateEntry(key="analysis_result", value={"score": 0.95}, posted_by="analyzer-agent"))
            ```
        """
        index = len(self.entries)
        self.entries.append(entry)

        # Update index
        if entry.key not in self._index:
            self._index[entry.key] = []
        self._index[entry.key].append(index)

        logger.debug(
            "State entry posted",
            extra={
                "session_id": self.session_id,
                "key": entry.key,
                "posted_by": entry.posted_by,
                "entry_index": index,
            },
        )

    def get(self, key: str) -> StateEntry | None:
        """Get the latest entry for a key.

        Args:
            key: The key to look up

        Returns:
            The most recent StateEntry for this key, or None if not found

        Example:
            ```python
            entry = manifest.get("research_findings")
            if entry:
                print(f"Latest findings: {entry.value}")
            ```
        """
        indices = self._index.get(key)
        if not indices:
            return None
        return self.entries[indices[-1]]

    def get_history(self, key: str) -> list[StateEntry]:
        """Get all entries for a key in chronological order.

        Useful for understanding how a piece of state evolved over time,
        or for debugging agent behavior.

        Args:
            key: The key to look up

        Returns:
            List of all entries for this key, oldest first

        Example:
            ```python
            history = manifest.get_history("progress")
            for entry in history:
                print(f"{entry.timestamp}: {entry.value} (by {entry.posted_by})")
            ```
        """
        indices = self._index.get(key, [])
        return [self.entries[i] for i in indices]

    def get_by_agent(self, agent_id: str) -> list[StateEntry]:
        """Get all entries posted by a specific agent.

        Useful for auditing agent contributions or understanding
        an agent's activity during a session.

        Args:
            agent_id: The ID of the agent

        Returns:
            List of all entries posted by this agent, in chronological order

        Example:
            ```python
            contributions = manifest.get_by_agent("research-agent-1")
            print(f"Agent contributed {len(contributions)} entries")
            ```
        """
        return [entry for entry in self.entries if entry.posted_by == agent_id]

    def get_recent(self, limit: int = 10) -> list[StateEntry]:
        """Get the most recent entries.

        Returns entries in reverse chronological order (most recent first).

        Args:
            limit: Maximum number of entries to return (default: 10)

        Returns:
            List of recent entries, most recent first

        Example:
            ```python
            recent = manifest.get_recent(limit=5)
            for entry in recent:
                print(f"{entry.key}: {entry.value}")
            ```
        """
        # Return entries in reverse order (most recent first)
        return list(reversed(self.entries[-limit:]))

    def to_context_string(self, max_entries: int = 10) -> str:
        """Convert recent state to a string for LLM context.

        Formats recent entries as a human-readable string suitable for
        including in an LLM prompt to provide context about shared state.

        Args:
            max_entries: Maximum number of entries to include (default: 10)

        Returns:
            Formatted string representation of recent state

        Example:
            ```python
            context = manifest.to_context_string(max_entries=5)
            prompt = f"Shared State:\\n{context}\\n\\nYour task: ..."
            ```
        """
        if not self.entries:
            return "No shared state available."

        recent = self.get_recent(limit=max_entries)
        lines = ["## Shared State (Blackboard)", ""]

        for entry in recent:
            timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            value_str = str(entry.value)
            # Truncate long values
            if len(value_str) > 200:
                value_str = value_str[:197] + "..."

            lines.append(f"**{entry.key}** (by {entry.posted_by} at {timestamp_str})")
            lines.append(f"  {value_str}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest for storage.

        Returns:
            Dictionary representation suitable for MongoDB or JSON storage.
        """
        return {
            "session_id": self.session_id,
            "entries": [
                {
                    "key": entry.key,
                    "value": entry.value,
                    "posted_by": entry.posted_by,
                    "timestamp": entry.timestamp.isoformat(),
                    "metadata": entry.metadata,
                }
                for entry in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateManifest":
        """Deserialize from storage.

        Args:
            data: Dictionary representation from storage.

        Returns:
            StateManifest instance with index rebuilt.
        """
        entries = [
            StateEntry(
                key=e["key"],
                value=e["value"],
                posted_by=e["posted_by"],
                timestamp=datetime.fromisoformat(e["timestamp"]),
                metadata=e.get("metadata", {}),
            )
            for e in data.get("entries", [])
        ]
        return cls(session_id=data["session_id"], entries=entries)
