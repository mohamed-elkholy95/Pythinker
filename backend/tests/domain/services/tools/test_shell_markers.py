"""Tests for structured terminal marker parsing in ShellTool."""
import pytest
from app.domain.services.tools.shell import ShellTool, CMD_BEGIN, CMD_END


class TestStructuredMarkerParsing:
    def test_extract_with_markers(self):
        raw = f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} ls\nfile1.txt\nfile2.py\n{CMD_END}"
        result = ShellTool._extract_structured_output(raw)
        assert "file1.txt" in result
        assert CMD_BEGIN not in result

    def test_extract_without_markers_fallback(self):
        raw = "ubuntu@sandbox:~ $ ls\nfile1.txt\nfile2.py"
        result = ShellTool._extract_structured_output(raw)
        assert result == raw

    def test_extract_multiple_commands(self):
        raw = (
            f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} ls\nfile1.txt\n{CMD_END}"
            f"{CMD_BEGIN}\nubuntu@sandbox:~\n{CMD_END} pwd\n/home/ubuntu\n{CMD_END}"
        )
        result = ShellTool._extract_structured_output(raw)
        assert "file1.txt" in result
        assert "/home/ubuntu" in result

    def test_extract_empty_output(self):
        result = ShellTool._extract_structured_output("")
        assert result == ""
