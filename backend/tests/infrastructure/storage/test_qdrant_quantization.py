"""Tests for Qdrant scalar quantization config (Phase 5D)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client import models


class TestQdrantQuantization:
    """Tests for quantization configuration in collection creation."""

    @pytest.mark.asyncio
    async def test_quantization_enabled_adds_scalar_config(self):
        """When quantization is enabled, ScalarQuantization is passed to create_collection."""
        mock_settings = MagicMock()
        mock_settings.qdrant_quantization_enabled = True
        mock_settings.qdrant_quantization_type = "scalar"
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.qdrant_grpc_port = 6334
        mock_settings.qdrant_prefer_grpc = False
        mock_settings.qdrant_api_key = None
        mock_settings.qdrant_user_knowledge_collection = "user_knowledge"

        from app.infrastructure.storage.qdrant import QdrantStorage

        storage = QdrantStorage.__new__(QdrantStorage)
        storage._settings = mock_settings
        storage._client = AsyncMock()
        storage._client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
        storage._client.create_collection = AsyncMock()
        storage._client.create_payload_index = AsyncMock()

        await storage._ensure_collections()

        # Check that create_collection was called with quantization_config
        for call in storage._client.create_collection.call_args_list:
            kwargs = call.kwargs or {}
            # Also check positional keyword args
            if not kwargs:
                # Might be passed as keyword args in the call
                kwargs = dict(
                    zip(
                        [
                            "collection_name",
                            "vectors_config",
                            "sparse_vectors_config",
                            "optimizers_config",
                            "quantization_config",
                            "on_disk_payload",
                        ],
                        call.args or [],
                        strict=False,
                    )
                )

            quant = kwargs.get("quantization_config") or (
                call.kwargs.get("quantization_config") if call.kwargs else None
            )
            if quant is not None:
                assert isinstance(quant, models.ScalarQuantization)

    @pytest.mark.asyncio
    async def test_quantization_disabled_passes_none(self):
        """When quantization is disabled, quantization_config is None."""
        mock_settings = MagicMock()
        mock_settings.qdrant_quantization_enabled = False
        mock_settings.qdrant_quantization_type = "scalar"

        from app.infrastructure.storage.qdrant import QdrantStorage

        storage = QdrantStorage.__new__(QdrantStorage)
        storage._settings = mock_settings
        storage._client = AsyncMock()
        storage._client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
        storage._client.create_collection = AsyncMock()
        storage._client.create_payload_index = AsyncMock()

        await storage._ensure_collections()

        for call in storage._client.create_collection.call_args_list:
            kwargs = call.kwargs or {}
            quant = kwargs.get("quantization_config")
            assert quant is None
