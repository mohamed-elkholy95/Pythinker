"""BSON/MongoDB utility helpers.

Centralizes ObjectId conversion and document normalization used
across multiple infrastructure repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId

logger = logging.getLogger(__name__)

__all__ = [
    "normalize_doc_id",
    "normalize_for_mongodb",
    "to_object_id",
]


def to_object_id(id_str: str) -> ObjectId:
    """Convert a string to a MongoDB ObjectId.

    Args:
        id_str: 24-character hex string representation of an ObjectId.

    Returns:
        Corresponding ObjectId instance.

    Raises:
        ValueError: If *id_str* is not a valid ObjectId string.
    """
    try:
        return ObjectId(id_str)
    except Exception as exc:
        raise ValueError(f"Invalid ObjectId string: {id_str!r}") from exc


def normalize_for_mongodb(value: Any) -> Any:
    """Recursively normalize values for BSON serialization.

    MongoDB requires document keys to be strings.  Some payload
    producers (e.g. sparse vectors) use integer keys, so this
    function converts all mapping keys to strings and recurses
    into nested structures.

    Args:
        value: Any Python value to normalize.

    Returns:
        Normalized value safe for BSON serialization.
    """
    if isinstance(value, dict):
        return {str(key): normalize_for_mongodb(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_for_mongodb(item) for item in value]
    return value


def normalize_doc_id(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB ``_id`` field from ObjectId to str in-place.

    This is the most common post-query normalization step: raw
    MongoDB documents contain an :class:`~bson.ObjectId` ``_id``
    that downstream code expects as a plain string.

    Args:
        doc: Raw MongoDB document (may contain ObjectId ``_id``).

    Returns:
        The same dict with ``_id`` converted to str (or unchanged
        if the key is absent or already a string).
    """
    if "_id" in doc and isinstance(doc["_id"], ObjectId):
        doc["_id"] = str(doc["_id"])
    return doc
