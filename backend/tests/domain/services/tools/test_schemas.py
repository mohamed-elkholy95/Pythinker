"""Tests for tool input schema validation.

Covers all Pydantic model validators, field constraints,
the validate_tool_args decorator, and the schema registry.
"""

import pytest
from pydantic import ValidationError

from app.domain.services.tools.schemas import (
    TOOL_SCHEMAS,
    BrowserClickArgs,
    BrowserInputArgs,
    BrowserNavigateArgs,
    FileReadArgs,
    FileSearchArgs,
    FileWriteArgs,
    MCPToolCallArgs,
    SearchWebArgs,
    ShellBackgroundArgs,
    ShellExecuteArgs,
    get_schema_for_tool,
    validate_args,
    validate_tool_args,
)


# ─────────────────────────────────────────────────────────────
# ShellExecuteArgs
# ─────────────────────────────────────────────────────────────


class TestShellExecuteArgs:
    def test_valid_command(self):
        args = ShellExecuteArgs(command="ls -la /tmp")
        assert args.command == "ls -la /tmp"
        assert args.timeout == 60
        assert args.capture_output is True

    def test_command_with_custom_timeout(self):
        args = ShellExecuteArgs(command="sleep 10", timeout=120)
        assert args.timeout == 120

    def test_command_min_length(self):
        with pytest.raises(ValidationError):
            ShellExecuteArgs(command="")

    def test_command_max_length(self):
        with pytest.raises(ValidationError):
            ShellExecuteArgs(command="x" * 10001)

    def test_timeout_min(self):
        with pytest.raises(ValidationError):
            ShellExecuteArgs(command="ls", timeout=0)

    def test_timeout_max(self):
        with pytest.raises(ValidationError):
            ShellExecuteArgs(command="ls", timeout=601)

    def test_blocks_rm_rf_root(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command="rm -rf /")

    def test_blocks_dd_devzero(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command="dd if=/dev/zero of=/dev/sda")

    def test_blocks_mkfs(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command="mkfs.ext4 /dev/sda1")

    def test_blocks_fork_bomb(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command=":() { :|:& }")

    def test_blocks_direct_disk_write(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command="echo x > /dev/sda")

    def test_allows_safe_rm_without_slash(self):
        args = ShellExecuteArgs(command="rm -rf mydir")
        assert "rm" in args.command

    def test_blocks_rm_rf_any_absolute(self):
        # The regex blocks "rm -rf /" which also catches "rm -rf /tmp"
        with pytest.raises(ValidationError, match="dangerous"):
            ShellExecuteArgs(command="rm -rf /tmp/mydir")

    def test_working_directory_none(self):
        args = ShellExecuteArgs(command="ls", working_directory=None)
        assert args.working_directory is None

    def test_working_directory_valid(self):
        args = ShellExecuteArgs(command="ls", working_directory="/home/user/project")
        assert args.working_directory == "/home/user/project"

    def test_working_directory_tmp(self):
        args = ShellExecuteArgs(command="ls", working_directory="/tmp/build")
        assert args.working_directory == "/tmp/build"

    def test_working_directory_workspace(self):
        args = ShellExecuteArgs(command="ls", working_directory="/workspace/app")
        assert args.working_directory == "/workspace/app"

    def test_working_directory_relative(self):
        args = ShellExecuteArgs(command="ls", working_directory="./src")
        assert args.working_directory == "./src"

    def test_working_directory_excessive_traversal(self):
        with pytest.raises(ValidationError, match="traversal"):
            ShellExecuteArgs(command="ls", working_directory="../../../../etc")


# ─────────────────────────────────────────────────────────────
# ShellBackgroundArgs
# ─────────────────────────────────────────────────────────────


class TestShellBackgroundArgs:
    def test_inherits_shell_execute(self):
        args = ShellBackgroundArgs(command="python server.py", name="my-server")
        assert args.command == "python server.py"
        assert args.name == "my-server"

    def test_name_optional(self):
        args = ShellBackgroundArgs(command="sleep 999")
        assert args.name is None

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            ShellBackgroundArgs(command="ls", name="x" * 101)

    def test_inherits_dangerous_command_check(self):
        with pytest.raises(ValidationError, match="dangerous"):
            ShellBackgroundArgs(command="rm -rf /")


# ─────────────────────────────────────────────────────────────
# FileReadArgs
# ─────────────────────────────────────────────────────────────


class TestFileReadArgs:
    def test_valid_file_read(self):
        args = FileReadArgs(file="/home/user/test.py")
        assert args.file == "/home/user/test.py"
        assert args.start_line is None
        assert args.end_line is None
        assert args.sudo is False

    def test_with_line_range(self):
        args = FileReadArgs(file="/tmp/test.txt", start_line=10, end_line=50)
        assert args.start_line == 10
        assert args.end_line == 50

    def test_file_min_length(self):
        with pytest.raises(ValidationError):
            FileReadArgs(file="")

    def test_file_max_length(self):
        with pytest.raises(ValidationError):
            FileReadArgs(file="x" * 4097)

    def test_start_line_negative(self):
        with pytest.raises(ValidationError):
            FileReadArgs(file="/tmp/f.py", start_line=-1)

    def test_end_line_negative(self):
        with pytest.raises(ValidationError):
            FileReadArgs(file="/tmp/f.py", end_line=-1)

    def test_sudo_flag(self):
        args = FileReadArgs(file="/etc/config", sudo=True)
        assert args.sudo is True


# ─────────────────────────────────────────────────────────────
# FileWriteArgs
# ─────────────────────────────────────────────────────────────


class TestFileWriteArgs:
    def test_valid_file_write(self):
        args = FileWriteArgs(file="/home/user/out.txt", content="hello world")
        assert args.file == "/home/user/out.txt"
        assert args.content == "hello world"
        assert args.append is False

    def test_append_mode(self):
        args = FileWriteArgs(file="/tmp/log.txt", content="line\n", append=True)
        assert args.append is True

    def test_blocks_etc_passwd(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/etc/passwd", content="bad")

    def test_blocks_etc_shadow(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/etc/shadow", content="bad")

    def test_blocks_etc_sudoers(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/etc/sudoers", content="bad")

    def test_blocks_ssh_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="~/.ssh/authorized_keys", content="bad")

    def test_blocks_gnupg_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="~/.gnupg/keys", content="bad")

    def test_blocks_aws_credentials(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="~/.aws/credentials", content="bad")

    def test_blocks_root_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/root/.bashrc", content="bad")

    def test_blocks_boot_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/boot/grub.cfg", content="bad")

    def test_blocks_sys_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/sys/kernel/something", content="bad")

    def test_blocks_proc_dir(self):
        with pytest.raises(ValidationError, match="protected"):
            FileWriteArgs(file="/proc/self/mem", content="bad")

    def test_allows_workspace_write(self):
        args = FileWriteArgs(file="/workspace/output.md", content="report")
        assert args.file == "/workspace/output.md"

    def test_file_min_length(self):
        with pytest.raises(ValidationError):
            FileWriteArgs(file="", content="x")


# ─────────────────────────────────────────────────────────────
# FileSearchArgs
# ─────────────────────────────────────────────────────────────


class TestFileSearchArgs:
    def test_valid_search(self):
        args = FileSearchArgs(pattern="TODO")
        assert args.pattern == "TODO"
        assert args.max_results == 100
        assert args.case_sensitive is False

    def test_with_directory(self):
        args = FileSearchArgs(pattern="import", directory="/workspace/src")
        assert args.directory == "/workspace/src"

    def test_with_file_pattern(self):
        args = FileSearchArgs(pattern="class", file_pattern="*.py")
        assert args.file_pattern == "*.py"

    def test_case_sensitive(self):
        args = FileSearchArgs(pattern="MyClass", case_sensitive=True)
        assert args.case_sensitive is True

    def test_max_results_bounds(self):
        with pytest.raises(ValidationError):
            FileSearchArgs(pattern="x", max_results=0)
        with pytest.raises(ValidationError):
            FileSearchArgs(pattern="x", max_results=1001)

    def test_pattern_min_length(self):
        with pytest.raises(ValidationError):
            FileSearchArgs(pattern="")


# ─────────────────────────────────────────────────────────────
# BrowserNavigateArgs
# ─────────────────────────────────────────────────────────────


class TestBrowserNavigateArgs:
    def test_valid_url(self):
        args = BrowserNavigateArgs(url="https://example.com")
        assert args.url == "https://example.com"
        assert args.timeout == 30

    def test_http_url(self):
        args = BrowserNavigateArgs(url="http://localhost:8000")
        assert args.url == "http://localhost:8000"

    def test_blocks_file_protocol(self):
        with pytest.raises(ValidationError, match="Blocked protocol"):
            BrowserNavigateArgs(url="file:///etc/passwd")

    def test_blocks_javascript_protocol(self):
        with pytest.raises(ValidationError, match="Blocked protocol"):
            BrowserNavigateArgs(url="javascript:alert(1)")

    def test_blocks_data_html(self):
        with pytest.raises(ValidationError, match="Blocked protocol"):
            BrowserNavigateArgs(url="data:text/html,<script>alert(1)</script>")

    def test_blocks_invalid_protocol(self):
        with pytest.raises(ValidationError, match="must start with"):
            BrowserNavigateArgs(url="ftp://files.example.com/data")

    def test_allows_relative_url(self):
        args = BrowserNavigateArgs(url="/api/v1/health")
        assert args.url == "/api/v1/health"

    def test_allows_about_url(self):
        args = BrowserNavigateArgs(url="about:blank")
        assert args.url == "about:blank"

    def test_timeout_bounds(self):
        with pytest.raises(ValidationError):
            BrowserNavigateArgs(url="https://x.com", timeout=0)
        with pytest.raises(ValidationError):
            BrowserNavigateArgs(url="https://x.com", timeout=301)

    def test_wait_for(self):
        args = BrowserNavigateArgs(url="https://x.com", wait_for="#main")
        assert args.wait_for == "#main"


# ─────────────────────────────────────────────────────────────
# BrowserClickArgs
# ─────────────────────────────────────────────────────────────


class TestBrowserClickArgs:
    def test_valid_click(self):
        args = BrowserClickArgs(selector="#submit-btn")
        assert args.selector == "#submit-btn"
        assert args.button == "left"
        assert args.double_click is False

    def test_right_click(self):
        args = BrowserClickArgs(selector=".menu", button="right")
        assert args.button == "right"

    def test_middle_click(self):
        args = BrowserClickArgs(selector="a", button="middle")
        assert args.button == "middle"

    def test_invalid_button(self):
        with pytest.raises(ValidationError, match="Invalid button"):
            BrowserClickArgs(selector="a", button="invalid")

    def test_button_case_insensitive(self):
        args = BrowserClickArgs(selector="a", button="LEFT")
        assert args.button == "left"

    def test_double_click(self):
        args = BrowserClickArgs(selector="td", double_click=True)
        assert args.double_click is True

    def test_selector_min_length(self):
        with pytest.raises(ValidationError):
            BrowserClickArgs(selector="")


# ─────────────────────────────────────────────────────────────
# BrowserInputArgs
# ─────────────────────────────────────────────────────────────


class TestBrowserInputArgs:
    def test_valid_input(self):
        args = BrowserInputArgs(selector="#search", text="query")
        assert args.selector == "#search"
        assert args.text == "query"
        assert args.clear_first is True
        assert args.press_enter is False

    def test_press_enter(self):
        args = BrowserInputArgs(selector="input", text="test", press_enter=True)
        assert args.press_enter is True

    def test_no_clear(self):
        args = BrowserInputArgs(selector="input", text="append", clear_first=False)
        assert args.clear_first is False


# ─────────────────────────────────────────────────────────────
# SearchWebArgs
# ─────────────────────────────────────────────────────────────


class TestSearchWebArgs:
    def test_valid_search(self):
        args = SearchWebArgs(query="python async patterns")
        assert args.query == "python async patterns"
        assert args.search_type == "info"
        assert args.expand_queries is False

    def test_news_search(self):
        args = SearchWebArgs(query="AI news", search_type="news")
        assert args.search_type == "news"

    def test_academic_search(self):
        args = SearchWebArgs(query="transformer architecture", search_type="academic")
        assert args.search_type == "academic"

    def test_all_valid_search_types(self):
        for t in ("info", "news", "image", "academic", "api", "data", "tool"):
            args = SearchWebArgs(query="test", search_type=t)
            assert args.search_type == t

    def test_invalid_search_type(self):
        with pytest.raises(ValidationError, match="Invalid search type"):
            SearchWebArgs(query="test", search_type="video")

    def test_search_type_case_insensitive(self):
        args = SearchWebArgs(query="test", search_type="NEWS")
        assert args.search_type == "news"

    def test_valid_date_ranges(self):
        for dr in ("all", "past_hour", "past_day", "past_week", "past_month", "past_year"):
            args = SearchWebArgs(query="test", date_range=dr)
            assert args.date_range == dr

    def test_invalid_date_range(self):
        with pytest.raises(ValidationError, match="Invalid date range"):
            SearchWebArgs(query="test", date_range="last_century")

    def test_date_range_none(self):
        args = SearchWebArgs(query="test", date_range=None)
        assert args.date_range is None

    def test_date_range_case_insensitive(self):
        args = SearchWebArgs(query="test", date_range="PAST_WEEK")
        assert args.date_range == "past_week"

    def test_query_min_length(self):
        with pytest.raises(ValidationError):
            SearchWebArgs(query="")

    def test_expand_queries_flag(self):
        args = SearchWebArgs(query="test", expand_queries=True)
        assert args.expand_queries is True


# ─────────────────────────────────────────────────────────────
# MCPToolCallArgs
# ─────────────────────────────────────────────────────────────


class TestMCPToolCallArgs:
    def test_valid_call(self):
        args = MCPToolCallArgs(
            server_name="github",
            tool_name="list_repos",
            arguments={"org": "my-org"},
        )
        assert args.server_name == "github"
        assert args.tool_name == "list_repos"
        assert args.arguments == {"org": "my-org"}

    def test_default_empty_arguments(self):
        args = MCPToolCallArgs(server_name="test", tool_name="ping")
        assert args.arguments == {}

    def test_blocks_semicolon_in_server_name(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="evil;cmd", tool_name="x")

    def test_blocks_pipe_in_tool_name(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="ok", tool_name="x|rm")

    def test_blocks_ampersand(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="ok", tool_name="x&y")

    def test_blocks_dollar(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="$HOME", tool_name="x")

    def test_blocks_backtick(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="`whoami`", tool_name="x")

    def test_blocks_newline(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            MCPToolCallArgs(server_name="ok\ncmd", tool_name="x")


# ─────────────────────────────────────────────────────────────
# validate_tool_args decorator
# ─────────────────────────────────────────────────────────────


class TestValidateToolArgs:
    async def test_async_decorator(self):
        @validate_tool_args(ShellExecuteArgs)
        async def fake_shell(**kwargs):
            return kwargs

        result = await fake_shell(command="ls", timeout=30)
        assert result["command"] == "ls"
        assert result["timeout"] == 30

    def test_sync_decorator(self):
        @validate_tool_args(FileReadArgs)
        def fake_read(**kwargs):
            return kwargs

        result = fake_read(file="/tmp/test.txt")
        assert result["file"] == "/tmp/test.txt"

    async def test_decorator_rejects_invalid(self):
        @validate_tool_args(ShellExecuteArgs)
        async def fake_shell(**kwargs):
            return kwargs

        with pytest.raises(ValidationError):
            await fake_shell(command="")


# ─────────────────────────────────────────────────────────────
# validate_args function
# ─────────────────────────────────────────────────────────────


class TestValidateArgs:
    def test_valid_args(self):
        result = validate_args(ShellExecuteArgs, {"command": "echo hello"})
        assert isinstance(result, ShellExecuteArgs)
        assert result.command == "echo hello"

    def test_invalid_args_raises(self):
        with pytest.raises(ValidationError):
            validate_args(ShellExecuteArgs, {"command": ""})


# ─────────────────────────────────────────────────────────────
# Schema registry and get_schema_for_tool
# ─────────────────────────────────────────────────────────────


class TestSchemaRegistry:
    def test_all_expected_tools_registered(self):
        expected = {
            "shell_execute",
            "shell_background",
            "file_read",
            "file_write",
            "file_search",
            "browser_navigate",
            "browser_click",
            "browser_input",
            "mcp_call",
            "info_search_web",
        }
        assert set(TOOL_SCHEMAS.keys()) == expected

    def test_direct_match(self):
        assert get_schema_for_tool("shell_execute") is ShellExecuteArgs

    def test_direct_match_file_read(self):
        assert get_schema_for_tool("file_read") is FileReadArgs

    def test_partial_match(self):
        schema = get_schema_for_tool("custom_shell_execute_v2")
        assert schema is ShellExecuteArgs

    def test_no_match_returns_none(self):
        assert get_schema_for_tool("nonexistent_tool") is None

    def test_all_schemas_are_pydantic_models(self):
        from pydantic import BaseModel

        for name, cls in TOOL_SCHEMAS.items():
            assert issubclass(cls, BaseModel), f"{name} is not a BaseModel"
