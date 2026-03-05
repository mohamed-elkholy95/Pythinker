"""Tests for file management enforcement (design 2B)."""

import time

import pytest

from app.domain.services.tools.file import FileTool


class TestFileOverwriteBlocking:
    def _make_tool(self):
        tool = FileTool.__new__(FileTool)
        tool._write_history = {}
        tool._overwrite_blocked_until = {}
        tool._recent_write_sizes = {}
        return tool

    def test_no_warning_below_threshold(self):
        tool = self._make_tool()
        result = tool._check_repetitive_overwrites("/workspace/report.md", append=False)
        assert result is None

    def test_blocks_after_third_overwrite(self):
        tool = self._make_tool()
        path = "/workspace/report.md"
        now = time.monotonic()
        tool._write_history[path] = [now - 2, now - 1, now]
        result = tool._check_repetitive_overwrites(path, append=False)
        assert result is not None
        assert "ERROR" in result
        assert "BLOCKED" in result
        assert path in tool._overwrite_blocked_until

    def test_blocked_path_returns_error(self):
        tool = self._make_tool()
        path = "/workspace/report.md"
        tool._overwrite_blocked_until[path] = time.monotonic() + 60.0
        result = tool._check_repetitive_overwrites(path, append=False)
        assert result is not None
        assert "BLOCKED" in result

    def test_append_not_blocked(self):
        tool = self._make_tool()
        result = tool._check_repetitive_overwrites("/workspace/report.md", append=True)
        assert result is None


class TestContentRegressionEnforcement:
    def _make_tool(self):
        tool = FileTool.__new__(FileTool)
        tool._write_history = {}
        tool._overwrite_blocked_until = {}
        tool._recent_write_sizes = {}
        return tool

    def test_severe_regression_returns_error(self):
        tool = self._make_tool()
        tool._recent_write_sizes["/workspace/report.md"] = 2000
        result = tool._check_content_regression("/workspace/report.md", "x" * 100)  # 5% of original
        assert result is not None
        assert "ERROR" in result

    def test_moderate_regression_returns_warning(self):
        tool = self._make_tool()
        tool._recent_write_sizes["/workspace/report.md"] = 2000
        result = tool._check_content_regression("/workspace/report.md", "x" * 1100)  # 55% — between 50-60%
        assert result is not None
        assert "WARNING" in result

    def test_no_regression_returns_none(self):
        tool = self._make_tool()
        tool._recent_write_sizes["/workspace/report.md"] = 1000
        result = tool._check_content_regression("/workspace/report.md", "x" * 900)  # 90%
        assert result is None
