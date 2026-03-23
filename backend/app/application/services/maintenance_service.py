"""
Database maintenance service for cleaning up corrupted data.

This service provides utilities for maintaining data integrity in the database,
particularly for cleaning up events with invalid attachments that could cause
errors when fetching session data.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from beanie import PydanticObjectId

from app.core.config import get_settings
from app.domain.models.session import SessionStatus
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class MaintenanceService:
    """Service for database maintenance operations."""

    def __init__(self, db):
        """
        Initialize the maintenance service.

        Args:
            db: The MongoDB database instance
        """
        self._db = db

    async def cleanup_invalid_attachments(self, session_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        """
        Clean up events with invalid attachments (null file_id or filename).

        This fixes the issue where ReportEvent attachments were not properly
        synced to storage, resulting in FileNotFoundError when fetching sessions.

        Args:
            session_id: Optional specific session to clean up. If None, cleans all sessions.
            dry_run: If True, only reports what would be cleaned without making changes.

        Returns:
            Dict with cleanup statistics and details
        """
        sessions_collection = self._db.sessions

        stats = {
            "dry_run": dry_run,
            "sessions_scanned": 0,
            "sessions_affected": 0,
            "events_cleaned": 0,
            "attachments_removed": 0,
            "affected_sessions": [],
            "errors": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            # Build query
            query = {}
            if session_id:
                # Try both string ID and ObjectId
                try:
                    query["_id"] = PydanticObjectId(session_id)
                except Exception:
                    query["_id"] = session_id

            # Find sessions with events that have attachments
            cursor = sessions_collection.find({**query, "events": {"$exists": True}}, {"_id": 1, "events": 1})

            async for session in cursor:
                stats["sessions_scanned"] += 1
                session_id_str = str(session["_id"])
                events = session.get("events", [])

                events_to_update = []
                session_attachments_removed = 0

                for event_idx, event in enumerate(events):
                    if not event:
                        continue

                    attachments = event.get("attachments")
                    if not attachments:
                        continue

                    # Filter out invalid attachments
                    valid_attachments = []
                    invalid_count = 0

                    for attachment in attachments:
                        if attachment is None:
                            invalid_count += 1
                            continue

                        file_id = attachment.get("file_id")
                        filename = attachment.get("filename")

                        if not file_id or not filename:
                            invalid_count += 1
                            logger.debug(
                                f"Session {session_id_str}: Event {event_idx} "
                                f"has invalid attachment: file_id={file_id}, filename={filename}"
                            )
                        else:
                            valid_attachments.append(attachment)

                    if invalid_count > 0:
                        events_to_update.append(
                            {
                                "event_idx": event_idx,
                                "event_type": event.get("type", "unknown"),
                                "original_count": len(attachments),
                                "valid_count": len(valid_attachments),
                                "invalid_count": invalid_count,
                                "valid_attachments": valid_attachments or None,
                            }
                        )
                        session_attachments_removed += invalid_count

                if events_to_update:
                    stats["sessions_affected"] += 1
                    stats["events_cleaned"] += len(events_to_update)
                    stats["attachments_removed"] += session_attachments_removed

                    affected_session_info = {
                        "session_id": session_id_str,
                        "events_affected": len(events_to_update),
                        "attachments_removed": session_attachments_removed,
                        "event_details": [
                            {
                                "event_index": e["event_idx"],
                                "event_type": e["event_type"],
                                "attachments_before": e["original_count"],
                                "attachments_after": e["valid_count"],
                            }
                            for e in events_to_update
                        ],
                    }
                    stats["affected_sessions"].append(affected_session_info)

                    if not dry_run:
                        # Apply the updates
                        try:
                            for update_info in events_to_update:
                                event_idx = update_info["event_idx"]
                                valid_attachments = update_info["valid_attachments"]

                                await sessions_collection.update_one(
                                    {"_id": session["_id"]},
                                    {"$set": {f"events.{event_idx}.attachments": valid_attachments}},
                                )

                            logger.info(
                                f"Cleaned {len(events_to_update)} events in session {session_id_str}, "
                                f"removed {session_attachments_removed} invalid attachments"
                            )
                        except Exception as e:
                            error_msg = f"Failed to update session {session_id_str}: {e}"
                            logger.error(error_msg)
                            stats["errors"].append(error_msg)

            # Summary logging
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would clean {stats['events_cleaned']} events in "
                    f"{stats['sessions_affected']} sessions, removing "
                    f"{stats['attachments_removed']} invalid attachments"
                )
            else:
                logger.info(
                    f"Cleaned {stats['events_cleaned']} events in "
                    f"{stats['sessions_affected']} sessions, removed "
                    f"{stats['attachments_removed']} invalid attachments"
                )

        except Exception as e:
            error_msg = f"Maintenance operation failed: {e}"
            logger.exception(error_msg)
            stats["errors"].append(error_msg)

        return stats

    async def get_session_health(self, session_id: str) -> dict[str, Any]:
        """
        Get health status for a specific session's data integrity.

        Args:
            session_id: The session ID to check

        Returns:
            Dict with session health information
        """
        sessions_collection = self._db.sessions

        try:
            # Try both string ID and ObjectId
            try:
                query_id = PydanticObjectId(session_id)
            except Exception:
                query_id = session_id

            session = await sessions_collection.find_one({"_id": query_id}, {"_id": 1, "status": 1, "events": 1})

            if not session:
                return {"session_id": session_id, "found": False, "error": "Session not found"}

            events = session.get("events", [])

            health = {
                "session_id": session_id,
                "found": True,
                "status": session.get("status"),
                "total_events": len(events),
                "events_with_attachments": 0,
                "total_attachments": 0,
                "valid_attachments": 0,
                "invalid_attachments": 0,
                "issues": [],
            }

            for event_idx, event in enumerate(events):
                if not event:
                    health["issues"].append({"event_index": event_idx, "issue": "Null event"})
                    continue

                attachments = event.get("attachments")
                if not attachments:
                    continue

                health["events_with_attachments"] += 1
                health["total_attachments"] += len(attachments)

                for att_idx, attachment in enumerate(attachments):
                    if attachment is None:
                        health["invalid_attachments"] += 1
                        health["issues"].append(
                            {
                                "event_index": event_idx,
                                "event_type": event.get("type"),
                                "attachment_index": att_idx,
                                "issue": "Null attachment",
                            }
                        )
                    elif not attachment.get("file_id"):
                        health["invalid_attachments"] += 1
                        health["issues"].append(
                            {
                                "event_index": event_idx,
                                "event_type": event.get("type"),
                                "attachment_index": att_idx,
                                "issue": "Missing file_id",
                                "filename": attachment.get("filename"),
                                "file_path": attachment.get("file_path"),
                            }
                        )
                    elif not attachment.get("filename"):
                        health["invalid_attachments"] += 1
                        health["issues"].append(
                            {
                                "event_index": event_idx,
                                "event_type": event.get("type"),
                                "attachment_index": att_idx,
                                "issue": "Missing filename",
                                "file_id": attachment.get("file_id"),
                            }
                        )
                    else:
                        health["valid_attachments"] += 1

            health["is_healthy"] = len(health["issues"]) == 0

            return health

        except Exception as e:
            logger.exception(f"Failed to check session health for {session_id}: {e}")
            return {"session_id": session_id, "found": False, "error": str(e)}

    async def cleanup_stale_running_sessions(
        self,
        stale_threshold_minutes: int = 30,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """
        Clean up stale sessions with leaked runtime state.

        Rules:
        - Stale `running` / `initializing` sessions are marked `failed`
        - Stale `pending` sessions are only reset when runtime state leaked
          (`task_id` is set or an owned sandbox is attached). They are kept
          in `pending` status so idle sessions remain usable.

        Args:
            stale_threshold_minutes: Consider sessions stale if updated before this threshold.
            dry_run: If True, only reports what would be cleaned without making changes.

        Returns:
            Dict with cleanup statistics and details
        """
        sessions_collection = self._db.sessions

        stats = {
            "dry_run": dry_run,
            "stale_threshold_minutes": stale_threshold_minutes,
            "sessions_cleaned": 0,
            "sandboxes_destroyed": 0,
            "sessions_marked_failed": [],
            "sessions_reset_pending": [],
            "sessions_skipped": [],
            "errors": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            # Calculate stale cutoff time
            cutoff_time = datetime.now(UTC) - timedelta(minutes=stale_threshold_minutes)

            active_stale_statuses = [SessionStatus.RUNNING.value, SessionStatus.INITIALIZING.value]
            query = {
                "updated_at": {"$lt": cutoff_time},
                "$or": [
                    {"status": {"$in": active_stale_statuses}},
                    {
                        "status": SessionStatus.PENDING.value,
                        "$or": [
                            {"task_id": {"$ne": None}},
                            {"sandbox_id": {"$ne": None}},
                        ],
                    },
                ],
            }

            cursor = sessions_collection.find(
                query,
                {
                    "_id": 1,
                    "status": 1,
                    "updated_at": 1,
                    "title": 1,
                    "sandbox_id": 1,
                    "sandbox_owned": 1,
                    "sandbox_lifecycle_mode": 1,
                    "task_id": 1,
                },
            )

            async for session in cursor:
                session_id_str = str(session["_id"])
                old_status = session.get("status")
                updated_at = session.get("updated_at")
                sandbox_id = session.get("sandbox_id")
                task_id = session.get("task_id")
                sandbox_owned = bool(session.get("sandbox_owned", False))
                sandbox_lifecycle_mode = session.get("sandbox_lifecycle_mode")
                configured_lifecycle_mode = getattr(get_settings(), "sandbox_lifecycle_mode", "static")
                sandbox_is_owned = sandbox_owned or sandbox_lifecycle_mode == "ephemeral"
                if sandbox_lifecycle_mode is None and configured_lifecycle_mode == "ephemeral":
                    sandbox_is_owned = True

                mark_failed = old_status in active_stale_statuses
                pending_has_runtime_leak = bool(task_id) or bool(sandbox_id and sandbox_is_owned)
                if not mark_failed and not pending_has_runtime_leak:
                    stats["sessions_skipped"].append(
                        {
                            "session_id": session_id_str,
                            "status": old_status,
                            "reason": "pending_without_owned_sandbox_or_task",
                            "sandbox_id": sandbox_id,
                            "sandbox_owned": sandbox_is_owned,
                            "task_id": task_id,
                            "last_updated": updated_at.isoformat() if updated_at else None,
                        }
                    )
                    continue

                action = "mark_failed" if mark_failed else "reset_pending_runtime"
                session_info = {
                    "session_id": session_id_str,
                    "old_status": old_status,
                    "new_status": SessionStatus.FAILED.value if mark_failed else SessionStatus.PENDING.value,
                    "action": action,
                    "title": session.get("title"),
                    "sandbox_id": sandbox_id,
                    "sandbox_owned": sandbox_is_owned,
                    "task_id": task_id,
                    "last_updated": updated_at.isoformat() if updated_at else None,
                }
                if mark_failed:
                    stats["sessions_marked_failed"].append(session_info)
                else:
                    stats["sessions_reset_pending"].append(session_info)
                stats["sessions_cleaned"] += 1

                if not dry_run:
                    # Destroy orphaned sandbox container
                    if sandbox_id and sandbox_is_owned:
                        try:
                            from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox

                            sandbox = await DockerSandbox.get(sandbox_id)
                            if sandbox:
                                await asyncio.wait_for(sandbox.destroy(), timeout=15.0)
                                stats["sandboxes_destroyed"] += 1
                                logger.info(
                                    f"Destroyed orphaned owned sandbox {sandbox_id} for stale session {session_id_str}"
                                )
                        except TimeoutError:
                            logger.warning(f"Sandbox {sandbox_id} destroy timed out during stale cleanup")
                        except Exception as e:
                            logger.warning(f"Failed to destroy sandbox {sandbox_id}: {e}")

                    try:
                        update_fields: dict[str, Any] = {
                            "status": SessionStatus.FAILED.value if mark_failed else SessionStatus.PENDING.value,
                            "updated_at": datetime.now(UTC),
                            "task_id": None,
                        }
                        if mark_failed or sandbox_is_owned:
                            update_fields.update(
                                {
                                    "sandbox_id": None,
                                    "sandbox_owned": False,
                                    "sandbox_created_at": None,
                                }
                            )

                        await sessions_collection.update_one(
                            {"_id": session["_id"]},
                            {"$set": update_fields},
                        )
                        if mark_failed:
                            logger.info(
                                f"Marked stale session {session_id_str} as failed "
                                f"(was {old_status}, last updated: {updated_at})"
                            )
                        else:
                            logger.info(
                                f"Reset stale pending runtime for session {session_id_str} "
                                f"(task_id={task_id}, sandbox_id={sandbox_id}, last updated: {updated_at})"
                            )
                    except Exception as e:
                        error_msg = f"Failed to update session {session_id_str}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)

            # Summary logging
            if dry_run:
                logger.info(
                    "[DRY RUN] Would clean %d stale sessions (%d failed, %d pending-reset, %d skipped)",
                    stats["sessions_cleaned"],
                    len(stats["sessions_marked_failed"]),
                    len(stats["sessions_reset_pending"]),
                    len(stats["sessions_skipped"]),
                )
            else:
                # Suppress noise when nothing was cleaned — use debug level for zero-action runs
                _total_actions = stats["sessions_cleaned"] + stats["sandboxes_destroyed"]
                _log = logger.info if _total_actions > 0 else logger.debug
                _log(
                    "Cleaned %d stale sessions (%d failed, %d pending-reset, %d skipped), "
                    "destroyed %d orphaned sandboxes",
                    stats["sessions_cleaned"],
                    len(stats["sessions_marked_failed"]),
                    len(stats["sessions_reset_pending"]),
                    len(stats["sessions_skipped"]),
                    stats["sandboxes_destroyed"],
                )

        except Exception as e:
            error_msg = f"Stale session cleanup failed: {e}"
            logger.exception(error_msg)
            stats["errors"].append(error_msg)

        return stats

    async def cleanup_empty_cancelled_sessions(
        self,
        age_threshold_hours: int = 24,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """
        Clean up empty cancelled sessions with no content or history.

        Removes sessions where ALL of these are true:
        - title is None
        - status == "cancelled"
        - latest_message is None
        - created_at is older than age_threshold_hours

        Args:
            age_threshold_hours: Consider sessions stale if created before this threshold.
            dry_run: If True, only reports what would be cleaned without making changes.

        Returns:
            Dict with cleanup statistics and details
        """
        sessions_collection = self._db.sessions

        stats = {
            "dry_run": dry_run,
            "age_threshold_hours": age_threshold_hours,
            "sessions_scanned": 0,
            "sessions_deleted": 0,
            "deleted_sessions": [],
            "errors": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }

        try:
            # Calculate age cutoff time
            cutoff_time = datetime.now(UTC) - timedelta(hours=age_threshold_hours)

            # Query for sessions matching all deletion criteria
            query = {
                "title": None,
                "status": SessionStatus.CANCELLED.value,
                "latest_message": None,
                "created_at": {"$lt": cutoff_time},
            }

            cursor = sessions_collection.find(
                query,
                {
                    "_id": 1,
                    "title": 1,
                    "status": 1,
                    "latest_message": 1,
                    "created_at": 1,
                },
            )

            sessions_to_delete = []
            async for session in cursor:
                stats["sessions_scanned"] += 1
                session_id_str = str(session["_id"])
                created_at = session.get("created_at")

                session_info = {
                    "session_id": session_id_str,
                    "title": session.get("title"),
                    "status": session.get("status"),
                    "latest_message": session.get("latest_message"),
                    "created_at": created_at.isoformat() if created_at else None,
                }
                stats["deleted_sessions"].append(session_info)
                sessions_to_delete.append(session["_id"])

            stats["sessions_deleted"] = len(sessions_to_delete)

            if not dry_run and sessions_to_delete:
                try:
                    result = await sessions_collection.delete_many({"_id": {"$in": sessions_to_delete}})
                    logger.info(
                        f"Deleted {result.deleted_count} empty cancelled sessions "
                        f"(age threshold: {age_threshold_hours}h)"
                    )
                except Exception as e:
                    error_msg = f"Failed to delete empty cancelled sessions: {e}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)

            # Summary logging
            if dry_run:
                logger.info(
                    "[DRY RUN] Would delete %d empty cancelled sessions (age threshold: %dh)",
                    stats["sessions_deleted"],
                    age_threshold_hours,
                )
            else:
                logger.info(
                    "Deleted %d empty cancelled sessions (age threshold: %dh)",
                    stats["sessions_deleted"],
                    age_threshold_hours,
                )

        except Exception as e:
            error_msg = f"Empty cancelled session cleanup failed: {e}"
            logger.exception(error_msg)
            stats["errors"].append(error_msg)

        return stats

    async def cleanup_old_screenshots(self, ttl_days: int = 30) -> dict[str, Any]:
        """Delete screenshots (metadata + MinIO objects) older than ttl_days.

        Strategy: fetch exact expired records, delete only their specific
        object keys, then remove matching Mongo documents. Fresh screenshots
        in mixed-age sessions are never touched.
        """
        stats: dict[str, Any] = {
            "ttl_days": ttl_days,
            "objects_deleted": 0,
            "documents_deleted": 0,
            "errors": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            from app.infrastructure.repositories.mongo_screenshot_repository import MongoScreenshotRepository
            from app.infrastructure.storage.minio_storage import get_minio_storage

            cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
            repo = MongoScreenshotRepository()
            minio = get_minio_storage()

            # Fetch exact expired records (record-level precision)
            expired = await repo.find_expired_screenshots(cutoff)
            if not expired:
                logger.debug("Screenshot TTL cleanup: no expired screenshots found")
                return stats

            # Build exact object key delete lists
            storage_keys = [s.storage_key for s in expired if s.storage_key]
            thumbnail_keys = [s.thumbnail_storage_key for s in expired if s.thumbnail_storage_key]

            # Delete only those specific MinIO objects
            try:
                obj_count = await minio.delete_screenshot_objects(storage_keys, thumbnail_keys)
                stats["objects_deleted"] = obj_count
            except Exception as e:
                stats["errors"].append(f"MinIO object delete failed: {e}")
                logger.warning("Screenshot TTL cleanup: MinIO delete failed: %s", e)

            # Delete only the expired Mongo documents
            expired_ids = [s.id for s in expired]
            deleted = await repo.delete_by_ids(expired_ids)
            stats["documents_deleted"] = deleted

            logger.info(
                "Screenshot TTL cleanup: deleted %d documents, %d objects (ttl=%d days)",
                deleted,
                stats["objects_deleted"],
                ttl_days,
            )
        except Exception as e:
            error_msg = f"Screenshot TTL cleanup failed: {e}"
            logger.exception(error_msg)
            stats["errors"].append(error_msg)

        return stats

    async def cleanup_old_snapshots(self, ttl_days: int = 7) -> dict[str, Any]:
        """Delete snapshot documents older than ttl_days."""
        stats: dict[str, Any] = {
            "ttl_days": ttl_days,
            "documents_deleted": 0,
            "errors": [],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            from app.infrastructure.repositories.mongo_snapshot_repository import MongoSnapshotRepository

            cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
            repo = MongoSnapshotRepository()
            deleted = await repo.delete_all_older_than(cutoff)
            stats["documents_deleted"] = deleted

            if deleted > 0:
                logger.info(
                    "Snapshot TTL cleanup: deleted %d documents (ttl=%d days)",
                    deleted,
                    ttl_days,
                )
        except Exception as e:
            error_msg = f"Snapshot TTL cleanup failed: {e}"
            logger.exception(error_msg)
            stats["errors"].append(error_msg)

        return stats


# Factory function for dependency injection
def get_maintenance_service(db=None) -> MaintenanceService:
    """Get a MaintenanceService instance.

    When db is omitted, resolve it from configured MongoDB settings.
    """
    if db is None:
        settings = get_settings()
        db = get_mongodb().client[settings.mongodb_database]
    return MaintenanceService(db)
