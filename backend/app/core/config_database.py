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
    # Event store archival (Phase 1A: unbounded growth prevention)
    mongodb_event_retention_days: int = 90
    # Slow query profiler (Phase 4B)
    mongodb_profiler_enabled: bool = False
    mongodb_slow_query_threshold_ms: int = 100
    # Bounded session event array (Phase 2.3: prevents BSONDocumentTooLarge)
    mongodb_session_event_limit: int = 5000


class RedisSettingsMixin:
    """Redis connection, pooling, and stream configuration."""

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    # Connection pooling and timeouts
    redis_max_connections: int = 200  # Max connections in pool (scaled for multi-replica + SSE)
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
    redis_cache_max_connections: int = 200
    redis_scan_count: int = 1000  # SCAN batch size for pattern operations (replaces KEYS)
    redis_stream_max_len: int = 10000  # Stream retention cap per stream (0 disables auto-trim)
    redis_stream_poll_block_ms: int = 1000  # Blocking read window for SSE Redis stream polling
    # TTL applied to task I/O streams on completion (not deleted — allows SSE replay window).
    # Must be long enough for SSE reconnect; short enough to avoid unbounded memory growth.
    # Formula: >= JWT_ACCESS_TOKEN_EXPIRE_MINUTES x 60 so a valid session can always replay.
    redis_stream_ttl_seconds: int = 300  # 5 minutes — matches JWT access token window
    # TTL jitter to prevent thundering herd on mass cache expiry (Phase 2A)
    redis_cache_ttl_jitter_percent: float = 0.1  # ±10% jitter on TTL
    # Stale-while-revalidate pattern (Phase 2B)
    redis_cache_swr_enabled: bool = False


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
    # Retry with exponential backoff (Phase 3A)
    minio_retry_max_attempts: int = 3
    minio_retry_base_delay: float = 0.5
    # Multipart upload threshold (Phase 3B)
    minio_multipart_threshold_bytes: int = 52_428_800  # 50MB
    minio_multipart_part_size: int = 10_485_760  # 10MB
    # Bucket versioning (Phase 6E)
    minio_versioning_enabled: bool = False


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
    # Scalar quantization for memory-efficient vector storage (Phase 5D)
    qdrant_quantization_enabled: bool = False
    qdrant_quantization_type: str = "scalar"  # "scalar" (INT8) — ~75% memory savings
    # Conversation context age-based cleanup (Phase 6F)
    qdrant_conversation_context_max_age_days: int = 30
    # Tenant-aware HNSW: m=0 disables global links, payload_m builds per-user sub-graphs
    qdrant_hnsw_payload_m: int = 16
    qdrant_hnsw_m: int = 0
    # Query-time search beam width (higher = better recall, more latency)
    qdrant_hnsw_ef: int = 128


class SLOSettingsMixin:
    """Latency SLO thresholds for infrastructure services (Phase 4A)."""

    slo_mongodb_p95_seconds: float = 0.1
    slo_redis_p95_seconds: float = 0.01
    slo_minio_p95_seconds: float = 0.5
    slo_qdrant_p95_seconds: float = 0.2
