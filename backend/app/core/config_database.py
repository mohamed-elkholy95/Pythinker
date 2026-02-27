"""Database-related settings mixins.

Contains configuration for MongoDB, Redis, MinIO (object storage), and Qdrant (vector DB).
All field names map directly to environment variables via pydantic-settings.
"""


class DatabaseSettingsMixin:
    """MongoDB connection and pooling configuration."""

    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "pythinker"
    mongodb_username: str | None = None
    mongodb_password: str | None = None
    # Connection pooling and timeouts
    mongodb_max_pool_size: int = 100  # Max connections in pool
    mongodb_min_pool_size: int = 5  # Min connections to maintain
    mongodb_max_idle_time_ms: int = 300_000  # 5min idle timeout (prevents connection churn)
    mongodb_connect_timeout_ms: int = 10_000  # 10s connection timeout
    mongodb_server_selection_timeout_ms: int = 30_000  # 30s server selection timeout
    mongodb_socket_timeout_ms: int = 20_000  # 20s socket timeout
    # Automatic retry on transient errors (primary elections, network blips)
    mongodb_retry_writes: bool = True
    mongodb_retry_reads: bool = True


class RedisSettingsMixin:
    """Redis connection, pooling, and stream configuration."""

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    # Connection pooling and timeouts
    redis_max_connections: int = 50  # Max connections in pool
    redis_socket_timeout: float = 30.0  # 30s socket timeout for long-running operations like xread
    redis_socket_connect_timeout: float = 5.0  # 5s connection timeout
    redis_health_check_interval: int = 30  # 30s health check interval
    redis_retry_on_timeout: bool = True  # Retry on timeout
    # Dedicated cache Redis (split from runtime Redis for eviction isolation)
    # Disabled by default — enable when a redis-cache service is running
    redis_cache_enabled: bool = False
    redis_cache_host: str = "redis-cache"
    redis_cache_port: int = 6379
    redis_cache_db: int = 0
    redis_cache_password: str | None = None
    redis_cache_max_connections: int = 100
    redis_scan_count: int = 1000  # SCAN batch size for pattern operations (replaces KEYS)
    redis_stream_max_len: int = 10000  # Stream retention cap per stream (0 disables auto-trim)
    redis_stream_poll_block_ms: int = 1000  # Blocking read window for SSE Redis stream polling


class StorageSettingsMixin:
    """MinIO S3 object storage configuration.

    Credentials MUST be provided via environment variables (no hardcoded secrets).
    """

    minio_endpoint: str = "minio:9000"
    minio_access_key: str  # Required: set MINIO_ACCESS_KEY in .env
    minio_secret_key: str  # Required: set MINIO_SECRET_KEY in .env
    minio_bucket_name: str = "pythinker"
    minio_use_ssl: bool = False
    minio_region: str = "us-east-1"
    minio_presigned_expiry_seconds: int = 3600  # 1 hour default
    file_storage_backend: str = "minio"  # "minio" | "gridfs"
    # Snapshot bucket (uses primary minio_endpoint/credentials above)
    minio_bucket_snapshots: str = "sandbox-snapshots"
    minio_secure: bool = False  # Use HTTPS (false for local dev)
    # Screenshot-specific buckets
    minio_screenshots_bucket: str = "screenshots"
    minio_thumbnails_bucket: str = "thumbnails"


class QdrantSettingsMixin:
    """Qdrant vector database configuration with hybrid search support."""

    qdrant_url: str = "http://qdrant:6333"
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True  # 2x faster than REST
    qdrant_collection: str = "agent_memories"  # Legacy collection (deprecated, use user_knowledge)
    qdrant_api_key: str | None = None

    # Multi-collection configuration (Phase 1: Named vectors with dense + sparse hybrid search)
    qdrant_user_knowledge_collection: str = "user_knowledge"  # Primary memory collection
    qdrant_task_artifacts_collection: str = "task_artifacts"
    qdrant_tool_logs_collection: str = "tool_logs"

    # Phase 1: Hybrid search feature flags
    qdrant_use_hybrid_search: bool = True  # Enable dense+sparse hybrid retrieval (RRF fusion)
    qdrant_sparse_vector_enabled: bool = True  # Generate BM25 sparse vectors

    # Conversation context collection (real-time turn vectorization during active sessions)
    qdrant_conversation_context_collection: str = "conversation_context"
