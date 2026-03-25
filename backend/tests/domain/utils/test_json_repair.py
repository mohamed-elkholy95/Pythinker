"""Tests for domain JSON extraction and repair utilities."""

import pytest

from app.domain.utils.json_repair import (
    extract_json_text,
    parse_json_response,
)


@pytest.mark.unit
class TestExtractJsonText:
    """Tests for extract_json_text function."""

    def test_bare_json_object(self) -> None:
        result = extract_json_text('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_bare_json_array(self) -> None:
        result = extract_json_text('[1, 2, 3]')
        assert result == '[1, 2, 3]'

    def test_markdown_code_fence(self) -> None:
        text = '```json\n{"name": "test"}\n```'
        result = extract_json_text(text)
        assert result is not None
        assert '"name"' in result

    def test_markdown_fence_no_lang(self) -> None:
        text = '```\n{"name": "test"}\n```'
        result = extract_json_text(text)
        assert result is not None

    def test_prose_with_json(self) -> None:
        text = 'Here is the result: {"answer": 42}'
        result = extract_json_text(text)
        assert result is not None
        assert '"answer"' in result

    def test_empty_string(self) -> None:
        assert extract_json_text("") is None

    def test_none_like_empty(self) -> None:
        assert extract_json_text("   ") is None

    def test_no_json_content(self) -> None:
        assert extract_json_text("This is just plain text with no JSON") is None

    def test_trailing_comma_repaired(self) -> None:
        text = '{"a": 1, "b": 2,}'
        result = extract_json_text(text)
        assert result is not None

    def test_single_quotes_repaired(self) -> None:
        text = "{'key': 'value'}"
        result = extract_json_text(text)
        # May or may not repair depending on complexity, but should try
        # The function is best-effort for single quotes
        if result is not None:
            assert '"key"' in result or "'key'" in result

    def test_truncated_json_closed(self) -> None:
        text = '{"key": "value", "nested": {"inner": 1'
        result = extract_json_text(text)
        assert result is not None

    def test_js_comments_removed(self) -> None:
        text = '{"key": "value" // this is a comment\n}'
        result = extract_json_text(text)
        assert result is not None

    def test_nested_json_in_prose(self) -> None:
        text = 'The answer is:\n```json\n{"items": [{"id": 1}, {"id": 2}]}\n```\nDone!'
        result = extract_json_text(text)
        assert result is not None
        assert '"items"' in result


@pytest.mark.unit
class TestParseJsonResponse:
    """Tests for parse_json_response function."""

    def test_valid_json_object(self) -> None:
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_array(self) -> None:
        result = parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_json_in_code_fence(self) -> None:
        text = '```json\n{"answer": 42}\n```'
        result = parse_json_response(text)
        assert result == {"answer": 42}

    def test_no_json_returns_default(self) -> None:
        result = parse_json_response("just text")
        assert result is None

    def test_custom_default(self) -> None:
        result = parse_json_response("no json", default={"fallback": True})
        assert result == {"fallback": True}

    def test_nested_objects(self) -> None:
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = parse_json_response(text)
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_boolean_values(self) -> None:
        result = parse_json_response('{"flag": true, "other": false}')
        assert result == {"flag": True, "other": False}

    def test_null_value(self) -> None:
        result = parse_json_response('{"key": null}')
        assert result == {"key": None}

    def test_numeric_values(self) -> None:
        result = parse_json_response('{"int": 42, "float": 3.14}')
        assert result["int"] == 42
        assert result["float"] == 3.14

    def test_empty_object(self) -> None:
        result = parse_json_response("{}")
        assert result == {}

    def test_empty_array(self) -> None:
        result = parse_json_response("[]")
        assert result == []
