"""Tests for CommandFormatter — human-readable tool call formatting."""

from app.domain.services.tools.command_formatter import (
    CommandFormatter,
    _format_file_path,
    _format_url,
    _sanitize_path_like,
    _truncate,
)


class TestSanitizePathLike:
    def test_no_change(self) -> None:
        assert _sanitize_path_like("/home/user/file.txt") == "/home/user/file.txt"

    def test_removes_cjk(self) -> None:
        result = _sanitize_path_like("ev保存://trs-162a26da4366")
        assert "保存" not in result

    def test_empty(self) -> None:
        assert _sanitize_path_like("") == ""


class TestTruncate:
    def test_short_text(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_exact_length(self) -> None:
        assert _truncate("hello", 5) == "hello"

    def test_long_text(self) -> None:
        result = _truncate("a" * 100, 20)
        assert len(result) == 20
        assert result.endswith("...")


class TestFormatUrl:
    def test_simple_url(self) -> None:
        result = _format_url("https://example.com/page")
        assert result == "example.com/page"

    def test_long_url_truncated(self) -> None:
        result = _format_url("https://example.com/" + "x" * 100, 30)
        assert len(result) <= 30


class TestFormatFilePath:
    def test_removes_sandbox_prefix(self) -> None:
        assert _format_file_path("/home/ubuntu/report.md") == "report.md"

    def test_removes_workspace_prefix(self) -> None:
        assert _format_file_path("/workspace/data/file.csv") == "data/file.csv"

    def test_normal_path(self) -> None:
        assert _format_file_path("relative/file.py") == "relative/file.py"


class TestCommandFormatterSearch:
    def test_search(self) -> None:
        display, category, _summary = CommandFormatter.format_tool_call(
            "search", "web_search", {"query": "Python 3.12 features"}
        )
        assert "Python 3.12" in display
        assert category == "search"

    def test_search_long_query(self) -> None:
        display, _cat, _ = CommandFormatter.format_tool_call("search", "web_search", {"query": "a" * 200})
        assert len(display) < 200


class TestCommandFormatterBrowser:
    def test_navigate(self) -> None:
        display, category, _ = CommandFormatter.format_tool_call("browser", "navigate", {"url": "https://python.org"})
        assert "Navigate" in display
        assert category == "browse"

    def test_click(self) -> None:
        display, _cat, _ = CommandFormatter.format_tool_call("browser", "click", {"index": 5})
        assert "Click" in display
        assert "5" in display

    def test_type(self) -> None:
        display, _cat, _ = CommandFormatter.format_tool_call("browser", "input_text", {"text": "search query"})
        assert "Type" in display

    def test_scroll_down(self) -> None:
        display, _, _ = CommandFormatter.format_tool_call("browser", "scroll_down", {})
        assert "Scroll" in display
        assert "down" in display

    def test_view_content(self) -> None:
        display, _, _ = CommandFormatter.format_tool_call("browser", "view_content", {})
        assert "page content" in display.lower() or "Read" in display

    def test_restart(self) -> None:
        display, _, _ = CommandFormatter.format_tool_call("browser", "restart_browser", {"url": "https://example.com"})
        assert "Restart" in display


class TestCommandFormatterShell:
    def test_shell(self) -> None:
        _display, category, _ = CommandFormatter.format_tool_call("shell", "run_command", {"command": "ls -la"})
        assert category == "shell"

    def test_multiline(self) -> None:
        display, _, _ = CommandFormatter.format_tool_call(
            "shell", "run_command", {"command": "# comment\nls -la\necho done"}
        )
        assert "ls" in display


class TestCommandFormatterFile:
    def test_file(self) -> None:
        _display, category, _ = CommandFormatter.format_tool_call("file", "file_read", {"path": "/workspace/report.md"})
        assert category == "file"


class TestCommandFormatterDefault:
    def test_unknown_tool(self) -> None:
        display, category, _ = CommandFormatter.format_tool_call("unknown_tool", "do_something", {"arg": "val"})
        assert display
        assert category


class TestCommandFormatterDeal:
    def test_deal(self) -> None:
        display, _cat, _ = CommandFormatter.format_tool_call("deal", "search_deals", {"query": "laptop deals"})
        assert display
