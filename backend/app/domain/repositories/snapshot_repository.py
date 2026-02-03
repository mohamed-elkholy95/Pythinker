"""Repository interface for StateSnapshot aggregate."""

from datetime import datetime
from typing import Protocol

from app.domain.models.snapshot import StateSnapshot


class SnapshotRepository(Protocol):
    """Repository interface for StateSnapshot aggregate."""

    async def save(self, snapshot: StateSnapshot) -> None:
        """Save a state snapshot."""
        ...

    async def save_many(self, snapshots: list[StateSnapshot]) -> None:
        """Save multiple snapshots in a batch operation."""
        ...

    async def find_by_id(self, snapshot_id: str) -> StateSnapshot | None:
        """Find a snapshot by its ID."""
        ...

    async def find_by_session(self, session_id: str, limit: int | None = None) -> list[StateSnapshot]:
        """Find all snapshots for a session, ordered by sequence number."""
        ...

    async def find_by_action(self, action_id: str) -> StateSnapshot | None:
        """Find the snapshot associated with a specific action."""
        ...

    async def find_nearest_before(self, session_id: str, sequence_number: int) -> StateSnapshot | None:
        """
        Find the nearest snapshot at or before the given sequence number.
        Used for efficient state reconstruction.
        """
        ...

    async def find_nearest_before_time(self, session_id: str, timestamp: datetime) -> StateSnapshot | None:
        """
        Find the nearest snapshot at or before the given timestamp.
        Used for time-based state reconstruction.
        """
        ...

    async def get_snapshots_in_range(
        self, session_id: str, start_sequence: int, end_sequence: int
    ) -> list[StateSnapshot]:
        """
        Get all snapshots within a sequence number range.
        Useful for reconstructing state over a range of actions.
        """
        ...

    async def count_by_session(self, session_id: str) -> int:
        """Count the number of snapshots for a session."""
        ...

    async def delete_by_session(self, session_id: str) -> int:
        """
        Delete all snapshots for a session.
        Returns the number of deleted snapshots.
        """
        ...

    async def delete_older_than(self, session_id: str, before_date: datetime) -> int:
        """
        Delete snapshots older than a given date.
        Used for retention policy enforcement.
        Returns the number of deleted snapshots.
        """
        ...

    async def get_latest_full_snapshot(self, session_id: str) -> StateSnapshot | None:
        """
        Get the most recent full state snapshot for a session.
        Full snapshots contain complete session state.
        """
        ...
