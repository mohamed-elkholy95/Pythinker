"""Test tool-marker text detection in execution module."""
import pytest

from app.domain.services.agents.execution import _is_tool_marker_text

TOOL_MARKER_MESSAGES = [
    '[Attempted to call browser_navigate with {"url": "https://example.com"}]',
    '[Attempted to call file_write with {"path": "/workspace/report.md", "content": "# Report..."}]',
    '[Attempted to call browser_navigate with {"url": "https://exam...]\n[Attempted to call file_read with {"path": "/workspace/data.json"}]',
    '  [Attempted to call web_search with {"query": "test"}]  ',  # whitespace-padded
]

NON_MARKER_MESSAGES = [
    '{"success": true, "result": "done", "attachments": []}',
    "I have completed the research task.",
    "",
    "The [Attempted to call] pattern is inside prose.",
    '[Some other bracket pattern]',
]


@pytest.mark.parametrize("text", TOOL_MARKER_MESSAGES)
def test_detects_tool_marker_text(text):
    assert _is_tool_marker_text(text) is True


@pytest.mark.parametrize("text", NON_MARKER_MESSAGES)
def test_does_not_flag_non_marker_text(text):
    assert _is_tool_marker_text(text) is False
