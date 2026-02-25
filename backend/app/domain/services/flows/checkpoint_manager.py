"""
Checkpoint/Resume system for workflow persistence.

Provides serialization of workflow state to MongoDB for recovery,
automatic checkpointing after stage completion, and resume detection
on session restart.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CheckpointStatus(str, Enum):
    """Status of a workflow checkpoint."""

    ACTIVE = "active"  # Currently executing
    PAUSED = "paused"  # Manually paused
    RESUMED = "resumed"  # Resumed from checkpoint
    COMPLETED = "completed"  # Workflow completed
    FAILED = "failed"  # Workflow failed
    EXPIRED = "expired"  # Checkpoint expired


@dataclass
class WorkflowCheckpoint:
    """
    Checkpoint data for a workflow.

    Stores complete workflow state for persistence and recovery.
    """

    workflow_id: str
    session_id: str
    stage_index: int
    completed_steps: list[str]
    step_results: dict[str, Any]
    status: CheckpointStatus
    workflow_data: dict[str, Any]  # Full workflow serialization
    context: dict[str, Any]  # Shared context
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "stage_index": self.stage_index,
            "completed_steps": self.completed_steps,
            "step_results": self.step_results,
            "status": self.status.value,
            "workflow_data": self.workflow_data,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowCheckpoint":
        """Create from dictionary."""
        return cls(
            workflow_id=data["workflow_id"],
            session_id=data["session_id"],
            stage_index=data["stage_index"],
            completed_steps=data.get("completed_steps", []),
            step_results=data.get("step_results", {}),
            status=CheckpointStatus(data.get("status", "active")),
            workflow_data=data.get("workflow_data", {}),
            context=data.get("context", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            metadata=data.get("metadata", {}),
        )

    def is_expired(self) -> bool:
        """Check if the checkpoint has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


class CheckpointManager:
    """
    Manages workflow checkpoints for persistence and recovery.

    Features:
    - Serialize workflow state to MongoDB
    - Automatic checkpoint after each stage completion
    - Resume detection on session restart
    - Intermediate result storage
    - Checkpoint expiration and cleanup
    """

    def __init__(
        self,
        mongodb_collection: Any | None = None,
        ttl_hours: int = 24,
        auto_cleanup: bool = True,
    ):
        """
        Initialize checkpoint manager.

        Args:
            mongodb_collection: MongoDB collection for storage (async)
            ttl_hours: Time-to-live for checkpoints in hours
            auto_cleanup: Automatically clean expired checkpoints
        """
        self._collection = mongodb_collection
        self._ttl_hours = ttl_hours
        self._auto_cleanup = auto_cleanup

        # In-memory fallback storage
        self._memory_storage: dict[str, WorkflowCheckpoint] = {}

        logger.info("CheckpointManager initialized")

    def _get_key(self, workflow_id: str, session_id: str) -> str:
        """Generate storage key for a checkpoint."""
        return f"{session_id}:{workflow_id}"

    async def save_checkpoint(
        self,
        workflow: Any,  # Workflow instance
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowCheckpoint | None:
        """
        Save a checkpoint for a workflow.

        Args:
            workflow: Workflow instance to checkpoint
            session_id: Session identifier
            metadata: Additional metadata

        Returns:
            Created WorkflowCheckpoint or None on failure
        """
        from datetime import timedelta

        from app.domain.services.flows.task_orchestrator import StageStatus, Workflow

        if not isinstance(workflow, Workflow):
            logger.error("Invalid workflow type for checkpoint")
            return None

        session_id = session_id or workflow.metadata.get("session_id", "default")

        # Determine current stage index
        stage_index = 0
        for i, stage in enumerate(workflow.stages):
            if stage.status in [StageStatus.RUNNING, StageStatus.PENDING]:
                stage_index = i
                break
            stage_index = i + 1

        # Collect completed steps
        completed_steps = []
        step_results = {}
        for stage in workflow.stages:
            for step in stage.steps:
                if step.status.value == "completed":
                    completed_steps.append(step.id)
                    if step.result:
                        step_results[step.id] = step.result

        # Create checkpoint
        checkpoint = WorkflowCheckpoint(
            workflow_id=workflow.id,
            session_id=session_id,
            stage_index=stage_index,
            completed_steps=completed_steps,
            step_results=step_results,
            status=CheckpointStatus.ACTIVE,
            workflow_data=workflow.to_dict(),
            context=workflow.context.copy(),
            expires_at=datetime.now(UTC) + timedelta(hours=self._ttl_hours),
            metadata=metadata or {},
        )

        # Save to storage
        key = self._get_key(workflow.id, session_id)

        if self._collection:
            try:
                await self._collection.update_one(
                    {"workflow_id": workflow.id, "session_id": session_id}, {"$set": checkpoint.to_dict()}, upsert=True
                )
                logger.debug(f"Saved checkpoint for workflow {workflow.id}")
            except Exception as e:
                logger.error(f"Failed to save checkpoint to MongoDB: {e}")
                # Fallback to memory
                self._memory_storage[key] = checkpoint
        else:
            self._memory_storage[key] = checkpoint

        return checkpoint

    async def load_checkpoint(
        self,
        workflow_id: str,
        session_id: str,
    ) -> WorkflowCheckpoint | None:
        """
        Load a checkpoint for a workflow.

        Args:
            workflow_id: Workflow identifier
            session_id: Session identifier

        Returns:
            WorkflowCheckpoint if found and valid, None otherwise
        """
        key = self._get_key(workflow_id, session_id)

        if self._collection:
            try:
                doc = await self._collection.find_one(
                    {
                        "workflow_id": workflow_id,
                        "session_id": session_id,
                    }
                )
                if doc:
                    checkpoint = WorkflowCheckpoint.from_dict(doc)
                    if not checkpoint.is_expired():
                        return checkpoint
                    logger.debug(f"Checkpoint for {workflow_id} has expired")
                    await self.delete_checkpoint(workflow_id, session_id)
            except Exception as e:
                logger.error(f"Failed to load checkpoint from MongoDB: {e}")
        else:
            checkpoint = self._memory_storage.get(key)
            if checkpoint and not checkpoint.is_expired():
                return checkpoint

        return None

    async def delete_checkpoint(
        self,
        workflow_id: str,
        session_id: str,
    ) -> bool:
        """
        Delete a checkpoint.

        Args:
            workflow_id: Workflow identifier
            session_id: Session identifier

        Returns:
            True if deleted, False otherwise
        """
        key = self._get_key(workflow_id, session_id)

        if self._collection:
            try:
                result = await self._collection.delete_one(
                    {
                        "workflow_id": workflow_id,
                        "session_id": session_id,
                    }
                )
                return result.deleted_count > 0
            except Exception as e:
                logger.error(f"Failed to delete checkpoint from MongoDB: {e}")
                return False
        else:
            if key in self._memory_storage:
                del self._memory_storage[key]
                return True

        return False

    async def list_checkpoints(
        self,
        session_id: str | None = None,
        status: CheckpointStatus | None = None,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List checkpoints with optional filters.

        Args:
            session_id: Filter by session
            status: Filter by status
            include_expired: Include expired checkpoints

        Returns:
            List of checkpoint metadata (not full data)
        """
        checkpoints = []

        if self._collection:
            try:
                query: dict[str, Any] = {}
                if session_id:
                    query["session_id"] = session_id
                if status:
                    query["status"] = status.value

                async for doc in self._collection.find(query):
                    checkpoint = WorkflowCheckpoint.from_dict(doc)
                    if include_expired or not checkpoint.is_expired():
                        checkpoints.append(
                            {
                                "workflow_id": checkpoint.workflow_id,
                                "session_id": checkpoint.session_id,
                                "status": checkpoint.status.value,
                                "stage_index": checkpoint.stage_index,
                                "completed_steps": len(checkpoint.completed_steps),
                                "created_at": checkpoint.created_at.isoformat(),
                                "updated_at": checkpoint.updated_at.isoformat(),
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to list checkpoints from MongoDB: {e}")
        else:
            for checkpoint in self._memory_storage.values():
                if session_id and checkpoint.session_id != session_id:
                    continue
                if status and checkpoint.status != status:
                    continue
                if not include_expired and checkpoint.is_expired():
                    continue

                checkpoints.append(
                    {
                        "workflow_id": checkpoint.workflow_id,
                        "session_id": checkpoint.session_id,
                        "status": checkpoint.status.value,
                        "stage_index": checkpoint.stage_index,
                        "completed_steps": len(checkpoint.completed_steps),
                        "created_at": checkpoint.created_at.isoformat(),
                        "updated_at": checkpoint.updated_at.isoformat(),
                    }
                )

        return checkpoints

    async def has_resumable_checkpoint(
        self,
        session_id: str,
    ) -> str | None:
        """
        Check if a session has a resumable checkpoint.

        Args:
            session_id: Session identifier

        Returns:
            Workflow ID if resumable checkpoint exists, None otherwise
        """
        checkpoints = await self.list_checkpoints(
            session_id=session_id,
            status=CheckpointStatus.ACTIVE,
        )

        if checkpoints:
            return checkpoints[0]["workflow_id"]

        # Also check paused
        checkpoints = await self.list_checkpoints(
            session_id=session_id,
            status=CheckpointStatus.PAUSED,
        )

        if checkpoints:
            return checkpoints[0]["workflow_id"]

        return None

    async def restore_workflow(
        self,
        workflow_id: str,
        session_id: str,
    ) -> Any | None:
        """
        Restore a workflow from checkpoint.

        Args:
            workflow_id: Workflow identifier
            session_id: Session identifier

        Returns:
            Restored Workflow instance or None
        """
        from app.domain.services.flows.task_orchestrator import Workflow

        checkpoint = await self.load_checkpoint(workflow_id, session_id)
        if not checkpoint:
            return None

        try:
            workflow = Workflow.from_dict(checkpoint.workflow_data)

            # Restore context
            workflow.context = checkpoint.context.copy()

            # Update checkpoint status
            checkpoint.status = CheckpointStatus.RESUMED
            checkpoint.updated_at = datetime.now(UTC)
            await self.save_checkpoint(workflow, session_id)

            logger.info(f"Restored workflow {workflow_id} from checkpoint")
            return workflow

        except Exception as e:
            logger.error(f"Failed to restore workflow from checkpoint: {e}")
            return None

    async def mark_completed(
        self,
        workflow_id: str,
        session_id: str,
    ) -> bool:
        """
        Mark a workflow checkpoint as completed.

        Args:
            workflow_id: Workflow identifier
            session_id: Session identifier

        Returns:
            True if updated, False otherwise
        """
        checkpoint = await self.load_checkpoint(workflow_id, session_id)
        if not checkpoint:
            return False

        checkpoint.status = CheckpointStatus.COMPLETED
        checkpoint.updated_at = datetime.now(UTC)

        key = self._get_key(workflow_id, session_id)

        if self._collection:
            try:
                await self._collection.update_one(
                    {"workflow_id": workflow_id, "session_id": session_id},
                    {
                        "$set": {
                            "status": CheckpointStatus.COMPLETED.value,
                            "updated_at": checkpoint.updated_at.isoformat(),
                        }
                    },
                )
                return True
            except Exception as e:
                logger.error(f"Failed to update checkpoint status: {e}")
                return False
        else:
            self._memory_storage[key] = checkpoint
            return True

    async def cleanup_expired(self) -> int:
        """
        Clean up expired checkpoints.

        Returns:
            Number of checkpoints cleaned up
        """
        cleaned = 0

        if self._collection:
            try:
                result = await self._collection.delete_many({"expires_at": {"$lt": datetime.now(UTC).isoformat()}})
                cleaned = result.deleted_count
            except Exception as e:
                logger.error(f"Failed to cleanup expired checkpoints: {e}")
        else:
            expired_keys = [key for key, cp in self._memory_storage.items() if cp.is_expired()]
            for key in expired_keys:
                del self._memory_storage[key]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired checkpoints")

        return cleaned

    async def get_step_result(
        self,
        workflow_id: str,
        session_id: str,
        step_id: str,
    ) -> Any | None:
        """
        Get a specific step result from a checkpoint.

        Args:
            workflow_id: Workflow identifier
            session_id: Session identifier
            step_id: Step identifier

        Returns:
            Step result if found, None otherwise
        """
        checkpoint = await self.load_checkpoint(workflow_id, session_id)
        if not checkpoint:
            return None

        return checkpoint.step_results.get(step_id)

    async def save_plan_checkpoint(
        self,
        session_id: str,
        plan_id: str,
        completed_steps: list[str],
        step_results: dict[str, Any],
        stage_index: int,
        metadata: dict[str, Any] | None = None,
    ) -> "WorkflowCheckpoint | None":
        """
        Save a plan-level checkpoint without requiring a Workflow object.

        Used by PlanActFlow to persist plan execution progress directly.
        Creates a WorkflowCheckpoint from plan data and stores it via the
        standard storage path (MongoDB or in-memory fallback).

        Args:
            session_id: Session identifier
            plan_id: Plan identifier (used as workflow_id)
            completed_steps: List of completed step IDs
            step_results: Map of step_id → result string
            stage_index: Current step index (0-based)
            metadata: Additional metadata dict

        Returns:
            Created WorkflowCheckpoint or None on failure
        """
        from datetime import timedelta

        try:
            checkpoint = WorkflowCheckpoint(
                workflow_id=plan_id,
                session_id=session_id,
                stage_index=stage_index,
                completed_steps=completed_steps,
                step_results=step_results,
                status=CheckpointStatus.ACTIVE,
                workflow_data={"plan_id": plan_id, "type": "plan"},
                context={},
                expires_at=datetime.now(UTC) + timedelta(hours=self._ttl_hours),
                metadata=metadata or {},
            )

            key = self._get_key(plan_id, session_id)

            if self._collection:
                try:
                    await self._collection.update_one(
                        {"workflow_id": plan_id, "session_id": session_id},
                        {"$set": checkpoint.to_dict()},
                        upsert=True,
                    )
                    logger.debug("Saved plan checkpoint for session %s step %d", session_id, stage_index)
                except Exception as mongo_err:
                    logger.error("Failed to save plan checkpoint to MongoDB: %s", mongo_err)
                    self._memory_storage[key] = checkpoint
            else:
                self._memory_storage[key] = checkpoint

            return checkpoint
        except Exception as e:
            logger.error("save_plan_checkpoint failed: %s", e)
            return None


# Singleton instance
_checkpoint_manager: CheckpointManager | None = None


def get_checkpoint_manager() -> CheckpointManager:
    """Get the global checkpoint manager singleton."""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager


def set_checkpoint_manager(manager: CheckpointManager) -> None:
    """Set the global checkpoint manager singleton."""
    global _checkpoint_manager
    _checkpoint_manager = manager
