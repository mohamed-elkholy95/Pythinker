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

    agent_service = get_agent_service()

    from app.domain.services.channels.message_router import MessageRouter

    message_router = MessageRouter(
        agent_service=agent_service,
        user_channel_repo=user_channel_repo,
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
    await mongodb.shutdown()
    logger.info("Gateway shutdown complete")


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_gateway())


if __name__ == "__main__":
    main()
