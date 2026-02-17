"""
Event Store Repository - Append-only event log with MongoDB.

Implements event sourcing pattern:
- Immutable events (never updated)
- Append-only writes
- Monotonic sequence numbers
- NO TTL on source events (projections can have TTL)
"""

import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import ClassVar

from beanie import Document
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field

from app.domain.exceptions.base import DuplicateResourceException
from app.domain.models.agent_event import AgentEvent, AgentEventType

logger = logging.getLogger(__name__)


class AgentEventDocument(Document):
    """MongoDB document for agent events."""

    event_id: str = Field(index=True, unique=True)
    event_type: AgentEventType = Field(index=True)
    session_id: str = Field(index=True)
    task_id: str = Field(index=True)
    sequence: int = Field(index=True)
    timestamp: datetime = Field(index=True)
    payload: dict
    metadata: dict

    class Settings:
        name = "agent_events"  # Collection name
        # NO TTL INDEX - events are immutable source of truth
        indexes: ClassVar[list] = [
            "event_id",
            "event_type",
            "session_id",
            "task_id",
            "sequence",
            "timestamp",
            [("session_id", 1), ("sequence", 1)],  # Compound index for ordering
            [("task_id", 1), ("timestamp", 1)],
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

        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise DuplicateResourceException(f"Event {event.event_id} already exists") from e
            logger.error(f"Failed to append event {event.event_id}: {e}", exc_info=True)
            raise

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
