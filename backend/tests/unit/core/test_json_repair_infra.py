"""Tests for infrastructure JSON repair module."""

import json

import pytest
from pydantic import BaseModel

from app.infrastructure.external.llm.json_repair import (
    extract_text_from_response,
    format_tool_result,
    parse_json_model,
)


class SampleModel(BaseModel):
    name: str
    value: int


@pytest.mark.unit
class TestParseJsonModel:
    """Tests for parse_json_model function."""

    def test_valid_json_parses(self) -> None:
        result = parse_json_model('{"name": "test", "value": 42}', SampleModel)
        assert result is not None
        assert result.name == "test"
        assert result.value == 42

    def test_json_in_markdown_fence(self) -> None:
        text = '```json\n{"name": "fenced", "value": 1}\n```'
        result = parse_json_model(text, SampleModel)
        assert result is not None
        assert result.name == "fenced"

    def test_invalid_json_returns_none(self) -> None:
        result = parse_json_model("not json at all", SampleModel)
        assert result is None

    def test_schema_mismatch_returns_none(self) -> None:
        result = parse_json_model('{"wrong_field": "value"}', SampleModel)
        assert result is None

    def test_strict_mode_raises_on_no_json(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON"):
            parse_json_model("no json here", SampleModel, strict=True)

    def test_strict_mode_raises_on_schema_mismatch(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            parse_json_model('{"wrong": "data"}', SampleModel, strict=True)

    def test_json_with_prose_prefix(self) -> None:
        text = 'Here is the result: {"name": "embedded", "value": 99}'
        result = parse_json_model(text, SampleModel)
        assert result is not None
        assert result.value == 99

    def test_empty_string_returns_none(self) -> None:
        result = parse_json_model("", SampleModel)
        assert result is None


@pytest.mark.unit
class TestFormatToolResult:
    """Tests for format_tool_result function."""

    def test_dict_serialized(self) -> None:
        result = format_tool_result({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_list_serialized(self) -> None:
        result = format_tool_result([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_valid_json_string_passthrough(self) -> None:
        json_str = '{"already": "json"}'
        result = format_tool_result(json_str)
        assert result == json_str

    def test_plain_string_wrapped(self) -> None:
        result = format_tool_result("hello world")
        parsed = json.loads(result)
        assert parsed == {"result": "hello world"}

    def test_int_serialized(self) -> None:
        result = format_tool_result(42)
        parsed = json.loads(result)
        assert parsed == 42

    def test_none_serialized(self) -> None:
        result = format_tool_result(None)
        parsed = json.loads(result)
        assert parsed is None

    def test_unicode_preserved(self) -> None:
        result = format_tool_result({"emoji": "🎉"})
        assert "🎉" in result

    def test_non_serializable_falls_back(self) -> None:
        from datetime import UTC, datetime

        result = format_tool_result({"time": datetime.now(UTC)})
        parsed = json.loads(result)
        assert "time" in parsed


@pytest.mark.unit
class TestExtractTextFromResponse:
    """Tests for extract_text_from_response function."""

    def test_string_content(self) -> None:
        response = {"content": "Hello world"}
        assert extract_text_from_response(response) == "Hello world"

    def test_list_content_with_text_blocks(self) -> None:
        response = {
            "content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ]
        }
        assert extract_text_from_response(response) == "Part 1 Part 2"

    def test_list_content_with_strings(self) -> None:
        response = {"content": ["Hello", "World"]}
        assert extract_text_from_response(response) == "Hello World"

    def test_empty_content(self) -> None:
        assert extract_text_from_response({}) == ""

    def test_none_content(self) -> None:
        assert extract_text_from_response({"content": None}) == ""

    def test_mixed_block_types(self) -> None:
        response = {
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "image", "url": "http://example.com/img.png"},
            ]
        }
        result = extract_text_from_response(response)
        assert "Hello" in result
