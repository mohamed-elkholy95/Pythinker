"""MongoDB Checkpointer for LangGraph.

This module implements a LangGraph checkpoint saver using MongoDB,
enabling persistent state across workflow executions.
"""

import importlib
import importlib.util
import json
import logging
import sys
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig


def _import_from_site_packages(module_path: str):
    """Import a module directly from site-packages, bypassing local shadowing."""
    import site

    # Get site-packages directories
    site_packages = site.getsitepackages()
    if hasattr(site, "getusersitepackages"):
        user_site = site.getusersitepackages()
        if user_site:
            site_packages.append(user_site)

    # Find the langgraph package
    for sp in site_packages:
        pkg_path = Path(sp) / "langgraph"
        if pkg_path.exists():
            # Found it! Import from here
            checkpoint_init = pkg_path / "checkpoint" / "base" / "__init__.py"
            if checkpoint_init.exists():
                spec = importlib.util.spec_from_file_location("langgraph_checkpoint_base", checkpoint_init)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module

    raise ImportError(f"Could not find langgraph package in site-packages: {site_packages}")


def _get_checkpoint_classes():
    """Get checkpoint classes, handling import shadowing during pytest."""
    # First, check if the correct module is already loaded
    if "langgraph.checkpoint.base" in sys.modules:
        mod = sys.modules["langgraph.checkpoint.base"]
        if hasattr(mod, "BaseCheckpointSaver"):
            return (
                mod.BaseCheckpointSaver,
                mod.ChannelVersions,
                mod.Checkpoint,
                mod.CheckpointMetadata,
                mod.CheckpointTuple,
                mod.get_checkpoint_id,
            )

    try:
        # Try direct import
        from langgraph.checkpoint.base import (
            BaseCheckpointSaver,
            ChannelVersions,
            Checkpoint,
            CheckpointMetadata,
            CheckpointTuple,
            get_checkpoint_id,
        )

        return (
            BaseCheckpointSaver,
            ChannelVersions,
            Checkpoint,
            CheckpointMetadata,
            CheckpointTuple,
            get_checkpoint_id,
        )
    except (ImportError, ModuleNotFoundError, AttributeError):
        # Direct import failed (likely due to shadowing), use file-based import
        mod = _import_from_site_packages("langgraph.checkpoint.base")
        return (
            mod.BaseCheckpointSaver,
            mod.ChannelVersions,
            mod.Checkpoint,
            mod.CheckpointMetadata,
            mod.CheckpointTuple,
            mod.get_checkpoint_id,
        )


# Get the checkpoint classes
(
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
) = _get_checkpoint_classes()

logger = logging.getLogger(__name__)


class MongoDBCheckpointer(BaseCheckpointSaver):
    """MongoDB-based checkpoint saver for LangGraph.

    This checkpointer uses Motor (async MongoDB driver) to store and retrieve
    workflow checkpoints, enabling persistence and resume capabilities.

    The checkpointer stores checkpoints in a `langgraph_checkpoints` collection
    and pending writes in a `langgraph_writes` collection.

    Usage:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client["pythinker"]
        checkpointer = MongoDBCheckpointer(db)

        graph = create_plan_act_graph(checkpointer=checkpointer)
    """

    def __init__(
        self,
        db: Any,  # AsyncIOMotorDatabase
        checkpoint_collection: str = "langgraph_checkpoints",
        writes_collection: str = "langgraph_writes",
    ):
        """Initialize the MongoDB checkpointer.

        Args:
            db: Motor async MongoDB database instance
            checkpoint_collection: Name of the checkpoints collection
            writes_collection: Name of the pending writes collection
        """
        super().__init__()
        self.db = db
        self._checkpoints = db[checkpoint_collection]
        self._writes = db[writes_collection]

    @asynccontextmanager
    async def _cursor_context(self, cursor):
        """Context manager for MongoDB cursor cleanup."""
        try:
            yield cursor
        finally:
            pass  # Motor cursors don't need explicit close

    def _config_to_query(
        self,
        config: RunnableConfig,
        checkpoint_ns: str = "",
    ) -> dict[str, Any]:
        """Convert config to MongoDB query.

        Args:
            config: Runnable config with thread_id
            checkpoint_ns: Checkpoint namespace

        Returns:
            MongoDB query dictionary
        """
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        checkpoint_id = configurable.get("checkpoint_id")

        query: dict[str, Any] = {"thread_id": thread_id}

        if checkpoint_ns:
            query["checkpoint_ns"] = checkpoint_ns
        else:
            query["checkpoint_ns"] = ""

        if checkpoint_id:
            query["checkpoint_id"] = checkpoint_id

        return query

    def _serialize_checkpoint(self, checkpoint: Checkpoint) -> dict[str, Any]:
        """Serialize a checkpoint for MongoDB storage.

        Args:
            checkpoint: Checkpoint to serialize

        Returns:
            MongoDB-compatible dictionary
        """
        # Convert checkpoint to a serializable format
        # Note: Some values may need special handling for complex types
        return {
            "v": checkpoint.get("v", 1),
            "ts": checkpoint.get("ts", datetime.now(UTC).isoformat()),
            "id": checkpoint.get("id"),
            "channel_values": self._serialize_channel_values(checkpoint.get("channel_values", {})),
            "channel_versions": checkpoint.get("channel_versions", {}),
            "versions_seen": checkpoint.get("versions_seen", {}),
            "pending_sends": checkpoint.get("pending_sends", []),
        }

    def _serialize_channel_values(self, channel_values: dict[str, Any]) -> dict[str, Any]:
        """Serialize channel values, handling non-serializable objects.

        Agent instances and other non-serializable objects are excluded
        from serialization since they're injected at runtime.

        Args:
            channel_values: Dictionary of channel values

        Returns:
            Serializable dictionary
        """
        serialized = {}
        # Keys to skip (non-serializable agent/tool instances)
        skip_keys = {"planner", "executor", "verifier", "reflection_agent", "task_state_manager", "user_message"}

        for key, value in channel_values.items():
            if key in skip_keys:
                continue
            try:
                # Try to serialize as JSON to verify it's serializable
                json.dumps(value, default=str)
                serialized[key] = value
            except (TypeError, ValueError):
                # Skip non-serializable values
                logger.debug(f"Skipping non-serializable channel value: {key}")
                continue

        return serialized

    def _deserialize_checkpoint(self, doc: dict[str, Any]) -> Checkpoint:
        """Deserialize a checkpoint from MongoDB.

        Args:
            doc: MongoDB document

        Returns:
            Checkpoint object
        """
        return {
            "v": doc.get("v", 1),
            "ts": doc.get("ts"),
            "id": doc.get("id") or doc.get("checkpoint_id"),
            "channel_values": doc.get("channel_values", {}),
            "channel_versions": doc.get("channel_versions", {}),
            "versions_seen": doc.get("versions_seen", {}),
            "pending_sends": doc.get("pending_sends", []),
        }

    # Async methods for async graph execution

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get a checkpoint tuple for the given config.

        Args:
            config: Config with thread_id and optional checkpoint_id

        Returns:
            CheckpointTuple if found, None otherwise
        """
        configurable = config.get("configurable", {})
        checkpoint_ns = configurable.get("checkpoint_ns", "")

        query = self._config_to_query(config, checkpoint_ns)

        # Find the most recent checkpoint
        doc = await self._checkpoints.find_one(query, sort=[("ts", -1)])

        if not doc:
            return None

        checkpoint = self._deserialize_checkpoint(doc)

        # Build the config for this checkpoint
        checkpoint_config: RunnableConfig = {
            "configurable": {
                "thread_id": doc["thread_id"],
                "checkpoint_ns": doc.get("checkpoint_ns", ""),
                "checkpoint_id": doc.get("checkpoint_id") or checkpoint.get("id"),
            }
        }

        # Get pending writes for this checkpoint
        writes_cursor = self._writes.find(
            {
                "thread_id": doc["thread_id"],
                "checkpoint_ns": doc.get("checkpoint_ns", ""),
                "checkpoint_id": doc.get("checkpoint_id") or checkpoint.get("id"),
            }
        )
        pending_writes = []
        async for write_doc in writes_cursor:
            pending_writes.append(
                (
                    write_doc.get("task_id", ""),
                    write_doc.get("channel"),
                    write_doc.get("value"),
                )
            )

        return CheckpointTuple(
            config=checkpoint_config,
            checkpoint=checkpoint,
            metadata=doc.get("metadata", {}),
            parent_config=None,  # Could be enhanced to track parent
            pending_writes=pending_writes,
        )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Store a checkpoint.

        Args:
            config: Config with thread_id
            checkpoint: Checkpoint to store
            metadata: Associated metadata
            new_versions: New channel versions

        Returns:
            Config for the stored checkpoint
        """
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = checkpoint.get("id") or get_checkpoint_id()

        # P1.4: Track parent checkpoint for lineage/branching support
        # The current checkpoint_id in config is the parent (we're creating a new one)
        parent_checkpoint_id = configurable.get("checkpoint_id")

        doc = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,  # P1.4: Track lineage
            **self._serialize_checkpoint(checkpoint),
            "metadata": metadata,
            "new_versions": new_versions,
            "updated_at": datetime.now(UTC),
        }

        # Upsert the checkpoint
        await self._checkpoints.update_one(
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
            {"$set": doc},
            upsert=True,
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Store pending writes.

        Args:
            config: Config with thread_id and checkpoint_id
            writes: List of (channel, value) tuples
            task_id: ID of the task that produced the writes
        """
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable.get("checkpoint_id")

        if not writes:
            return

        docs = []
        for channel, value in writes:
            try:
                # Verify serializable
                json.dumps(value, default=str)
                docs.append(
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "task_id": task_id,
                        "channel": channel,
                        "value": value,
                        "created_at": datetime.now(UTC),
                    }
                )
            except (TypeError, ValueError):
                logger.debug(f"Skipping non-serializable write for channel: {channel}")
                continue

        if docs:
            await self._writes.insert_many(docs)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints matching the given criteria.

        Args:
            config: Optional config to filter by thread_id
            filter: Additional filter criteria
            before: Config for pagination (checkpoints before this one)
            limit: Maximum number of results

        Yields:
            CheckpointTuple for each matching checkpoint
        """
        query: dict[str, Any] = {}

        if config:
            configurable = config.get("configurable", {})
            if thread_id := configurable.get("thread_id"):
                query["thread_id"] = thread_id
            if checkpoint_ns := configurable.get("checkpoint_ns"):
                query["checkpoint_ns"] = checkpoint_ns

        if filter:
            query.update(filter)

        if before:
            before_configurable = before.get("configurable", {})
            if before_ts := before_configurable.get("ts"):
                query["ts"] = {"$lt": before_ts}

        cursor = self._checkpoints.find(query).sort("ts", -1)

        if limit:
            cursor = cursor.limit(limit)

        async for doc in cursor:
            checkpoint = self._deserialize_checkpoint(doc)

            checkpoint_config: RunnableConfig = {
                "configurable": {
                    "thread_id": doc["thread_id"],
                    "checkpoint_ns": doc.get("checkpoint_ns", ""),
                    "checkpoint_id": doc.get("checkpoint_id") or checkpoint.get("id"),
                }
            }

            yield CheckpointTuple(
                config=checkpoint_config,
                checkpoint=checkpoint,
                metadata=doc.get("metadata", {}),
                parent_config=None,
                pending_writes=[],
            )

    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes for a thread.

        Args:
            thread_id: ID of the thread to delete
        """
        await self._checkpoints.delete_many({"thread_id": thread_id})
        await self._writes.delete_many({"thread_id": thread_id})
        logger.info(f"Deleted all checkpoints for thread: {thread_id}")

    # Sync methods (required by interface but raise for async-only usage)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Sync get_tuple - not supported, use aget_tuple."""
        raise NotImplementedError("MongoDBCheckpointer only supports async operations. Use aget_tuple instead.")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Sync put - not supported, use aput."""
        raise NotImplementedError("MongoDBCheckpointer only supports async operations. Use aput instead.")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Sync put_writes - not supported, use aput_writes."""
        raise NotImplementedError("MongoDBCheckpointer only supports async operations. Use aput_writes instead.")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """Sync list - not supported, use alist."""
        raise NotImplementedError("MongoDBCheckpointer only supports async operations. Use alist instead.")
