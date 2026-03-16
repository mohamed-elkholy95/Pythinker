"""Tests for extract_json_from_shell_output utility.

Validates that JSON payloads are correctly extracted from sandbox terminal
output that may be wrapped in [CMD_BEGIN]...[CMD_END] shell framing markers.
"""

import json

import pytest

from app.domain.utils.text import extract_json_from_shell_output


class TestExtractJsonFromShellOutput:
    """Test suite for shell output JSON extraction."""

    def test_clean_json_passthrough(self):
        """Clean JSON input is returned unchanged."""
        raw = '{"success": true, "data_points": 8}'
        assert extract_json_from_shell_output(raw) == raw

    def test_clean_json_with_whitespace(self):
        """JSON with leading/trailing whitespace is stripped."""
        raw = '  \n  {"success": true}  \n  '
        assert extract_json_from_shell_output(raw) == '{"success": true}'

    def test_clean_json_array(self):
        """JSON array input is returned unchanged."""
        raw = '[1, 2, 3]'
        assert extract_json_from_shell_output(raw) == raw

    def test_shell_framed_plotly_output(self):
        """Real-world Plotly orchestrator output with CMD markers is extracted."""
        raw = (
            "[CMD_BEGIN]\n"
            "ubuntu@sandbox:~\n"
            "[CMD_END] /opt/base-python-venv/bin/python3 /app/scripts/generate_comparison_chart_plotly.py "
            "< /workspace/plotly_input_de30fe11.json\n"
            '{"success": true, "html_path": "/workspace/report.html", '
            '"png_path": "/workspace/report.png", "html_size": 9171, '
            '"png_size": 224745, "data_points": 8}\n'
        )
        result = extract_json_from_shell_output(raw)
        assert '"success": true' in result
        assert '"data_points": 8' in result
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["data_points"] == 8

    def test_shell_framed_error_output(self):
        """Shell-framed error JSON is still extracted."""
        raw = (
            "[CMD_BEGIN]\n"
            "ubuntu@sandbox:~\n"
            "[CMD_END] python3 script.py\n"
            '{"success": false, "error": "File not found"}\n'
        )
        result = extract_json_from_shell_output(raw)
        parsed = json.loads(result)
        assert parsed["success"] is False
        assert parsed["error"] == "File not found"

    def test_multiple_json_lines_returns_last(self):
        """When multiple JSON lines exist, returns the last valid one."""
        raw = (
            "Loading config...\n"
            '{"status": "loading"}\n'
            "Processing...\n"
            '{"success": true, "result": "done"}\n'
        )
        result = extract_json_from_shell_output(raw)
        parsed = json.loads(result)
        assert parsed["success"] is True

    def test_empty_input(self):
        """Empty input returns empty."""
        assert extract_json_from_shell_output("") == ""

    def test_none_like_empty(self):
        """None-like empty strings are handled."""
        assert extract_json_from_shell_output("   ") == ""

    def test_no_json_returns_stripped(self):
        """Input with no JSON returns the stripped input."""
        raw = "ubuntu@sandbox:~ some output without json"
        result = extract_json_from_shell_output(raw)
        assert result == raw.strip()

    def test_json_embedded_in_text(self):
        """JSON embedded in surrounding text is extracted via substring."""
        raw = 'Some text before {"key": "value"} some text after'
        result = extract_json_from_shell_output(raw)
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_multiline_json(self):
        """Multiline JSON (pretty-printed) spanning multiple lines."""
        raw = (
            "[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] python3 script.py\n"
            '{\n  "success": true,\n  "data": [1, 2, 3]\n}\n'
        )
        result = extract_json_from_shell_output(raw)
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["data"] == [1, 2, 3]
