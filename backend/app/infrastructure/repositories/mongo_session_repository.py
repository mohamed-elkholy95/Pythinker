import logging
from datetime import UTC, datetime
from typing import Any

from app.domain.exceptions.base import BusinessRuleViolation, SessionNotFoundException
from app.domain.models.event import BaseEvent
from app.domain.models.file import FileInfo
from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.models.documents import SessionDocument

logger = logging.getLogger(__name__)


# Allowlist of fields that may be updated via the generic update_by_id method.
# Prevents NoSQL injection through arbitrary field names in $set operations.
# Fields correspond to SessionDocument attributes that domain services need
# to update dynamically (workspace init, complexity assessment, etc.).
ALLOWED_SESSION_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        # Workspace metadata
        "workspace_structure",
        "project_name",
        "project_path",
        "template_id",
        "template_used",
        "workspace_capabilities",
        "dev_command",
        "build_command",
        "test_command",
        "port",
        "env_var_keys",
        "secret_keys",
        "git_remote",
        # Execution metadata
        "complexity_score",
        "iteration_limit_override",
        # Budget tracking
        "budget_limit",
        "budget_warning_threshold",
        "budget_paused",
        # Multi-task
        "multi_task_challenge",
        # Session state
        "title",
        "status",
        "mode",
        "sandbox_id",
        "sandbox_owned",
        "sandbox_lifecycle_mode",
        "sandbox_created_at",
    }
)


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

    async def get_by_id(self, session_id: str) -> Session | None:
        """Backward-compatible alias for find_by_id."""
        return await self.find_by_id(session_id)

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
            raise SessionNotFoundException(session_id)

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        """Update the latest message of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"latest_message": message, "latest_message_at": timestamp, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        """Add an event to a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$push": {"events": event.model_dump()}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        """Add a file to a session, avoiding duplicates by file_id or file_path"""
        # First check if file already exists to avoid duplicates
        session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not session:
            raise SessionNotFoundException(session_id)

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
            raise SessionNotFoundException(session_id)

    async def remove_file(self, session_id: str, file_id: str) -> None:
        """Remove a file from a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$pull": {"files": {"file_id": file_id}}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def get_file_by_path(self, session_id: str, file_path: str) -> FileInfo | None:
        """Get file by path from a session"""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session:
            raise SessionNotFoundException(session_id)

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
            raise SessionNotFoundException(session_id)

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        """Update the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"unread_message_count": count, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def increment_unread_message_count(self, session_id: str) -> None:
        """Atomically increment the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$inc": {"unread_message_count": 1}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def decrement_unread_message_count(self, session_id: str) -> None:
        """Atomically decrement the unread message count of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$inc": {"unread_message_count": -1}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def update_shared_status(self, session_id: str, is_shared: bool) -> None:
        """Update the shared status of a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"is_shared": is_shared, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def update_mode(self, session_id: str, mode: AgentMode) -> None:
        """Update the agent mode of a session (discuss/agent)"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$set": {"mode": mode.value, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

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
            raise SessionNotFoundException(session_id)

    async def update_by_id(self, session_id: str, updates: dict[str, Any]) -> None:
        """Update session fields by ID with a dictionary of updates.

        Only fields listed in ALLOWED_SESSION_UPDATE_FIELDS are accepted.
        Raises ValueError if any disallowed field names are provided.
        """
        if not updates:
            return

        # Validate all field names against allowlist to prevent NoSQL injection
        disallowed_fields = set(updates.keys()) - ALLOWED_SESSION_UPDATE_FIELDS
        if disallowed_fields:
            raise BusinessRuleViolation(
                f"Disallowed update fields: {', '.join(sorted(disallowed_fields))}. "
                f"Only these fields may be updated via update_by_id: "
                f"{', '.join(sorted(ALLOWED_SESSION_UPDATE_FIELDS))}"
            )

        # Build safe update payload with timestamp
        safe_updates = dict(updates)
        safe_updates["updated_at"] = datetime.now(UTC)

        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update({"$set": safe_updates})
        if not result:
            raise SessionNotFoundException(session_id)

    # Timeline query methods
    # Use find_one instead of aggregate to avoid AsyncIOMotorLatentCommandCursor await issues
    # (Beanie/Motor aggregate().to_list() can return cursor in some versions)
    async def get_events_paginated(self, session_id: str, offset: int = 0, limit: int = 100) -> list[BaseEvent]:
        """Get paginated events for a session."""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session or not mongo_session.events:
            return []
        events = mongo_session.events
        return list(events[offset : offset + limit])

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
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session or not mongo_session.events:
            return 0
        return len(mongo_session.events)

    async def get_event_by_sequence(self, session_id: str, sequence: int) -> BaseEvent | None:
        """Get an event by its sequence number (0-indexed position)."""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session or not mongo_session.events:
            return None
        events = mongo_session.events
        if 0 <= sequence < len(events):
            return events[sequence]
        return None

    async def get_event_by_id(self, session_id: str, event_id: str) -> BaseEvent | None:
        """Get an event by its unique ID from the session's events array."""
        mongo_session = await SessionDocument.find_one(SessionDocument.session_id == session_id)
        if not mongo_session or not mongo_session.events:
            return None
        for event in mongo_session.events:
            eid = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
            if eid == event_id:
                return event
        return None
