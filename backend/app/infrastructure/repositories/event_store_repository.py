"""
Event Store Repository - Append-only event log with MongoDB.

Implements event sourcing pattern:
- Immutable events (never updated)
- Append-only writes
- Monotonic sequence numbers
- NO TTL on source events (projections can have TTL)
- Archival to cold collection for unbounded growth prevention
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import ClassVar

from beanie import Document
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field
from pymongo import IndexModel
from pymongo.errors import DuplicateKeyError

from app.domain.exceptions.base import DuplicateResourceException
from app.domain.models.agent_event import AgentEvent, AgentEventType

logger = logging.getLogger(__name__)


class AgentEventDocument(Document):
    """MongoDB document for agent events."""

    event_id: str = Field(index=True, unique=True)
    event_type: AgentEventType = Field(index=True)
    session_id: str  # Covered by compound (session_id, sequence) prefix
    task_id: str  # Covered by compound (task_id, timestamp) prefix
    sequence: int = Field(index=True)
    timestamp: datetime = Field(index=True)
    payload: dict
    metadata: dict

    class Settings:
        name = "agent_events"  # Collection name
        # TTL index on timestamp provides automatic cleanup of old events.
        # The archival background task copies events to agent_events_archive
        # BEFORE TTL deletion, so no data is lost. TTL = 90 days (7776000s).
        # Note: Standalone "session_id" and "task_id" indexes removed —
        # covered by compound prefixes (session_id,sequence) and (task_id,timestamp)
        # which serve both compound and prefix-only queries per MongoDB docs.
        indexes: ClassVar[list] = [
            "event_type",
            "sequence",
            [("session_id", 1), ("sequence", 1)],  # Compound index for ordering
            [("task_id", 1), ("timestamp", 1)],
            IndexModel([("timestamp", 1)], expireAfterSeconds=7_776_000),  # 90-day TTL
        ]


class EventStoreRepository:
    """
    Repository for append-only event storage.

    Features:
    - Immutable events (never updated)
    - Monotonic sequence numbers per session
    - NO TTL (events are source of truth)
    - Efficient querying by session/task/type
    """

    def __init__(self, db_client: AsyncIOMotorClient):
        self.db_client = db_client

    async def append_event(self, event: AgentEvent) -> None:
        """
        Append event to immutable log.

        Args:
            event: Agent event to append

        Raises:
            ValueError: If event already exists (duplicate event_id)
        """
        try:
            doc = AgentEventDocument(
                event_id=event.event_id,
                event_type=event.event_type,
                session_id=event.session_id,
                task_id=event.task_id,
                sequence=event.sequence,
                timestamp=event.timestamp,
                payload=event.payload,
                metadata=event.metadata,
            )
            await doc.insert()

            logger.debug(f"Appended event {event.event_type} (seq={event.sequence}) for session {event.session_id}")

        except DuplicateKeyError as e:
            raise DuplicateResourceException(f"Event {event.event_id} already exists") from e

    async def get_events_by_session(
        self,
        session_id: str,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[AgentEvent]:
        """
        Get all events for a session, ordered by sequence.

        Args:
            session_id: Session ID
            after_sequence: Only return events after this sequence number
            limit: Maximum number of events to return

        Returns:
            List of events ordered by sequence
        """
        query = {"session_id": session_id}
        if after_sequence is not None:
            query["sequence"] = {"$gt": after_sequence}

        cursor = AgentEventDocument.find(query).sort("sequence", 1)

        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list()

        return [
            AgentEvent(
                event_id=doc.event_id,
                event_type=doc.event_type,
                session_id=doc.session_id,
                task_id=doc.task_id,
                sequence=doc.sequence,
                timestamp=doc.timestamp,
                payload=doc.payload,
                metadata=doc.metadata,
            )
            for doc in docs
        ]

    async def get_events_by_task(
        self,
        task_id: str,
        limit: int | None = None,
    ) -> list[AgentEvent]:
        """
        Get all events for a task, ordered by timestamp.

        Args:
            task_id: Task ID
            limit: Maximum number of events to return

        Returns:
            List of events ordered by timestamp
        """
        cursor = AgentEventDocument.find({"task_id": task_id}).sort("timestamp", 1)

        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list()

        return [
            AgentEvent(
                event_id=doc.event_id,
                event_type=doc.event_type,
                session_id=doc.session_id,
                task_id=doc.task_id,
                sequence=doc.sequence,
                timestamp=doc.timestamp,
                payload=doc.payload,
                metadata=doc.metadata,
            )
            for doc in docs
        ]

    async def get_events_by_type(
        self,
        session_id: str,
        event_type: AgentEventType,
        limit: int | None = None,
    ) -> list[AgentEvent]:
        """
        Get all events of a specific type for a session.

        Args:
            session_id: Session ID
            event_type: Event type to filter
            limit: Maximum number of events to return

        Returns:
            List of events ordered by sequence
        """
        cursor = AgentEventDocument.find({"session_id": session_id, "event_type": event_type}).sort("sequence", 1)

        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list()

        return [
            AgentEvent(
                event_id=doc.event_id,
                event_type=doc.event_type,
                session_id=doc.session_id,
                task_id=doc.task_id,
                sequence=doc.sequence,
                timestamp=doc.timestamp,
                payload=doc.payload,
                metadata=doc.metadata,
            )
            for doc in docs
        ]

    async def stream_events(
        self,
        session_id: str,
        after_sequence: int = 0,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Stream events for a session in real-time.

        Args:
            session_id: Session ID
            after_sequence: Start streaming after this sequence

        Yields:
            Events as they are appended
        """
        # This would use MongoDB change streams for real-time updates
        # For now, just return existing events
        events = await self.get_events_by_session(session_id, after_sequence=after_sequence)
        for event in events:
            yield event

    async def get_next_sequence(self, session_id: str) -> int:
        """
        Get next sequence number for a session.

        Args:
            session_id: Session ID

        Returns:
            Next sequence number (1-indexed)
        """
        doc = await AgentEventDocument.find({"session_id": session_id}).sort("sequence", -1).limit(1).first_or_none()

        return (doc.sequence + 1) if doc else 1

    async def count_events(self, session_id: str) -> int:
        """
        Count total events for a session.

        Args:
            session_id: Session ID

        Returns:
            Total event count
        """
        return await AgentEventDocument.find({"session_id": session_id}).count()

    async def archive_events_before(self, cutoff: datetime, *, batch_size: int = 1000) -> int:
        """
        Archive events older than cutoff to the agent_events_archive collection.

        Copies events in batches to the archive collection, then deletes from source.
        This preserves event sourcing immutability while controlling disk growth.

        Args:
            cutoff: Archive events with timestamp before this datetime.
            batch_size: Number of events to process per batch.

        Returns:
            Total number of events archived.
        """
        from app.core.prometheus_metrics import event_store_archived_total

        source = AgentEventDocument.get_pymongo_collection()
        db = source.database
        archive = db["agent_events_archive"]

        total_archived = 0
        query = {"timestamp": {"$lt": cutoff}}

        while True:
            # Fetch a batch of old events
            cursor = source.find(query).sort("timestamp", 1).limit(batch_size)
            batch = await cursor.to_list(length=batch_size)
            if not batch:
                break

            # Insert into archive collection
            await archive.insert_many(batch, ordered=False)

            # Delete archived events from source by _id
            ids = [doc["_id"] for doc in batch]
            result = await source.delete_many({"_id": {"$in": ids}})
            archived_count = result.deleted_count
            total_archived += archived_count

            event_store_archived_total.inc(value=archived_count)
            logger.info(
                "Archived %d events (batch), total: %d",
                archived_count,
                total_archived,
            )

            # If batch was smaller than batch_size, we're done
            if len(batch) < batch_size:
                break

        if total_archived > 0:
            logger.info("Event archival complete: %d events moved to archive", total_archived)

        return total_archived
