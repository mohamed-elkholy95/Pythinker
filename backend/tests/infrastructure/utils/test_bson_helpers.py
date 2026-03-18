"""Tests for app.infrastructure.utils.bson_helpers."""

from __future__ import annotations

import pytest
from bson import ObjectId

from app.infrastructure.utils.bson_helpers import (
    normalize_doc_id,
    normalize_for_mongodb,
    to_object_id,
)


# ---------------------------------------------------------------------------
# to_object_id
# ---------------------------------------------------------------------------
class TestToObjectId:
    """Tests for the to_object_id helper."""

    def test_valid_hex_string(self) -> None:
        hex_str = "507f1f77bcf86cd799439011"
        result = to_object_id(hex_str)
        assert isinstance(result, ObjectId)
        assert str(result) == hex_str

    def test_roundtrip(self) -> None:
        original = ObjectId()
        result = to_object_id(str(original))
        assert result == original

    def test_invalid_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid ObjectId string"):
            to_object_id("not-a-valid-id")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid ObjectId string"):
            to_object_id("")


# ---------------------------------------------------------------------------
# normalize_for_mongodb
# ---------------------------------------------------------------------------
class TestNormalizeForMongodb:
    """Tests for the normalize_for_mongodb helper."""

    def test_dict_with_string_keys_unchanged(self) -> None:
        data = {"name": "test", "value": 42}
        result = normalize_for_mongodb(data)
        assert result == {"name": "test", "value": 42}

    def test_dict_with_integer_keys_converted(self) -> None:
        data = {0: "a", 1: "b", 2: "c"}
        result = normalize_for_mongodb(data)
        assert result == {"0": "a", "1": "b", "2": "c"}

    def test_nested_dict_with_integer_keys(self) -> None:
        data = {"sparse_vector": {10: 0.5, 20: 0.8, 30: 0.1}}
        result = normalize_for_mongodb(data)
        assert result == {"sparse_vector": {"10": 0.5, "20": 0.8, "30": 0.1}}

    def test_list_values_recursed(self) -> None:
        data = [{"a": 1}, {2: "b"}]
        result = normalize_for_mongodb(data)
        assert result == [{"a": 1}, {"2": "b"}]

    def test_tuple_converted_to_list(self) -> None:
        data = (1, 2, 3)
        result = normalize_for_mongodb(data)
        assert result == [1, 2, 3]

    def test_deeply_nested_structure(self) -> None:
        data = {
            "level1": {
                0: {
                    "level3": [
                        {1: "deep"},
                    ],
                },
            },
        }
        expected = {
            "level1": {
                "0": {
                    "level3": [
                        {"1": "deep"},
                    ],
                },
            },
        }
        result = normalize_for_mongodb(data)
        assert result == expected

    def test_primitive_passthrough(self) -> None:
        assert normalize_for_mongodb(42) == 42
        assert normalize_for_mongodb("hello") == "hello"
        assert normalize_for_mongodb(3.14) == 3.14
        assert normalize_for_mongodb(None) is None
        assert normalize_for_mongodb(True) is True

    def test_empty_dict(self) -> None:
        assert normalize_for_mongodb({}) == {}

    def test_empty_list(self) -> None:
        assert normalize_for_mongodb([]) == []


# ---------------------------------------------------------------------------
# normalize_doc_id
# ---------------------------------------------------------------------------
class TestNormalizeDocId:
    """Tests for the normalize_doc_id helper."""

    def test_objectid_converted_to_str(self) -> None:
        oid = ObjectId()
        doc = {"_id": oid, "name": "test"}
        result = normalize_doc_id(doc)
        assert result["_id"] == str(oid)
        assert isinstance(result["_id"], str)

    def test_already_string_id_unchanged(self) -> None:
        doc = {"_id": "already-a-string", "name": "test"}
        result = normalize_doc_id(doc)
        assert result["_id"] == "already-a-string"

    def test_no_id_field_unchanged(self) -> None:
        doc = {"name": "test", "value": 42}
        result = normalize_doc_id(doc)
        assert "_id" not in result

    def test_mutates_dict_in_place(self) -> None:
        oid = ObjectId()
        doc = {"_id": oid}
        result = normalize_doc_id(doc)
        assert result is doc  # same object
        assert doc["_id"] == str(oid)

    def test_other_fields_preserved(self) -> None:
        oid = ObjectId()
        doc = {"_id": oid, "status": "active", "count": 5}
        normalize_doc_id(doc)
        assert doc["status"] == "active"
        assert doc["count"] == 5
