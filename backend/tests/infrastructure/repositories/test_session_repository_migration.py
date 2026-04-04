"""Tests for repository-level session schema migration.

Phase 4 requires that session migration is applied in the infrastructure
deserialization path (MongoSessionRepository and CachedSessionRepository)
before calling Session.model_validate(...).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.models.documents import SessionDocument
from app.infrastructure.repositories.cached_session_repository import CachedSessionRepository
from app.infrastructure.repositories.mongo_session_repository import MongoSessionRepository


@pytest.fixture
def mongo_repo() -> MongoSessionRepository:
    return MongoSessionRepository()


class TestMongoSessionRepositoryMigration:
    @pytest.mark.asyncio
    async def test_find_by_id_applies_migration_before_model_validate(self, mongo_repo: MongoSessionRepository) -> None:
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "obj",
                "session_id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                "status": "running",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                # Intentionally omit schema_version to simulate legacy payloads.
            }
        )

        migrate = MagicMock(side_effect=lambda raw: {**raw, "schema_version": 1})

        with (
            patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection),
            patch("app.infrastructure.repositories.mongo_session_repository.migrate_session", migrate),
        ):
            session = await mongo_repo.find_by_id("s1")

        assert session is not None
        migrate.assert_called_once()
        # Ensure the migrator saw the normalized domain payload shape.
        migrated_input = migrate.call_args.args[0]
        assert migrated_input.get("id") == "s1"

    @pytest.mark.asyncio
    async def test_find_by_id_loads_legacy_payload_as_schema_v1(self, mongo_repo: MongoSessionRepository) -> None:
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={
                "_id": "obj",
                "session_id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                "status": "running",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                # Intentionally omit schema_version to simulate a v0 payload.
            }
        )

        with patch.object(SessionDocument, "get_pymongo_collection", create=True, return_value=mock_collection):
            session = await mongo_repo.find_by_id("s1")

        assert session is not None
        assert session.id == "s1"
        assert session.schema_version == 1


class TestCachedSessionRepositoryMigration:
    @pytest.mark.asyncio
    async def test_cached_get_applies_migration_before_model_validate(self) -> None:
        cache = MagicMock()
        cache.get = AsyncMock(
            return_value={
                "id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                # Intentionally omit schema_version to simulate legacy cached payloads.
            }
        )

        inner = MagicMock()
        repo = CachedSessionRepository(inner=inner, cache=cache)

        migrate = MagicMock(side_effect=lambda raw: {**raw, "schema_version": 1})

        with patch("app.infrastructure.repositories.cached_session_repository.migrate_session", migrate):
            session = await repo._get_cached("s1")

        assert session is not None
        migrate.assert_called_once()
        migrated_input = migrate.call_args.args[0]
        assert migrated_input.get("id") == "s1"

    @pytest.mark.asyncio
    async def test_cached_get_loads_legacy_payload_as_schema_v1(self) -> None:
        cache = MagicMock()
        cache.get = AsyncMock(
            return_value={
                "id": "s1",
                "user_id": "u1",
                "agent_id": "a1",
                # Intentionally omit schema_version to simulate a v0 payload.
            }
        )

        inner = MagicMock()
        repo = CachedSessionRepository(inner=inner, cache=cache)

        session = await repo._get_cached("s1")

        assert session is not None
        assert session.id == "s1"
        assert session.schema_version == 1
