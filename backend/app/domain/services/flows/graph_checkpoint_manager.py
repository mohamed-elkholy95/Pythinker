"""Checkpoint manager for WorkflowGraph executions."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.models.snapshot import SnapshotType, StateSnapshot
from app.domain.repositories.snapshot_repository import SnapshotRepository

logger = logging.getLogger(__name__)


@dataclass
class GraphCheckpoint:
    """Lightweight checkpoint for workflow graph state."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    node_name: str = ""
    iteration: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    state: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)


class GraphCheckpointManager:
    """Checkpoint manager that stores workflow graph checkpoints."""

    def __init__(
        self,
        repository: SnapshotRepository | None = None,
        max_per_session: int = 100,
    ) -> None:
        self._repository = repository
        self._max_per_session = max_per_session
        self._memory_store: dict[str, list[GraphCheckpoint]] = {}

    async def save_checkpoint(
        self,
        session_id: str,
        node_name: str,
        iteration: int,
        state: Any,
        execution: dict[str, Any] | None = None,
    ) -> GraphCheckpoint | None:
        """Save a checkpoint for a workflow graph state."""
        if not session_id:
            session_id = "unknown"

        payload = {
            "node_name": node_name,
            "iteration": iteration,
            "state": self._serialize_state(state),
            "execution": execution or {},
        }

        checkpoint = GraphCheckpoint(
            session_id=session_id,
            node_name=node_name,
            iteration=iteration,
            state=payload["state"],
            execution=payload["execution"],
        )

        if self._repository:
            try:
                snapshot = StateSnapshot(
                    session_id=session_id,
                    action_id=None,
                    sequence_number=iteration,
                    snapshot_type=SnapshotType.FULL_STATE,
                    full_state=payload,
                )
                await self._repository.save(snapshot)
            except Exception as e:
                logger.error(f"Failed to save checkpoint to repository: {e}")
                return None
        else:
            history = self._memory_store.setdefault(session_id, [])
            history.append(checkpoint)
            if len(history) > self._max_per_session:
                del history[0]

        return checkpoint

    def get_latest(self, session_id: str) -> GraphCheckpoint | None:
        """Get the latest in-memory checkpoint for a session."""
        history = self._memory_store.get(session_id, [])
        return history[-1] if history else None

    def _serialize_state(self, state: Any, depth: int = 0, max_depth: int = 4) -> Any:
        """Best-effort serialization for checkpointing."""
        if depth > max_depth:
            return "..."
        if isinstance(state, (str, int, float, bool)) or state is None:
            return state
        if isinstance(state, dict):
            return {k: self._serialize_state(v, depth + 1, max_depth) for k, v in state.items()}
        if isinstance(state, list):
            return [self._serialize_state(v, depth + 1, max_depth) for v in state]
        if hasattr(state, "__dict__"):
            raw = state.__dict__.copy()
            # Drop heavy/injected fields
            for key in list(raw.keys()):
                if key in {"planner", "executor", "verifier", "reflection_agent", "task_state_manager"}:
                    raw.pop(key, None)
            return self._serialize_state(raw, depth + 1, max_depth)
        return repr(state)


_graph_checkpoint_manager: GraphCheckpointManager | None = None


def get_graph_checkpoint_manager() -> GraphCheckpointManager:
    """Get or create the global graph checkpoint manager."""
    global _graph_checkpoint_manager
    if _graph_checkpoint_manager is None:
        _graph_checkpoint_manager = GraphCheckpointManager()
    return _graph_checkpoint_manager
