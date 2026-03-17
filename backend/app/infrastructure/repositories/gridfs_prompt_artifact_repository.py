"""GridFS implementation of PromptArtifactRepository.

DSPy optimizer programs are serialized as JSON blobs and stored in MongoDB
GridFS so they can be large (100s of KB) without hitting the 16 MB document
limit and can be versioned alongside run metadata.
"""

from __future__ import annotations

import logging

import motor.motor_asyncio
from bson import ObjectId

from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)

_BUCKET_NAME = "prompt_artifacts"


class GridFSPromptArtifactRepository:
    """MongoDB GridFS-backed PromptArtifactRepository."""

    def __init__(self) -> None:
        db = get_mongodb().database
        self._bucket = motor.motor_asyncio.AsyncIOMotorGridFSBucket(db, bucket_name=_BUCKET_NAME)

    async def save_artifact(self, run_id: str, data: bytes) -> str:
        file_id = ObjectId()
        await self._bucket.upload_from_stream_with_id(
            file_id=file_id,
            filename=f"run_{run_id}.json",
            source=data,
            metadata={"run_id": run_id},
        )
        artifact_id = str(file_id)
        logger.info("Saved optimization artifact %s for run %s (%d bytes)", artifact_id, run_id, len(data))
        return artifact_id

    async def load_artifact(self, artifact_id: str) -> bytes | None:
        try:
            stream = await self._bucket.open_download_stream(ObjectId(artifact_id))
            data = await stream.read()
            logger.debug("Loaded artifact %s (%d bytes)", artifact_id, len(data))
            return data
        except Exception:
            logger.warning("Artifact not found or unreadable: %s", artifact_id)
            return None

    async def delete_artifact(self, artifact_id: str) -> None:
        try:
            await self._bucket.delete(ObjectId(artifact_id))
            logger.info("Deleted artifact %s", artifact_id)
        except Exception:
            logger.warning("Failed to delete artifact %s", artifact_id)
