import logging
from datetime import UTC, datetime

from app.domain.models.event import BaseEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.models.documents import SessionDocument

logger = logging.getLogger(__name__)


class MongoSessionRepository(SessionRepository):
    """MongoDB implementation of SessionRepository"""

    async def save(self, session: Session) -> None:
        """Save or update a session"""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session.id)

        if not mongo_session:
            mongo_session = SessionDocument.from_domain(session)
            await mongo_session.save()
            return

        # Update fields from session domain model
        mongo_session.update_from_domain(session)
        await mongo_session.save()

    async def find_by_id(self, session_id: str) -> Session | None:
        """Find a session by its ID"""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        return mongo_session.to_domain() if mongo_session else None

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        """Find all sessions for a specific user"""
        mongo_sessions = (
            await SessionDocument.find(SessionDocument.user_id == user_id).sort("-latest_message_at").to_list()
        )
        return [mongo_session.to_domain() for mongo_session in mongo_sessions]

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Session | None:
        """Find a session by ID and user ID (for authorization)"""
        mongo_session = await SessionDocument.find_one(
            SessionDocument.session_id == session_id, SessionDocument.user_id == user_id
        )
        return mongo_session.to_domain() if mongo_session else None

    async def update_title(self, session_id: str, title: str) -> None:
        """Update the title of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"title": title, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        """Update the latest message of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"latest_message": message, "latest_message_at": timestamp, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        """Add an event to a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$push": {"events": event.model_dump()}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        """Add a file to a session, avoiding duplicates by file_id or file_path"""
        # First check if file already exists to avoid duplicates
        session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Check for existing file by file_id or file_path
        for existing_file in session.files or []:
            if file_info.file_id and existing_file.file_id == file_info.file_id:
                return  # File already exists by file_id, skip
            if file_info.file_path and existing_file.file_path == file_info.file_path:
                return  # File already exists by file_path, skip

        # Add file if not already present
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$push": {"files": file_info.model_dump()}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def remove_file(self, session_id: str, file_id: str) -> None:
        """Remove a file from a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$pull": {"files": {"file_id": file_id}}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def get_file_by_path(self, session_id: str, file_path: str) -> FileInfo | None:
        """Get file by path from a session"""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session:
            raise ValueError(f"Session {session_id} not found")

        # Search for file with matching path
        for file_info in mongo_session.files:
            if file_info.file_path == file_path:
                return file_info
        return None

    async def delete(self, session_id: str) -> None:
        """Delete a session"""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if mongo_session:
            await mongo_session.delete()

    async def get_all(self) -> list[Session]:
        """Get all sessions"""
        mongo_sessions = await SessionDocument.find().sort("-latest_message_at").to_list()
        return [mongo_session.to_domain() for mongo_session in mongo_sessions]

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        """Update the status of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"status": status, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        """Update the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"unread_message_count": count, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def increment_unread_message_count(self, session_id: str) -> None:
        """Atomically increment the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$inc": {"unread_message_count": 1}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def decrement_unread_message_count(self, session_id: str) -> None:
        """Atomically decrement the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$inc": {"unread_message_count": -1}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_shared_status(self, session_id: str, is_shared: bool) -> None:
        """Update the shared status of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"is_shared": is_shared, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_mode(self, session_id: str, mode: AgentMode) -> None:
        """Update the agent mode of a session (discuss/agent)"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"mode": mode.value, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_pending_action(
        self,
        session_id: str,
        pending_action: dict | None,
        status: str | None,
    ) -> None:
        """Update pending action details for confirmation flow."""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {
                "$set": {
                    "pending_action": pending_action,
                    "pending_action_status": status,
                    "updated_at": datetime.now(UTC),
                }
            }
        )
        if not result:
            raise ValueError(f"Session {session_id} not found")

    async def update_by_id(self, session_id: str, updates: dict) -> None:
        """Update session fields by ID with a dictionary of updates"""
        if not updates:
            return

        # Add updated_at timestamp
        updates["updated_at"] = datetime.now(UTC)

        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update({"$set": updates})
        if not result:
            raise ValueError(f"Session {session_id} not found")

    # Timeline query methods
    async def get_events_paginated(self, session_id: str, offset: int = 0, limit: int = 100) -> list[BaseEvent]:
        """Get paginated events for a session using MongoDB aggregation."""
        pipeline = [
            {"$match": {"session_id": session_id}},
            {"$project": {"events": {"$slice": ["$events", offset, limit]}}},
        ]
        results = await SessionDocument.aggregate(pipeline).to_list()
        if not results:
            return []
        return results[0].get("events", [])

    async def get_events_in_range(self, session_id: str, start_time: datetime, end_time: datetime) -> list[BaseEvent]:
        """Get events within a time range using MongoDB aggregation."""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session:
            return []

        # Filter events by timestamp
        return [
            event
            for event in mongo_session.events
            if hasattr(event, "timestamp") and start_time <= event.get("timestamp", start_time) <= end_time
        ]

    async def get_event_count(self, session_id: str) -> int:
        """Get the total number of events for a session."""
        pipeline = [{"$match": {"session_id": session_id}}, {"$project": {"count": {"$size": "$events"}}}]
        results = await SessionDocument.aggregate(pipeline).to_list()
        if not results:
            return 0
        return results[0].get("count", 0)

    async def get_event_by_sequence(self, session_id: str, sequence: int) -> BaseEvent | None:
        """Get an event by its sequence number (0-indexed position)."""
        pipeline = [
            {"$match": {"session_id": session_id}},
            {"$project": {"event": {"$arrayElemAt": ["$events", sequence]}}},
        ]
        results = await SessionDocument.aggregate(pipeline).to_list()
        if not results:
            return None
        return results[0].get("event")

    async def get_event_by_id(self, session_id: str, event_id: str) -> BaseEvent | None:
        """Get an event by its unique ID from the session's events array."""
        pipeline = [
            {"$match": {"session_id": session_id}},
            {
                "$project": {
                    "event": {"$filter": {"input": "$events", "as": "e", "cond": {"$eq": ["$$e.id", event_id]}}}
                }
            },
        ]
        results = await SessionDocument.aggregate(pipeline).to_list()
        if not results:
            return None
        events = results[0].get("event", [])
        return events[0] if events else None
