"""Tests for database-related settings mixins.

Validates default values, type constraints, and logical relationships
for MongoDB, Redis, MinIO, Qdrant, and SLO configuration.
"""

from app.core.config_database import (
    DatabaseSettingsMixin,
    QdrantSettingsMixin,
    RedisSettingsMixin,
    SLOSettingsMixin,
    StorageSettingsMixin,
)

# ─── DatabaseSettingsMixin ───


class TestDatabaseSettingsMixin:
    def test_default_pool_size(self) -> None:
        assert DatabaseSettingsMixin.mongodb_max_pool_size == 20
        assert DatabaseSettingsMixin.mongodb_min_pool_size == 1

    def test_min_pool_lte_max_pool(self) -> None:
        assert DatabaseSettingsMixin.mongodb_min_pool_size <= DatabaseSettingsMixin.mongodb_max_pool_size

    def test_default_timeouts_are_positive(self) -> None:
        assert DatabaseSettingsMixin.mongodb_connect_timeout_ms > 0
        assert DatabaseSettingsMixin.mongodb_server_selection_timeout_ms > 0
        assert DatabaseSettingsMixin.mongodb_socket_timeout_ms > 0
        assert DatabaseSettingsMixin.mongodb_max_idle_time_ms > 0

    def test_connect_timeout_less_than_server_selection(self) -> None:
        """Connect timeout should be shorter than server selection timeout."""
        assert DatabaseSettingsMixin.mongodb_connect_timeout_ms < DatabaseSettingsMixin.mongodb_server_selection_timeout_ms

    def test_retry_enabled_by_default(self) -> None:
        assert DatabaseSettingsMixin.mongodb_retry_writes is True
        assert DatabaseSettingsMixin.mongodb_retry_reads is True

    def test_event_retention_reasonable(self) -> None:
        assert DatabaseSettingsMixin.mongodb_event_retention_days == 90
        assert DatabaseSettingsMixin.mongodb_event_retention_days > 0

    def test_session_event_limit_prevents_bson_overflow(self) -> None:
        assert DatabaseSettingsMixin.mongodb_session_event_limit == 5000
        assert DatabaseSettingsMixin.mongodb_session_event_limit > 0

    def test_profiler_disabled_by_default(self) -> None:
        assert DatabaseSettingsMixin.mongodb_profiler_enabled is False
        assert DatabaseSettingsMixin.mongodb_slow_query_threshold_ms == 100

    def test_write_coalescer_delay_reasonable(self) -> None:
        assert DatabaseSettingsMixin.write_coalescer_delay_ms == 100
        assert DatabaseSettingsMixin.write_coalescer_delay_ms > 0

    def test_default_database_name(self) -> None:
        assert DatabaseSettingsMixin.mongodb_database == "pythinker"


# ─── RedisSettingsMixin ───


class TestRedisSettingsMixin:
    def test_default_connection_pool(self) -> None:
        assert RedisSettingsMixin.redis_max_connections == 50
        assert RedisSettingsMixin.redis_max_connections > 0

    def test_socket_timeouts_positive(self) -> None:
        assert RedisSettingsMixin.redis_socket_timeout > 0
        assert RedisSettingsMixin.redis_socket_connect_timeout > 0

    def test_connect_timeout_less_than_socket_timeout(self) -> None:
        """Connect timeout should be shorter than socket timeout for xread."""
        assert RedisSettingsMixin.redis_socket_connect_timeout < RedisSettingsMixin.redis_socket_timeout

    def test_retry_on_timeout_enabled(self) -> None:
        assert RedisSettingsMixin.redis_retry_on_timeout is True

    def test_stream_retention_cap(self) -> None:
        assert RedisSettingsMixin.redis_stream_max_len == 10000
        assert RedisSettingsMixin.redis_stream_max_len > 0

    def test_stream_ttl_matches_jwt_window(self) -> None:
        assert RedisSettingsMixin.redis_stream_ttl_seconds == 300

    def test_cache_disabled_by_default(self) -> None:
        assert RedisSettingsMixin.redis_cache_enabled is False

    def test_cache_jitter_is_percentage(self) -> None:
        assert 0 < RedisSettingsMixin.redis_cache_ttl_jitter_percent <= 1.0

    def test_swr_disabled_by_default(self) -> None:
        assert RedisSettingsMixin.redis_cache_swr_enabled is False

    def test_scan_count_reasonable(self) -> None:
        assert RedisSettingsMixin.redis_scan_count == 1000
        assert RedisSettingsMixin.redis_scan_count > 0

    def test_session_cache_ttl(self) -> None:
        assert RedisSettingsMixin.session_cache_ttl_seconds == 900


# ─── StorageSettingsMixin ───


class TestStorageSettingsMixin:
    def test_default_bucket_name(self) -> None:
        assert StorageSettingsMixin.minio_bucket_name == "pythinker"

    def test_presigned_url_expiry(self) -> None:
        assert StorageSettingsMixin.minio_presigned_expiry_seconds == 3600

    def test_multipart_threshold(self) -> None:
        assert StorageSettingsMixin.minio_multipart_threshold_bytes == 52_428_800  # 50MB

    def test_multipart_part_size(self) -> None:
        assert StorageSettingsMixin.minio_multipart_part_size == 10_485_760  # 10MB

    def test_part_size_less_than_threshold(self) -> None:
        assert StorageSettingsMixin.minio_multipart_part_size < StorageSettingsMixin.minio_multipart_threshold_bytes

    def test_retry_settings(self) -> None:
        assert StorageSettingsMixin.minio_retry_max_attempts == 3
        assert StorageSettingsMixin.minio_retry_base_delay == 0.5

    def test_ssl_disabled_for_dev(self) -> None:
        assert StorageSettingsMixin.minio_use_ssl is False
        assert StorageSettingsMixin.minio_secure is False

    def test_versioning_disabled_by_default(self) -> None:
        assert StorageSettingsMixin.minio_versioning_enabled is False

    def test_file_storage_backend_default(self) -> None:
        assert StorageSettingsMixin.file_storage_backend == "minio"


# ─── QdrantSettingsMixin ───


class TestQdrantSettingsMixin:
    def test_grpc_preferred(self) -> None:
        assert QdrantSettingsMixin.qdrant_prefer_grpc is True

    def test_hybrid_search_enabled_by_default(self) -> None:
        assert QdrantSettingsMixin.qdrant_use_hybrid_search is True
        assert QdrantSettingsMixin.qdrant_sparse_vector_enabled is True

    def test_primary_collection_is_user_knowledge(self) -> None:
        assert QdrantSettingsMixin.qdrant_user_knowledge_collection == "user_knowledge"

    def test_legacy_collection_still_defined(self) -> None:
        assert QdrantSettingsMixin.qdrant_collection == "agent_memories"

    def test_quantization_disabled_by_default(self) -> None:
        assert QdrantSettingsMixin.qdrant_quantization_enabled is False
        assert QdrantSettingsMixin.qdrant_quantization_type == "scalar"

    def test_hnsw_tenant_aware_config(self) -> None:
        """m=0 disables global links, payload_m=16 builds per-user sub-graphs."""
        assert QdrantSettingsMixin.qdrant_hnsw_m == 0
        assert QdrantSettingsMixin.qdrant_hnsw_payload_m == 16
        assert QdrantSettingsMixin.qdrant_hnsw_ef == 128

    def test_conversation_context_cleanup(self) -> None:
        assert QdrantSettingsMixin.qdrant_conversation_context_max_age_days == 30


# ─── SLOSettingsMixin ───


class TestSLOSettingsMixin:
    def test_all_thresholds_positive(self) -> None:
        assert SLOSettingsMixin.slo_mongodb_p95_seconds > 0
        assert SLOSettingsMixin.slo_redis_p95_seconds > 0
        assert SLOSettingsMixin.slo_minio_p95_seconds > 0
        assert SLOSettingsMixin.slo_qdrant_p95_seconds > 0

    def test_redis_fastest_slo(self) -> None:
        """Redis should have the tightest latency SLO."""
        assert SLOSettingsMixin.slo_redis_p95_seconds < SLOSettingsMixin.slo_mongodb_p95_seconds
        assert SLOSettingsMixin.slo_redis_p95_seconds < SLOSettingsMixin.slo_qdrant_p95_seconds

    def test_slo_values(self) -> None:
        assert SLOSettingsMixin.slo_mongodb_p95_seconds == 0.1
        assert SLOSettingsMixin.slo_redis_p95_seconds == 0.01
        assert SLOSettingsMixin.slo_minio_p95_seconds == 0.5
        assert SLOSettingsMixin.slo_qdrant_p95_seconds == 0.2
