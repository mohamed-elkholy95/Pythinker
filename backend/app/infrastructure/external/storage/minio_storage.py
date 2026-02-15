"""
MinIO Object Storage Adapter - S3-compatible storage for snapshots.

Implements ObjectStorage protocol for SnapshotManager.
"""

import logging

logger = logging.getLogger(__name__)


class MinIOStorage:
    """
    MinIO storage adapter for sandbox snapshots.

    Uses MinIO's S3-compatible API for object storage.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "sandbox-snapshots",
        secure: bool = False,
    ):
        """
        Initialize MinIO storage.

        Args:
            endpoint: MinIO endpoint (e.g., "localhost:9000")
            access_key: Access key ID
            secret_key: Secret access key
            bucket_name: Bucket name for snapshots
            secure: Use HTTPS (default: False for local dev)
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.secure = secure
        self.client = None

        # Lazy import to avoid dependency errors if MinIO not installed
        try:
            from minio import Minio

            self.client = Minio(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )

            # Ensure bucket exists
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created MinIO bucket: {bucket_name}")

        except ImportError:
            logger.warning("minio package not installed, snapshot storage unavailable")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}", exc_info=True)

    async def upload(self, key: str, data: bytes, metadata: dict[str, str] | None = None) -> None:
        """
        Upload object to MinIO.

        Args:
            key: Object key (path)
            data: Object data
            metadata: Optional metadata dict
        """
        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        try:
            from io import BytesIO

            data_stream = BytesIO(data)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=key,
                data=data_stream,
                length=len(data),
                metadata=metadata or {},
            )

            logger.debug(f"Uploaded {len(data) / 1024 / 1024:.1f}MB to {key}")

        except Exception as e:
            logger.error(f"Failed to upload {key}: {e}", exc_info=True)
            raise

    async def download(self, key: str) -> bytes:
        """
        Download object from MinIO.

        Args:
            key: Object key (path)

        Returns:
            Object data
        """
        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        try:
            response = self.client.get_object(self.bucket_name, key)
            data = response.read()
            response.close()
            response.release_conn()

            logger.debug(f"Downloaded {len(data) / 1024 / 1024:.1f}MB from {key}")
            return data

        except Exception as e:
            logger.error(f"Failed to download {key}: {e}", exc_info=True)
            raise

    async def delete(self, key: str) -> None:
        """
        Delete object from MinIO.

        Args:
            key: Object key (path)
        """
        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        try:
            self.client.remove_object(self.bucket_name, key)
            logger.debug(f"Deleted {key}")

        except Exception as e:
            logger.error(f"Failed to delete {key}: {e}", exc_info=True)
            raise

    async def exists(self, key: str) -> bool:
        """
        Check if object exists in MinIO.

        Args:
            key: Object key (path)

        Returns:
            True if object exists, False otherwise
        """
        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        try:
            self.client.stat_object(self.bucket_name, key)
            return True
        except Exception:
            return False

    def list_objects(self, prefix: str = "") -> list[str]:
        """
        List objects with prefix.

        Args:
            prefix: Object key prefix

        Returns:
            List of object keys
        """
        if not self.client:
            raise RuntimeError("MinIO client not initialized")

        try:
            objects = self.client.list_objects(self.bucket_name, prefix=prefix)
            return [obj.object_name for obj in objects]

        except Exception as e:
            logger.error(f"Failed to list objects with prefix {prefix}: {e}")
            return []
