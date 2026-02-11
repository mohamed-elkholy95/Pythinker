"""Tests for task/tool Qdrant repositories vector schema handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client import models

from app.infrastructure.repositories.qdrant_task_repository import QdrantTaskRepository
from app.infrastructure.repositories.qdrant_tool_log_repository import QdrantToolLogRepository


def _named_collection_info() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors={"dense": models.VectorParams(size=1536, distance=models.Distance.COSINE)})
        )
    )


def _unnamed_collection_info() -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=models.VectorParams(size=1536, distance=models.Distance.COSINE))
        )
    )


@pytest.mark.asyncio
@patch("app.infrastructure.repositories.qdrant_task_repository.get_qdrant")
@patch("app.infrastructure.repositories.qdrant_task_repository.get_settings")
async def test_task_repo_uses_named_dense_vector_for_named_collection(mock_settings, mock_qdrant):
    mock_settings.return_value = MagicMock(qdrant_task_artifacts_collection="task_artifacts")
    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.get_collection = AsyncMock(return_value=_named_collection_info())
    mock_storage.client.upsert = AsyncMock()
    mock_qdrant.return_value = mock_storage

    repo = QdrantTaskRepository()
    embedding = [0.1] * 1536

    await repo.store_task_artifact(
        artifact_id="a1",
        user_id="u1",
        session_id="s1",
        embedding=embedding,
        artifact_type="task_outcome",
    )

    call_kwargs = mock_storage.client.upsert.call_args.kwargs
    point = call_kwargs["points"][0]
    assert point.vector == {"dense": embedding}


@pytest.mark.asyncio
@patch("app.infrastructure.repositories.qdrant_task_repository.get_qdrant")
@patch("app.infrastructure.repositories.qdrant_task_repository.get_settings")
async def test_task_repo_query_retries_with_unnamed_vector_on_mode_mismatch(mock_settings, mock_qdrant):
    mock_settings.return_value = MagicMock(qdrant_task_artifacts_collection="task_artifacts")
    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.get_collection = AsyncMock(return_value=_named_collection_info())
    mock_response = MagicMock()
    mock_response.points = []
    mock_storage.client.query_points = AsyncMock(
        side_effect=[RuntimeError("vector with name `dense` does not exist"), mock_response]
    )
    mock_qdrant.return_value = mock_storage

    repo = QdrantTaskRepository()
    await repo.find_similar_tasks(user_id="u1", query_vector=[0.1] * 1536)

    first_call = mock_storage.client.query_points.call_args_list[0].kwargs
    second_call = mock_storage.client.query_points.call_args_list[1].kwargs
    assert first_call["using"] == "dense"
    assert "using" not in second_call


@pytest.mark.asyncio
@patch("app.infrastructure.repositories.qdrant_tool_log_repository.get_qdrant")
@patch("app.infrastructure.repositories.qdrant_tool_log_repository.get_settings")
async def test_tool_log_repo_uses_named_dense_vector_for_named_collection(mock_settings, mock_qdrant):
    mock_settings.return_value = MagicMock(qdrant_tool_logs_collection="tool_logs")
    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.get_collection = AsyncMock(return_value=_named_collection_info())
    mock_storage.client.upsert = AsyncMock()
    mock_qdrant.return_value = mock_storage

    repo = QdrantToolLogRepository()
    embedding = [0.2] * 1536

    await repo.log_tool_execution(
        log_id="l1",
        user_id="u1",
        session_id="s1",
        tool_name="shell",
        embedding=embedding,
        outcome="success",
    )

    call_kwargs = mock_storage.client.upsert.call_args.kwargs
    point = call_kwargs["points"][0]
    assert point.vector == {"dense": embedding}


@pytest.mark.asyncio
@patch("app.infrastructure.repositories.qdrant_tool_log_repository.get_qdrant")
@patch("app.infrastructure.repositories.qdrant_tool_log_repository.get_settings")
async def test_tool_log_repo_uses_unnamed_vectors_when_collection_schema_is_unnamed(mock_settings, mock_qdrant):
    mock_settings.return_value = MagicMock(qdrant_tool_logs_collection="tool_logs")
    mock_storage = MagicMock()
    mock_storage.client = MagicMock()
    mock_storage.client.get_collection = AsyncMock(return_value=_unnamed_collection_info())
    mock_response = MagicMock()
    mock_response.points = []
    mock_storage.client.query_points = AsyncMock(return_value=mock_response)
    mock_qdrant.return_value = mock_storage

    repo = QdrantToolLogRepository()
    await repo.find_similar_tool_executions(user_id="u1", query_vector=[0.2] * 1536)

    call_kwargs = mock_storage.client.query_points.call_args.kwargs
    assert "using" not in call_kwargs
