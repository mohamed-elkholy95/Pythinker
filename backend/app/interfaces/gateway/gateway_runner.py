"""Gateway runner — standalone entry point for the multi-channel gateway.

Starts the channel gateway as an independent process that:
1. Validates ``CHANNEL_GATEWAY_ENABLED`` is true.
2. Initialises a MongoDB connection (same URI as the main backend).
3. Wires the dependency chain:
   ``MongoUserChannelRepository → MessageRouter → NanobotGateway``
4. Starts the gateway and waits for a shutdown signal (SIGINT / SIGTERM).

Usage::

    python -m app.interfaces.gateway.gateway_runner

Environment:
    All settings are read via ``app.core.config.get_settings()``, which loads
    from ``.env`` and environment variables as usual.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.core.config import get_settings
from app.infrastructure.storage.minio_storage import get_minio_storage
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


async def run_gateway() -> None:
    """Initialise and run the channel gateway until a shutdown signal is received."""
    settings = get_settings()

    if not settings.channel_gateway_enabled:
        logger.error("Channel gateway is disabled. Set CHANNEL_GATEWAY_ENABLED=true to start it.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Initialise MongoDB + Beanie ODM
    # ------------------------------------------------------------------
    mongodb = get_mongodb()
    await mongodb.initialize()
    db = mongodb.database
    logger.info("MongoDB connection established for gateway")

    # Beanie must be initialised before any Document class-level field
    # access (e.g. AgentDocument.agent_id).  The main backend does this
    # inside lifespan.py; the gateway runs outside FastAPI so we repeat
    # it here with the same model list.
    from beanie import init_beanie

    from app.core.lifespan import BEANIE_DOCUMENT_MODELS

    await init_beanie(
        database=mongodb.client[settings.mongodb_database],
        document_models=BEANIE_DOCUMENT_MODELS,
    )
    logger.info("Beanie ODM initialised for gateway")

    # ------------------------------------------------------------------
    # 1b. Initialise Qdrant (optional — graceful degradation)
    # ------------------------------------------------------------------
    try:
        from app.infrastructure.storage.qdrant import get_qdrant

        await get_qdrant().initialize()
        logger.info("Qdrant connection established for gateway")

        # Wire vector memory repositories (same as lifespan.py)
        from app.domain.repositories.vector_memory_repository import set_vector_memory_repository
        from app.infrastructure.repositories.qdrant_memory_repository import QdrantMemoryRepository

        set_vector_memory_repository(QdrantMemoryRepository())

        from app.domain.repositories.vector_repos import (
            set_embedding_provider,
            set_task_artifact_repository,
            set_tool_log_repository,
        )
        from app.infrastructure.external.embedding.client import get_embedding_client
        from app.infrastructure.repositories.qdrant_task_repository import QdrantTaskRepository
        from app.infrastructure.repositories.qdrant_tool_log_repository import QdrantToolLogRepository

        set_task_artifact_repository(QdrantTaskRepository())
        set_tool_log_repository(QdrantToolLogRepository())
        try:
            set_embedding_provider(get_embedding_client())
        except RuntimeError:
            logger.warning("No embedding API key — embedding provider not set")
    except Exception as e:
        logger.warning("Qdrant init failed (graceful degradation): %s", e)

    # ------------------------------------------------------------------
    # 1c. Initialise MinIO storage for file/screenshot persistence
    # ------------------------------------------------------------------
    try:
        await get_minio_storage().initialize()
        logger.info("MinIO connection established for gateway")
    except Exception as e:
        logger.warning("MinIO init failed for gateway (degraded file persistence): %s", e)

    # ------------------------------------------------------------------
    # 1d. Initialise BM25 encoder from stored memories (hybrid search)
    # Without this the gateway falls back to dense-only retrieval on every
    # memory lookup, losing the keyword-recall benefit of hybrid RRF search.
    # ------------------------------------------------------------------
    try:
        from app.domain.services.embeddings.bm25_encoder import initialize_bm25_from_memories
        from app.infrastructure.repositories.mongo_memory_repository import MongoMemoryRepository

        memory_repo = MongoMemoryRepository(database=db)
        logger.info("Initializing BM25 encoder from stored memories...")
        await initialize_bm25_from_memories(memory_repo)
    except Exception as e:
        logger.warning("BM25 encoder initialization failed (non-critical): %s", e)

    # ------------------------------------------------------------------
    # 2. Build dependency chain
    # ------------------------------------------------------------------
    from app.infrastructure.repositories.user_channel_repository import (
        MongoUserChannelRepository,
    )

    user_channel_repo = MongoUserChannelRepository(db)
    await user_channel_repo.ensure_indexes()

    # AgentService — required by MessageRouter for session management.
    # Uses the same singleton factory as the main backend.
    from app.interfaces.dependencies import get_agent_service
    from app.interfaces.gateway.pdf_renderer_factory import build_configured_pdf_renderer

    agent_service = get_agent_service()

    from app.domain.services.channels.message_router import MessageRouter
    from app.domain.services.channels.telegram_delivery_policy import TelegramDeliveryPolicy

    # LinkCodeStore adapter — wraps Redis for the /link command.
    # Uses the existing get_redis() singleton.
    from app.infrastructure.storage.redis import get_redis

    class _RedisLinkCodeStore:
        """Thin adapter exposing get/delete for the link-code Redis keys."""

        async def get(self, key: str) -> str | None:
            return await get_redis().call("get", key)

        async def delete(self, key: str) -> None:
            await get_redis().call("delete", key)

    pdf_renderer = build_configured_pdf_renderer(settings=settings)

    telegram_delivery_policy = TelegramDeliveryPolicy(
        pdf_delivery_enabled=settings.telegram_pdf_delivery_enabled,
        message_min_chars=settings.telegram_pdf_message_min_chars,
        report_min_chars=settings.telegram_pdf_report_min_chars,
        caption_max_chars=settings.telegram_pdf_caption_max_chars,
        pdf_caption_enabled=settings.telegram_pdf_caption_enabled,
        pdf_progress_ack_enabled=settings.telegram_pdf_progress_ack_enabled,
        async_threshold_chars=settings.telegram_pdf_async_threshold_chars,
        include_toc=settings.telegram_pdf_include_toc,
        toc_min_sections=settings.telegram_pdf_toc_min_sections,
        unicode_font=settings.telegram_pdf_unicode_font,
        rate_limit_per_minute=settings.telegram_pdf_rate_limit_per_minute,
        force_long_text_pdf=settings.telegram_pdf_force_long_text,
        pdf_renderer=pdf_renderer,
    )

    message_router = MessageRouter(
        agent_service=agent_service,
        user_channel_repo=user_channel_repo,
        link_code_store=_RedisLinkCodeStore(),
        telegram_delivery_policy=telegram_delivery_policy,
        telegram_reuse_completed_sessions=settings.telegram_reuse_completed_sessions,
        telegram_session_idle_timeout_hours=settings.telegram_session_idle_timeout_hours,
        telegram_max_context_turns=settings.telegram_max_context_turns,
        telegram_context_summarization_enabled=settings.telegram_context_summarization_enabled,
        telegram_context_summarization_threshold_turns=settings.telegram_context_summarization_threshold_turns,
        telegram_pdf_delivery_enabled=settings.telegram_pdf_delivery_enabled,
        telegram_pdf_message_min_chars=settings.telegram_pdf_message_min_chars,
        telegram_pdf_report_min_chars=settings.telegram_pdf_report_min_chars,
        telegram_pdf_caption_max_chars=settings.telegram_pdf_caption_max_chars,
        telegram_pdf_caption_enabled=settings.telegram_pdf_caption_enabled,
        telegram_pdf_progress_ack_enabled=settings.telegram_pdf_progress_ack_enabled,
        telegram_pdf_async_threshold_chars=settings.telegram_pdf_async_threshold_chars,
        telegram_pdf_include_toc=settings.telegram_pdf_include_toc,
        telegram_pdf_toc_min_sections=settings.telegram_pdf_toc_min_sections,
        telegram_pdf_unicode_font=settings.telegram_pdf_unicode_font,
        telegram_pdf_rate_limit_per_minute=settings.telegram_pdf_rate_limit_per_minute,
        telegram_pdf_force_long_text=settings.telegram_pdf_force_long_text,
        telegram_require_linked_account=settings.telegram_require_linked_account,
        telegram_final_delivery_only=settings.telegram_final_delivery_only,
        telegram_final_delivery_allow_wait_prompts=settings.telegram_final_delivery_allow_wait_prompts,
    )

    # NanobotGateway — may not exist yet during incremental development.
    try:
        from app.infrastructure.external.channels.nanobot_gateway import (
            NanobotGateway,
        )
    except ImportError:
        logger.error(
            "NanobotGateway not available. Ensure app.infrastructure.external.channels.nanobot_gateway is implemented."
        )
        sys.exit(1)

    gateway = NanobotGateway(
        message_router,
        telegram_token=settings.telegram_bot_token,
        telegram_allowed=settings.telegram_allowed_users or None,
        telegram_rate_limit_cooldown_seconds=settings.telegram_rate_limit_cooldown_seconds,
        telegram_max_messages_per_batch=settings.telegram_max_messages_per_batch,
        telegram_pdf_file_id_cache_redis_enabled=settings.telegram_pdf_file_id_cache_redis_enabled,
        telegram_final_delivery_only=settings.telegram_final_delivery_only,
        telegram_final_delivery_allow_wait_prompts=settings.telegram_final_delivery_allow_wait_prompts,
        telegram_polling_bootstrap_retries=settings.telegram_polling_bootstrap_retries,
        telegram_polling_stall_restart_enabled=settings.telegram_polling_stall_restart_enabled,
        telegram_polling_stall_timeout_seconds=settings.telegram_polling_stall_timeout_seconds,
        telegram_send_retry_max_attempts=settings.telegram_send_retry_max_attempts,
        telegram_send_retry_base_delay_seconds=settings.telegram_send_retry_base_delay_seconds,
        telegram_send_retry_max_delay_seconds=settings.telegram_send_retry_max_delay_seconds,
        telegram_send_retry_jitter=settings.telegram_send_retry_jitter,
        telegram_send_circuit_breaker_enabled=settings.telegram_send_circuit_breaker_enabled,
        telegram_send_circuit_failure_threshold=settings.telegram_send_circuit_failure_threshold,
        telegram_send_circuit_recovery_timeout_seconds=settings.telegram_send_circuit_recovery_timeout_seconds,
        discord_token=settings.discord_bot_token,
        discord_allowed=settings.discord_allowed_users or None,
        slack_bot_token=settings.slack_bot_token,
        slack_app_token=settings.slack_app_token,
        slack_allowed=settings.slack_allowed_users or None,
    )

    # ------------------------------------------------------------------
    # 3. Start gateway
    # ------------------------------------------------------------------
    await gateway.start()
    logger.info("Channel gateway started — waiting for shutdown signal")

    # ------------------------------------------------------------------
    # 4. Wait for shutdown signal (SIGINT / SIGTERM)
    # ------------------------------------------------------------------
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    await shutdown_event.wait()

    # ------------------------------------------------------------------
    # 5. Graceful shutdown
    # ------------------------------------------------------------------
    logger.info("Shutdown signal received — stopping gateway")
    await gateway.stop()
    try:
        await get_minio_storage().shutdown()
    except Exception as e:
        logger.warning("MinIO shutdown failed for gateway: %s", e)
    await mongodb.shutdown()
    logger.info("Gateway shutdown complete")


def main() -> None:
    """CLI entry point."""
    # Use the same structured logging as the main backend.
    # This enables: httpx suppression (WARNING), sensitive-data redaction,
    # correlation IDs, and QueueHandler for high-throughput safety.
    from app.infrastructure.structured_logging import setup_structured_logging

    setup_structured_logging()
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()
