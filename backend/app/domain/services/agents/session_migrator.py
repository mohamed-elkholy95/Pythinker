"""Session schema migration utilities.

Sessions are persisted as JSON-like dict payloads (Mongo documents, Redis cache).
This module provides a lightweight migrator to keep deserialization forwards-
compatible as the Session schema evolves.
"""

from __future__ import annotations

from typing import Any

from app.domain.models.session import CURRENT_SCHEMA_VERSION


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):  # bool is an int subclass; treat explicitly.
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _migrate_v0_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(raw)
    migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    return migrated


def migrate_session(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a migrated copy of *raw* session payload.

    Version 0 is the implicit legacy schema (missing schema_version).
    """
    version = _coerce_int(raw.get("schema_version", 0), default=0)
    if version == 0:
        return _migrate_v0_to_v1(raw)
    return raw
