"""Tests for domain text manipulation utilities."""

import pytest

from app.domain.utils.text import (
    TextTruncator,
    TruncationResult,
    TruncationStyle,
    extract_json_from_shell_output,
    truncate,
    truncate_output,
)


@pytest.mark.unit
class TestTruncationStyle:
    """Tests for TruncationStyle enum."""

    def test_ellipsis_value(self) -> None:
        assert TruncationStyle.ELLIPSIS == "ellipsis"

    def test_bracketed_value(self) -> None:
        assert TruncationStyle.BRACKETED == "bracketed"

    def test_preserve_ends_value(self) -> None:
        assert TruncationStyle.PRESERVE_ENDS == "preserve_ends"


@pytest.mark.unit
class TestTruncationResult:
    """Tests for TruncationResult dataclass."""

    def test_chars_removed_property(self) -> None:
        result = TruncationResult(
            content="hel...",
            was_truncated=True,
            original_length=11,
            truncated_length=6,
        )
        assert result.chars_removed == 5

    def test_no_truncation(self) -> None:
        result = TruncationResult(
            content="hello",
            was_truncated=False,
            original_length=5,
            truncated_length=5,
        )
        assert result.chars_removed == 0


@pytest.mark.unit
class TestTextTruncator:
    """Tests for TextTruncator class."""

    # truncate() tests
    def test_truncate_short_text_unchanged(self) -> None:
        assert TextTruncator.truncate("hello", 10) == "hello"

    def test_truncate_exact_length(self) -> None:
        assert TextTruncator.truncate("hello", 5) == "hello"

    def test_truncate_long_text(self) -> None:
        result = TextTruncator.truncate("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_truncate_empty_string(self) -> None:
        assert TextTruncator.truncate("", 10) == ""

    def test_truncate_none_like(self) -> None:
        assert TextTruncator.truncate("", 5) == ""

    def test_truncate_custom_ellipsis(self) -> None:
        result = TextTruncator.truncate("hello world", 9, ellipsis="…")
        assert result.endswith("…")

    def test_truncate_max_smaller_than_ellipsis(self) -> None:
        result = TextTruncator.truncate("hello world", 2)
        assert len(result) == 2

    # truncate_with_result() tests
    def test_truncate_with_result_truncated(self) -> None:
        result = TextTruncator.truncate_with_result("hello world", 8)
        assert result.was_truncated is True
        assert result.original_length == 11
        assert result.truncated_length == 8
        assert result.chars_removed == 3

    def test_truncate_with_result_not_truncated(self) -> None:
        result = TextTruncator.truncate_with_result("hi", 10)
        assert result.was_truncated is False
        assert result.content == "hi"

    # truncate_preserving_ends() tests
    def test_preserve_ends_short_text(self) -> None:
        text = "short"
        assert TextTruncator.truncate_preserving_ends(text, 100) == text

    def test_preserve_ends_keeps_both(self) -> None:
        text = "A" * 100 + "B" * 100
        result = TextTruncator.truncate_preserving_ends(text, 80)
        assert result.startswith("A")
        assert result.endswith("B")
        assert "truncated" in result

    # truncate_lines() tests
    def test_truncate_lines_short(self) -> None:
        text = "line1\nline2\nline3"
        assert TextTruncator.truncate_lines(text, keep_first=5, keep_last=3) == text

    def test_truncate_lines_long(self) -> None:
        lines = [f"line{i}" for i in range(20)]
        text = "\n".join(lines)
        result = TextTruncator.truncate_lines(text, keep_first=3, keep_last=2)
        assert "line0" in result
        assert "line1" in result
        assert "line2" in result
        assert "line19" in result
        assert "omitted" in result

    def test_truncate_lines_with_max_lines(self) -> None:
        lines = [f"line{i}" for i in range(50)]
        text = "\n".join(lines)
        result = TextTruncator.truncate_lines(text, max_lines=10)
        assert "omitted" in result

    def test_truncate_lines_empty(self) -> None:
        assert TextTruncator.truncate_lines("") == ""

    # truncate_for_logging() tests
    def test_truncate_for_logging_basic(self) -> None:
        data = {"key": "value", "long": "A" * 200}
        result = TextTruncator.truncate_for_logging(data, max_value_length=50)
        assert len(result["long"]) <= 50
        assert result["key"] == "value"

    def test_truncate_for_logging_max_keys(self) -> None:
        data = {f"key{i}": f"val{i}" for i in range(10)}
        result = TextTruncator.truncate_for_logging(data, max_keys=3)
        assert len(result) == 4  # 3 keys + "..." indicator
        assert "..." in result

    def test_truncate_for_logging_empty(self) -> None:
        assert TextTruncator.truncate_for_logging({}) == {}

    # truncate_docstring() tests
    def test_truncate_docstring(self) -> None:
        doc = "First line summary.\n\nDetailed description here."
        result = TextTruncator.truncate_docstring(doc, max_length=50)
        assert result == "First line summary."

    def test_truncate_docstring_empty(self) -> None:
        assert TextTruncator.truncate_docstring("") == ""

    def test_truncate_docstring_long_first_line(self) -> None:
        doc = "A" * 200
        result = TextTruncator.truncate_docstring(doc, max_length=50)
        assert len(result) == 50


@pytest.mark.unit
class TestExtractJsonFromShellOutput:
    """Tests for extract_json_from_shell_output function."""

    def test_clean_json_passthrough(self) -> None:
        result = extract_json_from_shell_output('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_clean_array_passthrough(self) -> None:
        result = extract_json_from_shell_output('[1, 2, 3]')
        assert result == '[1, 2, 3]'

    def test_shell_framed_output(self) -> None:
        raw = """[CMD_BEGIN]
ubuntu@sandbox:~
[CMD_END] python3 script.py
{"success": true, "data_points": 8}"""
        result = extract_json_from_shell_output(raw)
        assert '"success": true' in result

    def test_empty_input(self) -> None:
        assert extract_json_from_shell_output("") == ""

    def test_no_json_returns_stripped(self) -> None:
        raw = "no json here"
        result = extract_json_from_shell_output(raw)
        assert result == "no json here"

    def test_json_last_line(self) -> None:
        raw = "some output\nmore output\n{\"result\": 42}"
        result = extract_json_from_shell_output(raw)
        assert '"result": 42' in result

    def test_multiline_json_extraction(self) -> None:
        raw = 'prefix text\n{"a": 1, "b": 2}'
        result = extract_json_from_shell_output(raw)
        assert '"a": 1' in result


@pytest.mark.unit
class TestBackwardCompatFunctions:
    """Tests for backward-compatible convenience functions."""

    def test_truncate_convenience(self) -> None:
        assert truncate("hello world", 8) == "hello..."

    def test_truncate_output_preserves_end(self) -> None:
        text = "A" * 100 + "B" * 100
        result = truncate_output(text, 80, preserve_end=True)
        assert result.endswith("B")

    def test_truncate_output_no_preserve(self) -> None:
        text = "hello world" * 10
        result = truncate_output(text, 20, preserve_end=False)
        assert len(result) == 20
