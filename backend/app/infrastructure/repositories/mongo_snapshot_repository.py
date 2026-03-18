"""MongoDB implementation of SnapshotRepository."""

import logging
from datetime import datetime

from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from app.domain.exceptions.base import IntegrationException
from app.domain.models.snapshot import SnapshotType, StateSnapshot
from app.domain.repositories.snapshot_repository import SnapshotRepository
from app.infrastructure.models.documents import SnapshotDocument

logger = logging.getLogger(__name__)


class MongoSnapshotRepository(SnapshotRepository):
    """MongoDB implementation of SnapshotRepository."""

    def _to_document(self, snapshot: StateSnapshot) -> SnapshotDocument:
        """Convert domain model to MongoDB document."""
        # Serialize snapshot data based on type
        snapshot_data = {}
        if snapshot.file_system:
            snapshot_data["file_system"] = snapshot.file_system.model_dump()
        if snapshot.file_content:
            snapshot_data["file_content"] = snapshot.file_content.model_dump()
        if snapshot.browser:
            snapshot_data["browser"] = snapshot.browser.model_dump()
        if snapshot.terminal:
            snapshot_data["terminal"] = snapshot.terminal.model_dump()
        if snapshot.editor:
            snapshot_data["editor"] = snapshot.editor.model_dump()
        if snapshot.plan:
            snapshot_data["plan"] = snapshot.plan.model_dump()
        if snapshot.full_state:
            snapshot_data["full_state"] = snapshot.full_state

        return SnapshotDocument(
            snapshot_id=snapshot.id,
            session_id=snapshot.session_id,
            action_id=snapshot.action_id,
            sequence_number=snapshot.sequence_number,
            created_at=snapshot.created_at,
            snapshot_type=snapshot.snapshot_type.value,
            resource_path=snapshot.resource_path,
            snapshot_data=snapshot_data,
            is_compressed=snapshot.is_compressed,
            compressed_size_bytes=snapshot.compressed_size_bytes,
        )

    def _to_domain(self, doc: SnapshotDocument) -> StateSnapshot:
        """Convert MongoDB document to domain model."""
        from app.domain.models.snapshot import (
            BrowserSnapshot,
            EditorSnapshot,
            FileSnapshot,
            FileSystemSnapshot,
            PlanSnapshot,
            TerminalSnapshot,
        )

        snapshot = StateSnapshot(
            id=doc.snapshot_id,
            session_id=doc.session_id,
            action_id=doc.action_id,
            sequence_number=doc.sequence_number,
            created_at=doc.created_at,
            snapshot_type=SnapshotType(doc.snapshot_type),
            resource_path=doc.resource_path,
            is_compressed=doc.is_compressed,
            compressed_size_bytes=doc.compressed_size_bytes,
        )

        # Deserialize snapshot data based on type
        data = doc.snapshot_data
        if "file_system" in data:
            snapshot.file_system = FileSystemSnapshot.model_validate(data["file_system"])
        if "file_content" in data:
            snapshot.file_content = FileSnapshot.model_validate(data["file_content"])
        if "browser" in data:
            snapshot.browser = BrowserSnapshot.model_validate(data["browser"])
        if "terminal" in data:
            snapshot.terminal = TerminalSnapshot.model_validate(data["terminal"])
        if "editor" in data:
            snapshot.editor = EditorSnapshot.model_validate(data["editor"])
        if "plan" in data:
            snapshot.plan = PlanSnapshot.model_validate(data["plan"])
        if "full_state" in data:
            snapshot.full_state = data["full_state"]

        return snapshot

    async def save(self, snapshot: StateSnapshot) -> None:
        """Save a state snapshot."""
        doc = self._to_document(snapshot)
        try:
            existing = await SnapshotDocument.find_one(SnapshotDocument.snapshot_id == snapshot.id)
            if existing:
                for field, value in doc.model_dump(exclude={"id"}).items():
                    setattr(existing, field, value)
                await existing.save()
            else:
                await doc.insert()
        except DuplicateKeyError as e:
            logger.warning("Duplicate snapshot %s: %s", snapshot.id, e)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error saving snapshot %s: %s", snapshot.id, e)
            raise IntegrationException(f"Failed to save snapshot: {e}", service="mongodb") from e

    async def save_many(self, snapshots: list[StateSnapshot]) -> None:
        """Save multiple snapshots in a batch operation."""
        if not snapshots:
            return
        docs = [self._to_document(s) for s in snapshots]
        try:
            await SnapshotDocument.insert_many(docs)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error batch-saving %d snapshots: %s", len(snapshots), e)
            raise IntegrationException(f"Failed to batch-save snapshots: {e}", service="mongodb") from e

    async def find_by_id(self, snapshot_id: str) -> StateSnapshot | None:
        """Find a snapshot by its ID."""
        try:
            doc = await SnapshotDocument.find_one(SnapshotDocument.snapshot_id == snapshot_id)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding snapshot %s: %s", snapshot_id, e)
            return None
        return self._to_domain(doc) if doc else None

    async def find_by_session(self, session_id: str, limit: int | None = None) -> list[StateSnapshot]:
        """Find all snapshots for a session, ordered by sequence number."""
        try:
            query = SnapshotDocument.find(SnapshotDocument.session_id == session_id).sort("+sequence_number")
            if limit:
                query = query.limit(limit)
            docs = await query.to_list()
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding snapshots for session %s: %s", session_id, e)
            return []
        return [self._to_domain(doc) for doc in docs]

    async def find_by_action(self, action_id: str) -> StateSnapshot | None:
        """Find the snapshot associated with a specific action."""
        try:
            doc = await SnapshotDocument.find_one(SnapshotDocument.action_id == action_id)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding snapshot for action %s: %s", action_id, e)
            return None
        return self._to_domain(doc) if doc else None

    async def find_nearest_before(self, session_id: str, sequence_number: int) -> StateSnapshot | None:
        """Find the nearest snapshot at or before the given sequence number."""
        try:
            doc = (
                await SnapshotDocument.find(
                    SnapshotDocument.session_id == session_id, SnapshotDocument.sequence_number <= sequence_number
                )
                .sort("-sequence_number")
                .first_or_none()
            )
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding nearest snapshot for session %s: %s", session_id, e)
            return None
        return self._to_domain(doc) if doc else None

    async def find_nearest_before_time(self, session_id: str, timestamp: datetime) -> StateSnapshot | None:
        """Find the nearest snapshot at or before the given timestamp."""
        try:
            doc = (
                await SnapshotDocument.find(
                    SnapshotDocument.session_id == session_id, SnapshotDocument.created_at <= timestamp
                )
                .sort("-created_at")
                .first_or_none()
            )
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding nearest snapshot by time for session %s: %s", session_id, e)
            return None
        return self._to_domain(doc) if doc else None

    async def get_snapshots_in_range(
        self, session_id: str, start_sequence: int, end_sequence: int
    ) -> list[StateSnapshot]:
        """Get all snapshots within a sequence number range."""
        try:
            docs = (
                await SnapshotDocument.find(
                    SnapshotDocument.session_id == session_id,
                    SnapshotDocument.sequence_number >= start_sequence,
                    SnapshotDocument.sequence_number <= end_sequence,
                )
                .sort("+sequence_number")
                .to_list()
            )
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error getting snapshot range for session %s: %s", session_id, e)
            return []
        return [self._to_domain(doc) for doc in docs]

    async def count_by_session(self, session_id: str) -> int:
        """Count the number of snapshots for a session."""
        try:
            return await SnapshotDocument.find(SnapshotDocument.session_id == session_id).count()
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error counting snapshots for session %s: %s", session_id, e)
            return 0

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all snapshots for a session. Returns the number deleted."""
        try:
            result = await SnapshotDocument.find(SnapshotDocument.session_id == session_id).delete()
            return result.deleted_count if result else 0
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error deleting snapshots for session %s: %s", session_id, e)
            return 0

    async def delete_older_than(self, session_id: str, before_date: datetime) -> int:
        """Delete snapshots older than a given date for a specific session."""
        try:
            result = await SnapshotDocument.find(
                SnapshotDocument.session_id == session_id, SnapshotDocument.created_at < before_date
            ).delete()
            return result.deleted_count if result else 0
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error deleting old snapshots for session %s: %s", session_id, e)
            return 0

    async def delete_all_older_than(self, before_date: datetime) -> int:
        """Delete all snapshots older than the given date (cross-session TTL cleanup)."""
        try:
            result = await SnapshotDocument.find(SnapshotDocument.created_at < before_date).delete()
            return result.deleted_count if result else 0
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error deleting old snapshots: %s", e)
            return 0

    async def get_latest_full_snapshot(self, session_id: str) -> StateSnapshot | None:
        """Get the most recent full state snapshot for a session."""
        try:
            doc = (
                await SnapshotDocument.find(
                    SnapshotDocument.session_id == session_id,
                    SnapshotDocument.snapshot_type == SnapshotType.FULL_STATE.value,
                )
                .sort("-sequence_number")
                .first_or_none()
            )
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error getting latest full snapshot for session %s: %s", session_id, e)
            return None
        return self._to_domain(doc) if doc else None
