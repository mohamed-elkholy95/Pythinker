"""Application-layer factory for ConversationContextService.

Wires infrastructure implementations (Qdrant repository, embedding client)
into the domain service. Keeps infrastructure imports out of the domain layer.
"""

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.domain.services.conversation_context_service import ConversationContextService

logger = logging.getLogger(__name__)


@lru_cache
def get_conversation_context_service() -> ConversationContextService | None:
    """Get singleton ConversationContextService, or None if disabled.

    Returns None if feature_conversation_context_enabled is False or if
    required infrastructure (embedding client, Qdrant) is unavailable.
    """
    settings = get_settings()
    if not settings.feature_conversation_context_enabled:
        return None

    try:
        from app.infrastructure.external.embedding.client import get_embedding_client
        from app.infrastructure.repositories.conversation_context_repository import (
            ConversationContextRepository as QdrantConversationContextRepository,
        )

        repository = QdrantConversationContextRepository()
        embedding_client = get_embedding_client()
        return ConversationContextService(
            repository=repository,
            embedding_client=embedding_client,
        )
    except (RuntimeError, Exception):
        logger.warning(
            "ConversationContextService unavailable: embedding client or repository "
            "could not be initialized. Conversation context features will be disabled.",
        )
        return None
