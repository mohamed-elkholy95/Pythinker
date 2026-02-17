"""Tests for tool_stream_parser — partial JSON content extraction."""

from __future__ import annotations

import json

from app.domain.services.agents.tool_stream_parser import (
    STREAMABLE_CONTENT_KEYS,
    content_type_for_function,
    extract_partial_content,
    is_streamable_function,
)

# ── is_streamable_function ──────────────────────────────────────────────


class TestIsStreamableFunction:
    def test_known_functions_are_streamable(self) -> None:
        for fn in STREAMABLE_CONTENT_KEYS:
            assert is_streamable_function(fn), f"{fn} should be streamable"

    def test_unknown_function_not_streamable(self) -> None:
        assert not is_streamable_function("browser_navigate")
        assert not is_streamable_function("browser_click")
        assert not is_streamable_function("")


# ── content_type_for_function ──────────────────────────────────────────


class TestContentTypeForFunction:
    def test_code_execution_returns_code(self) -> None:
        assert content_type_for_function("code_execute_python") == "code"
        assert content_type_for_function("code_execute_javascript") == "code"
        assert content_type_for_function("code_execute") == "code"

    def test_file_operations_return_text(self) -> None:
        assert content_type_for_function("file_write") == "text"
        assert content_type_for_function("file_str_replace") == "text"
        assert content_type_for_function("code_save_artifact") == "text"


# ── extract_partial_content — complete JSON ────────────────────────────


class TestExtractCompleteJSON:
    """Test extraction when the accumulated JSON is valid."""

    def test_file_write_complete(self) -> None:
        args = json.dumps({"file": "/tmp/test.py", "content": "import os\nimport sys\n"})
        result = extract_partial_content("file_write", args)
        assert result == "import os\nimport sys\n"

    def test_file_str_replace_complete(self) -> None:
        args = json.dumps({"file": "/app.py", "old_str": "foo", "new_str": "bar"})
        result = extract_partial_content("file_str_replace", args)
        assert result == "bar"

    def test_code_execute_python_complete(self) -> None:
        code = "print('hello world')\nfor i in range(10):\n    print(i)"
        args = json.dumps({"code": code})
        result = extract_partial_content("code_execute_python", args)
        assert result == code

    def test_code_save_artifact_complete(self) -> None:
        args = json.dumps({"filename": "report.md", "content": "# Report\n\nContent here."})
        result = extract_partial_content("code_save_artifact", args)
        assert result == "# Report\n\nContent here."

    def test_returns_none_for_unknown_function(self) -> None:
        args = json.dumps({"url": "https://example.com"})
        assert extract_partial_content("browser_navigate", args) is None

    def test_returns_none_when_field_missing(self) -> None:
        args = json.dumps({"file": "/tmp/test.py"})
        assert extract_partial_content("file_write", args) is None

    def test_returns_none_when_field_is_not_string(self) -> None:
        args = json.dumps({"file": "/tmp/test.py", "content": 42})
        assert extract_partial_content("file_write", args) is None


# ── extract_partial_content — truncated JSON ───────────────────────────


class TestExtractTruncatedJSON:
    """Test extraction from incomplete JSON (regex fallback)."""

    def test_truncated_mid_content(self) -> None:
        partial = '{"file": "/tmp/test.py", "content": "import os\\nimport sys'
        result = extract_partial_content("file_write", partial)
        assert result is not None
        assert "import os" in result
        assert "import sys" in result

    def test_truncated_after_opening_brace_only(self) -> None:
        partial = "{"
        assert extract_partial_content("file_write", partial) is None

    def test_truncated_before_content_field(self) -> None:
        partial = '{"file": "/tmp/test.py"'
        assert extract_partial_content("file_write", partial) is None

    def test_truncated_at_content_key(self) -> None:
        partial = '{"file": "/tmp/test.py", "content"'
        assert extract_partial_content("file_write", partial) is None

    def test_truncated_at_content_colon(self) -> None:
        partial = '{"file": "/tmp/test.py", "content": '
        assert extract_partial_content("file_write", partial) is None

    def test_truncated_at_content_opening_quote(self) -> None:
        partial = '{"file": "/tmp/test.py", "content": "'
        # Empty string — regex captures empty group
        result = extract_partial_content("file_write", partial)
        assert result is None or result == ""

    def test_truncated_with_escape_sequences(self) -> None:
        partial = '{"file": "test.py", "content": "line1\\nline2\\ttabbed'
        result = extract_partial_content("file_write", partial)
        assert result is not None
        assert result == "line1\nline2\ttabbed"

    def test_truncated_with_escaped_quotes(self) -> None:
        partial = '{"file": "test.py", "content": "say \\"hello\\"'
        result = extract_partial_content("file_write", partial)
        assert result is not None
        assert result == 'say "hello"'

    def test_truncated_with_backslash(self) -> None:
        partial = '{"file": "test.py", "content": "path\\\\to\\\\file'
        result = extract_partial_content("file_write", partial)
        assert result is not None
        assert result == "path\\to\\file"

    def test_code_execute_truncated(self) -> None:
        partial = '{"code": "for i in range(10):\\n    print(i)'
        result = extract_partial_content("code_execute_python", partial)
        assert result is not None
        assert "for i in range(10):" in result

    def test_file_str_replace_truncated(self) -> None:
        partial = '{"file": "app.py", "old_str": "foo", "new_str": "bar_replacement'
        result = extract_partial_content("file_str_replace", partial)
        assert result is not None
        assert "bar_replacement" in result


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_string(self) -> None:
        assert extract_partial_content("file_write", "") is None

    def test_very_short_string(self) -> None:
        assert extract_partial_content("file_write", "{}") is None

    def test_none_like_partial(self) -> None:
        assert extract_partial_content("file_write", "null") is None

    def test_unicode_content(self) -> None:
        args = json.dumps({"file": "test.txt", "content": "Hello \u4e16\u754c \U0001f680"})
        result = extract_partial_content("file_write", args)
        assert result is not None
        assert "\u4e16\u754c" in result
        assert "\U0001f680" in result  # rocket emoji

    def test_multiline_content(self) -> None:
        content = "line1\nline2\nline3\n\n# Header\n\nParagraph"
        args = json.dumps({"file": "doc.md", "content": content})
        result = extract_partial_content("file_write", args)
        assert result == content

    def test_large_content(self) -> None:
        """Ensure parser handles large file content without issues."""
        content = "x" * 100_000
        args = json.dumps({"file": "big.txt", "content": content})
        result = extract_partial_content("file_write", args)
        assert result == content

    def test_content_with_json_inside(self) -> None:
        """Content that itself contains JSON should be extracted correctly."""
        inner_json = '{"key": "value", "list": [1, 2, 3]}'
        args = json.dumps({"file": "data.json", "content": inner_json})
        result = extract_partial_content("file_write", args)
        assert result == inner_json
