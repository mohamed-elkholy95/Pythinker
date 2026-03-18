import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

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
        "task_id",
        "mode",
        "sandbox_id",
        "sandbox_owned",
        "sandbox_lifecycle_mode",
        "sandbox_created_at",
        # Telegram option commands
        "reasoning_visibility",
        "thinking_level",
        "verbose_mode",
        "elevated_mode",
    }
)


class MongoSessionRepository(SessionRepository):
    """MongoDB implementation of SessionRepository"""

    # Default projection for queries that don't need event/file payloads.
    # Matches the pattern already used by find_by_user_id and get_all.
    _LIGHT_PROJECTION: ClassVar[dict[str, int]] = {"events": 0, "files": 0}

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
        """Find a session by its ID (lightweight — excludes events/files)."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id},
            projection=self._LIGHT_PROJECTION,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.setdefault("events", [])
        doc.setdefault("files", [])
        if "session_id" in doc:
            doc["id"] = doc.pop("session_id")
        return Session.model_validate(doc)

    async def find_by_id_full(self, session_id: str) -> Session | None:
        """Find a session by its ID with full payload (includes events/files)."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id},
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.setdefault("events", [])
        doc.setdefault("files", [])
        if "session_id" in doc:
            doc["id"] = doc.pop("session_id")
        return Session.model_validate(doc)

    async def get_by_id(self, session_id: str) -> Session | None:
        """Backward-compatible alias for find_by_id."""
        return await self.find_by_id(session_id)

    async def find_by_user_id(self, user_id: str) -> list[Session]:
        """Find all sessions for a specific user.

        Uses projection to exclude heavy fields (events, files) for listing queries.
        This reduces document size by ~90% for sessions with many events.
        """
        collection = SessionDocument.get_pymongo_collection()
        cursor = collection.find(
            {"user_id": user_id},
            projection={"events": 0, "files": 0},
        ).sort("latest_message_at", -1)

        sessions: list[Session] = []
        async for doc in cursor:
            doc.pop("_id", None)
            doc.setdefault("events", [])
            doc.setdefault("files", [])
            # Rename document id field to domain id field
            if "session_id" in doc:
                doc["id"] = doc.pop("session_id")
            sessions.append(Session.model_validate(doc))
        return sessions

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Session | None:
        """Find a session by ID and user ID (lightweight — excludes events/files)."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id, "user_id": user_id},
            projection=self._LIGHT_PROJECTION,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.setdefault("events", [])
        doc.setdefault("files", [])
        if "session_id" in doc:
            doc["id"] = doc.pop("session_id")
        return Session.model_validate(doc)

    async def find_by_id_and_user_id_full(self, session_id: str, user_id: str) -> Session | None:
        """Find a session by ID and user ID with full payload (includes events/files)."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id, "user_id": user_id},
        )
        if not doc:
            return None
        doc.pop("_id", None)
        doc.setdefault("events", [])
        doc.setdefault("files", [])
        if "session_id" in doc:
            doc["id"] = doc.pop("session_id")
        return Session.model_validate(doc)

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
        """Add an event to a session.

        Uses $push + $each + $slice to keep only the most recent N events,
        preventing BSONDocumentTooLarge errors on long-running sessions.
        The atomic $inc on event_count tracks the true total regardless of trimming.
        """
        from app.core.config import get_settings

        limit = get_settings().mongodb_session_event_limit
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {
                "$push": {"events": {"$each": [event.model_dump()], "$slice": -limit}},
                "$inc": {"event_count": 1},
                "$set": {"updated_at": datetime.now(UTC)},
            }
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        """Add a file to a session, avoiding duplicates by file_id or file_path.

        Uses atomic conditional $push to avoid TOCTOU race conditions.
        """
        collection = SessionDocument.get_pymongo_collection()
        file_data = file_info.model_dump()

        # Build duplicate-exclusion filter: session must exist AND file must not already be present
        match_filter: dict = {"session_id": session_id}
        not_conditions = []
        if file_info.file_id:
            not_conditions.append({"files.file_id": {"$ne": file_info.file_id}})
        if file_info.file_path:
            not_conditions.append({"files.file_path": {"$ne": file_info.file_path}})
        if not_conditions:
            match_filter["$and"] = not_conditions

        # Atomic conditional push — only adds if no duplicate found
        result = await collection.update_one(
            match_filter,
            {"$push": {"files": file_data}, "$set": {"updated_at": datetime.now(UTC)}},
        )

        if result.matched_count == 0:
            # Either session doesn't exist or file already present — check which
            exists = await collection.count_documents({"session_id": session_id}, limit=1)
            if not exists:
                raise SessionNotFoundException(session_id)
            # else: file already exists, silently skip (same behavior as before)

    async def remove_file(self, session_id: str, file_id: str) -> None:
        """Remove a file from a session"""
        result = await SessionDocument.find_one(SessionDocument.session_id == session_id).update(
            {"$pull": {"files": {"file_id": file_id}}, "$set": {"updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise SessionNotFoundException(session_id)

    async def get_file_by_path(self, session_id: str, file_path: str) -> FileInfo | None:
        """Get file by path from a session (loads only files, not events)."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id},
            projection={"files": 1},
        )
        if not doc:
            raise SessionNotFoundException(session_id)

        # Search for file with matching path
        for file_data in doc.get("files") or []:
            if file_data.get("file_path") == file_path:
                if "filename" not in file_data and file_data.get("file_name"):
                    file_data = {**file_data, "filename": file_data["file_name"]}
                return FileInfo.model_validate(file_data)
        return None

    async def delete(self, session_id: str) -> None:
        """Delete a session (atomic single-operation delete)."""
        collection = SessionDocument.get_pymongo_collection()
        await collection.delete_one({"session_id": session_id})

    async def get_all(self, limit: int = 100) -> list[Session]:
        """Get all sessions (lightweight — excludes events/files)."""
        collection = SessionDocument.get_pymongo_collection()
        cursor = (
            collection.find(
                {},
                projection={"events": 0, "files": 0},
            )
            .sort("latest_message_at", -1)
            .limit(limit)
        )

        sessions: list[Session] = []
        async for doc in cursor:
            doc.pop("_id", None)
            doc.setdefault("events", [])
            doc.setdefault("files", [])
            if "session_id" in doc:
                doc["id"] = doc.pop("session_id")
            sessions.append(Session.model_validate(doc))
        return sessions

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
    # Uses MongoDB $slice projection to avoid loading entire events array into Python.
    async def get_events_paginated(self, session_id: str, offset: int = 0, limit: int = 100) -> list[BaseEvent]:
        """Get paginated events for a session using MongoDB $slice projection."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id},
            {"events": {"$slice": [offset, limit]}},
        )
        if not doc or not doc.get("events"):
            return []
        return doc["events"]

    async def get_events_in_range(self, session_id: str, start_time: datetime, end_time: datetime) -> list[BaseEvent]:
        """Get events within a time range using MongoDB aggregation $filter."""
        collection = SessionDocument.get_pymongo_collection()
        pipeline = [
            {"$match": {"session_id": session_id}},
            {
                "$project": {
                    "events": {
                        "$filter": {
                            "input": "$events",
                            "as": "ev",
                            "cond": {
                                "$and": [
                                    {"$gte": ["$$ev.timestamp", start_time]},
                                    {"$lte": ["$$ev.timestamp", end_time]},
                                ]
                            },
                        }
                    }
                }
            },
        ]
        async for doc in collection.aggregate(pipeline):
            return doc.get("events", [])
        return []

    async def get_event_count(self, session_id: str) -> int:
        """Get the total number of events using MongoDB $size aggregation."""
        collection = SessionDocument.get_pymongo_collection()
        pipeline = [
            {"$match": {"session_id": session_id}},
            {"$project": {"count": {"$size": {"$ifNull": ["$events", []]}}}},
        ]
        async for doc in collection.aggregate(pipeline):
            return doc.get("count", 0)
        return 0

    async def get_event_by_sequence(self, session_id: str, sequence: int) -> BaseEvent | None:
        """Get an event by its sequence number (0-indexed position) using $slice."""
        collection = SessionDocument.get_pymongo_collection()
        doc = await collection.find_one(
            {"session_id": session_id},
            {"events": {"$slice": [sequence, 1]}},
        )
        if not doc or not doc.get("events"):
            return None
        return doc["events"][0]

    async def get_event_by_id(self, session_id: str, event_id: str) -> BaseEvent | None:
        """Get an event by its unique ID using aggregation $filter."""
        collection = SessionDocument.get_pymongo_collection()
        pipeline = [
            {"$match": {"session_id": session_id}},
            {
                "$project": {
                    "events": {
                        "$filter": {
                            "input": "$events",
                            "as": "ev",
                            "cond": {"$eq": ["$$ev.id", event_id]},
                        }
                    }
                }
            },
        ]
        async for doc in collection.aggregate(pipeline):
            events = doc.get("events", [])
            return events[0] if events else None
        return None
