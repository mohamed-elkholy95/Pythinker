"""Repository interface for StateSnapshot aggregate."""

from typing import Optional, Protocol, List
from datetime import datetime
from app.domain.models.snapshot import StateSnapshot


class SnapshotRepository(Protocol):
    """Repository interface for StateSnapshot aggregate."""

    async def save(self, snapshot: StateSnapshot) -> None:
        """Save a state snapshot."""
        ...

    async def save_many(self, snapshots: List[StateSnapshot]) -> None:
        """Save multiple snapshots in a batch operation."""
        ...

    async def find_by_id(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Find a snapshot by its ID."""
        ...

    async def find_by_session(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[StateSnapshot]:
        """Find all snapshots for a session, ordered by sequence number."""
        ...

    async def find_by_action(self, action_id: str) -> Optional[StateSnapshot]:
        """Find the snapshot associated with a specific action."""
        ...

    async def find_nearest_before(
        self,
        session_id: str,
        sequence_number: int
    ) -> Optional[StateSnapshot]:
        """
        Find the nearest snapshot at or before the given sequence number.
        Used for efficient state reconstruction.
        """
        ...

    async def find_nearest_before_time(
        self,
        session_id: str,
        timestamp: datetime
    ) -> Optional[StateSnapshot]:
        """
        Find the nearest snapshot at or before the given timestamp.
        Used for time-based state reconstruction.
        """
        ...

    async def get_snapshots_in_range(
        self,
        session_id: str,
        start_sequence: int,
        end_sequence: int
    ) -> List[StateSnapshot]:
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

    async def delete_older_than(
        self,
        session_id: str,
        before_date: datetime
    ) -> int:
        """
        Delete snapshots older than a given date.
        Used for retention policy enforcement.
        Returns the number of deleted snapshots.
        """
        ...

    async def get_latest_full_snapshot(
        self,
        session_id: str
    ) -> Optional[StateSnapshot]:
        """
        Get the most recent full state snapshot for a session.
        Full snapshots contain complete session state.
        """
        ...
