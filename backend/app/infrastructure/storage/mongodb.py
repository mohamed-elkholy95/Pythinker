from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from pymongo.errors import ConnectionFailure
from bson import ObjectId
from typing import Optional
import logging
from app.core.config import get_settings
from functools import lru_cache

logger = logging.getLogger(__name__)

class MongoDB:
    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self._settings = get_settings()
        self._screenshot_bucket: Optional[AsyncIOMotorGridFSBucket] = None
        self._artifacts_bucket: Optional[AsyncIOMotorGridFSBucket] = None
    
    async def initialize(self) -> None:
        """Initialize MongoDB connection and Beanie ODM."""
        if self._client is not None:
            return
            
        try:
            # Connect to MongoDB with connection pooling and timeout settings
            connection_params = {
                "maxPoolSize": self._settings.mongodb_max_pool_size,
                "minPoolSize": self._settings.mongodb_min_pool_size,
                "maxIdleTimeMS": self._settings.mongodb_max_idle_time_ms,
                "connectTimeoutMS": self._settings.mongodb_connect_timeout_ms,
                "serverSelectionTimeoutMS": self._settings.mongodb_server_selection_timeout_ms,
                "socketTimeoutMS": self._settings.mongodb_socket_timeout_ms,
            }

            if self._settings.mongodb_username and self._settings.mongodb_password:
                # Use authenticated connection if username and password are configured
                self._client = AsyncIOMotorClient(
                    self._settings.mongodb_uri,
                    username=self._settings.mongodb_username,
                    password=self._settings.mongodb_password,
                    **connection_params,
                )
            else:
                # Use unauthenticated connection if no credentials are provided
                self._client = AsyncIOMotorClient(
                    self._settings.mongodb_uri,
                    **connection_params,
                )
            # Verify the connection
            await self._client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")

            # Initialize GridFS buckets for screenshot and artifact storage (Phase 2)
            db = self._client[self._settings.mongodb_database]
            self._screenshot_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="screenshots")
            self._artifacts_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="artifacts")
            logger.info("Initialized GridFS buckets for screenshots and artifacts")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Beanie: {str(e)}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("Disconnected from MongoDB")
                # Clear cache for this module
        get_mongodb.cache_clear()
    
    @property
    def client(self) -> AsyncIOMotorClient:
        """Return initialized MongoDB client"""
        if self._client is None:
            raise RuntimeError("MongoDB client not initialized. Call initialize() first.")
        return self._client

    @property
    def screenshot_bucket(self) -> AsyncIOMotorGridFSBucket:
        """Return GridFS bucket for screenshots"""
        if self._screenshot_bucket is None:
            raise RuntimeError("MongoDB not initialized. Call initialize() first.")
        return self._screenshot_bucket

    @property
    def artifacts_bucket(self) -> AsyncIOMotorGridFSBucket:
        """Return GridFS bucket for artifacts"""
        if self._artifacts_bucket is None:
            raise RuntimeError("MongoDB not initialized. Call initialize() first.")
        return self._artifacts_bucket

    async def store_screenshot(
        self,
        image_data: bytes,
        filename: str,
        metadata: dict,
    ) -> str:
        """Store screenshot in GridFS and return file ID"""
        file_id = await self.screenshot_bucket.upload_from_stream(
            filename,
            image_data,
            metadata=metadata
        )
        logger.debug(f"Stored screenshot: {filename} (ID: {file_id})")
        return str(file_id)

    async def get_screenshot(self, file_id: str) -> bytes:
        """Retrieve screenshot from GridFS"""
        grid_out = await self.screenshot_bucket.open_download_stream(
            ObjectId(file_id)
        )
        image_data = await grid_out.read()
        logger.debug(f"Retrieved screenshot: {file_id}")
        return image_data

    async def store_artifact(
        self,
        file_data: bytes,
        filename: str,
        metadata: dict,
    ) -> str:
        """Store artifact in GridFS and return file ID"""
        file_id = await self.artifacts_bucket.upload_from_stream(
            filename,
            file_data,
            metadata=metadata
        )
        logger.debug(f"Stored artifact: {filename} (ID: {file_id})")
        return str(file_id)

    async def get_artifact(self, file_id: str) -> bytes:
        """Retrieve artifact from GridFS"""
        grid_out = await self.artifacts_bucket.open_download_stream(
            ObjectId(file_id)
        )
        file_data = await grid_out.read()
        logger.debug(f"Retrieved artifact: {file_id}")
        return file_data


@lru_cache()
def get_mongodb() -> MongoDB:
    """Get the MongoDB instance."""
    return MongoDB()

