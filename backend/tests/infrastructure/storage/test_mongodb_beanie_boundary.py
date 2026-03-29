"""Tests for the Beanie/PyMongo boundary in MongoDB storage."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.storage.mongodb import MongoDB, initialize_beanie


@pytest.mark.asyncio
async def test_initialize_beanie_uses_pymongo_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Beanie should initialize against the dedicated PyMongo async database."""
    beanie_database = object()
    init_beanie_mock = AsyncMock()
    fake_mongodb = SimpleNamespace(beanie_database=beanie_database)

    monkeypatch.setattr("app.infrastructure.storage.mongodb.get_mongodb", lambda: fake_mongodb)
    monkeypatch.setattr("app.infrastructure.storage.mongodb._init_beanie", init_beanie_mock)

    await initialize_beanie(document_models=["app.models.SampleDocument"])

    init_beanie_mock.assert_awaited_once_with(
        database=beanie_database,
        document_models=["app.models.SampleDocument"],
    )


def test_beanie_database_uses_dedicated_async_pymongo_client() -> None:
    """The Beanie database handle should come from the PyMongo async client."""
    mongodb = MongoDB()
    motor_database = object()
    beanie_database = object()
    motor_client = MagicMock()
    pymongo_client = MagicMock()
    motor_client.__getitem__.return_value = motor_database
    pymongo_client.__getitem__.return_value = beanie_database

    mongodb._client = motor_client
    mongodb._beanie_client = pymongo_client
    mongodb._refresh_clients_for_current_loop = MagicMock()

    assert mongodb.database is motor_database
    assert mongodb.beanie_database is beanie_database
    mongodb._refresh_clients_for_current_loop.assert_called()


@pytest.mark.asyncio
async def test_shutdown_closes_motor_and_pymongo_clients() -> None:
    """Shutdown should close both MongoDB client implementations."""
    mongodb = MongoDB()
    motor_client = MagicMock()
    pymongo_client = MagicMock()
    mongodb._client = motor_client
    mongodb._beanie_client = pymongo_client

    await mongodb.shutdown()

    motor_client.close.assert_called_once()
    pymongo_client.close.assert_called_once()
