"""Human-readable command formatting for tool calls (Pythinker-style).

Generates full, descriptive sentences for tool operations that clearly
explain what the agent is doing. This improves user understanding of
agent actions in the UI.

Examples:
- "Search for OpenRouter free tier LLM models available for agent tasks"
- "Navigate to OpenRouter pricing page to get detailed pricing information"
- "Read the full markdown content of the OpenRouter free models page"
- "Save initial findings about OpenRouter free models"
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Matches CJK Unified Ideographs, CJK Compatibility, Hangul, Kana, and other
# non-Latin scripts that should never appear in file paths, URLs, or resource IDs.
_NON_ASCII_RE = re.compile(r"[^\x00-\x7F]+")


def _sanitize_path_like(text: str) -> str:
    """Strip non-ASCII characters from path-like or URL-like strings.

    Some LLM providers (e.g. MiniMax M2.7) inject CJK characters into
    tool call arguments meant to be file paths, URLs, or resource IDs.
    This produces garbled display text like "ev保存://trs-162a26da4366".
    Stripping non-ASCII from these structural strings fixes the display
    without affecting legitimate multilingual content (search queries, etc.).
    """
    cleaned = _NON_ASCII_RE.sub("", text)
    # Collapse any resulting double-slashes or whitespace
    cleaned = re.sub(r"/{3,}", "//", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _truncate(text: str, max_length: int = 60) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _format_url(url: str, max_length: int = 50) -> str:
    """Format URL for display: extract domain + path."""
    url = _sanitize_path_like(url)
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        display = parsed.netloc + parsed.path
        return _truncate(display, max_length)
    except Exception:
        return _truncate(url, max_length)


def _format_file_path(path: str) -> str:
    """Format file path: remove common prefixes and extract filename."""
    path = _sanitize_path_like(path)
    # Remove common sandbox prefixes
    return path.replace("/home/ubuntu/", "").replace("/workspace/", "")


class CommandFormatter:
    """Formats tool calls as human-readable descriptions for UI display.

    Generates Pythinker-style full sentences that clearly describe what
    the agent is doing, improving user understanding and trust.
    """

    @staticmethod
    def format_tool_call(
        tool_name: str,
        function_name: str,
        function_args: dict[str, Any],
    ) -> tuple[str, str, str]:
        """Format tool call into display components.

        Args:
            tool_name: Name of the tool
            function_name: Function being called
            function_args: Function arguments

        Returns:
            Tuple of (display_command, command_category, command_summary)
            - display_command: Full human-readable description
            - command_category: Category for styling (search, browse, file, shell, etc.)
            - command_summary: Short summary for compact displays
        """
        # Route to specific formatter based on tool/function name
        formatters = {
            "search": CommandFormatter._format_search,
            "info_search": CommandFormatter._format_search,
            "browser": CommandFormatter._format_browser,
            "shell": CommandFormatter._format_shell,
            "file": CommandFormatter._format_file,
            "mcp": CommandFormatter._format_mcp,
            "git": CommandFormatter._format_git,
            "code": CommandFormatter._format_code,
            "test": CommandFormatter._format_test,
            "message": CommandFormatter._format_message,
            "wide_research": CommandFormatter._format_wide_research,
            "deal": CommandFormatter._format_deal,
        }

        for prefix, formatter in formatters.items():
            if tool_name.startswith(prefix) or function_name.startswith(prefix):
                return formatter(function_name, function_args)

        # Default formatting
        return CommandFormatter._format_default(function_name, function_args)

    @staticmethod
    def _format_search(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format search commands."""
        query = args.get("query", args.get("topic", ""))
        truncated_query = _truncate(query, 80)

        description = f"Search for {truncated_query}"
        summary = _truncate(query, 40)

        return (description, "search", summary)

    @staticmethod
    def _format_wide_research(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format wide research commands."""
        topic = args.get("topic", "")
        queries = args.get("queries", [])

        if topic:
            description = f'Deep research on "{_truncate(topic, 60)}"'
        elif queries:
            description = f"Research across {len(queries)} queries"
        else:
            description = "Conducting deep research"

        return (description, "search", _truncate(topic, 40))

    @staticmethod
    def _format_browser(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format browser commands."""
        if "navigate" in function_name or "go_to" in function_name:
            url = args.get("url", "")
            formatted_url = _format_url(url, 60)
            return (f"Navigate to {formatted_url}", "browse", formatted_url)

        if "view" in function_name or "get_content" in function_name:
            return ("Read the current page content", "browse", "Read page")

        if "click" in function_name:
            index = args.get("index")
            selector = args.get("selector", "element")
            if index is not None:
                return (f"Click on element {index}", "browse", f"Click #{index}")
            return (f"Click on {_truncate(selector, 30)}", "browse", "Click")

        if "input" in function_name or "type" in function_name:
            text = _truncate(args.get("text", ""), 40)
            return (f'Type "{text}"', "browse", "Type text")

        if "scroll" in function_name:
            direction = "down" if "down" in function_name else "up"
            return (f"Scroll {direction} to see more content", "browse", f"Scroll {direction}")

        if "press_key" in function_name:
            key = args.get("key", "key")
            return (f"Press {key} key", "browse", f"Press {key}")

        if "select" in function_name:
            option = args.get("option", "option")
            return (f"Select option {option}", "browse", "Select")

        if "restart" in function_name:
            url = args.get("url", "")
            return (f"Restart browser and navigate to {_format_url(url)}", "browse", "Restart")

        if "console" in function_name:
            if "exec" in function_name:
                return ("Execute JavaScript in browser console", "browse", "Run JS")
            return ("View browser console output", "browse", "Console")

        return (f"Browser: {function_name}", "browse", function_name)

    @staticmethod
    def _format_shell(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format shell commands."""
        command = args.get("command", "")

        # Extract first meaningful line
        lines = [line.strip() for line in command.split("\n") if line.strip() and not line.strip().startswith("#")]
        first_line = lines[0] if lines else command

        # Clean up command for display
        display_cmd = _truncate(first_line, 80)

        # Try to make it more descriptive for common commands
        if command.startswith("cd "):
            directory = command[3:].strip()
            return (f"Change directory to {directory}", "shell", display_cmd)

        if command.startswith("pip install") or command.startswith("npm install") or command.startswith("bun install"):
            return (f"Install packages: {display_cmd}", "shell", display_cmd)

        if command.startswith("python ") or command.startswith("python3 "):
            script = command.split()[1] if len(command.split()) > 1 else "script"
            return (f"Run Python script: {script}", "shell", display_cmd)

        if command.startswith("node "):
            script = command.split()[1] if len(command.split()) > 1 else "script"
            return (f"Run Node.js script: {script}", "shell", display_cmd)

        if command.startswith("conda "):
            return (f"Conda: {display_cmd}", "shell", display_cmd)

        if command.startswith("git "):
            return (f"Git: {display_cmd}", "shell", display_cmd)

        if "pytest" in command or "test" in command.lower():
            return (f"Run tests: {display_cmd}", "shell", display_cmd)

        return (display_cmd, "shell", _truncate(first_line, 40))

    @staticmethod
    def _format_file(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format file commands."""
        file_path = args.get("file", args.get("path", args.get("file_path", "")))
        clean_path = _format_file_path(file_path)
        filename = clean_path.split("/")[-1] if "/" in clean_path else clean_path

        if "read" in function_name:
            return (f"Read the full content of {clean_path}", "file", filename)

        if "write" in function_name:
            if args.get("append"):
                return (f"Append content to {clean_path}", "file", filename)
            return (f"Save content to {clean_path}", "file", filename)

        if "replace" in function_name or "str_replace" in function_name:
            return (f"Edit {clean_path}", "file", filename)

        if "find" in function_name:
            if "content" in function_name:
                pattern = args.get("regex", "pattern")
                return (f'Search for "{_truncate(pattern, 30)}" in {filename}', "file", filename)
            glob_pattern = args.get("glob", "*")
            return (f"Find files matching {glob_pattern}", "file", glob_pattern)

        if "list" in function_name:
            directory = clean_path or "."
            return (f"List files in {directory}", "file", directory)

        return (f"File operation: {clean_path}", "file", filename)

    @staticmethod
    def _format_mcp(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format MCP tool commands."""
        # Extract tool name from function (e.g., mcp__tavily__search -> tavily search)
        parts = function_name.split("__")
        tool_name = " ".join(parts[1:]) if len(parts) >= 3 else function_name.replace("mcp_", "").replace("_", " ")
        resource = _sanitize_path_like(args.get("resource", args.get("tool_name", "")))

        if resource:
            return (f"Using extension: {tool_name}", "mcp", resource[:30])
        return (f"Using extension: {tool_name}", "mcp", tool_name)

    @staticmethod
    def _format_git(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format git commands."""
        repo_path = _sanitize_path_like(args.get("repo_path", args.get("path", "")))
        repo_name = repo_path.split("/")[-1] if repo_path else "repository"

        if "clone" in function_name:
            url = _sanitize_path_like(args.get("url", ""))
            repo = url.split("/")[-1].replace(".git", "") if url else "repository"
            return (f"Clone repository {repo}", "git", repo)

        if "status" in function_name:
            return (f"Check git status of {repo_name}", "git", "status")

        if "diff" in function_name:
            return (f"View changes in {repo_name}", "git", "diff")

        if "log" in function_name:
            return (f"View commit history of {repo_name}", "git", "log")

        if "branch" in function_name:
            return (f"List branches in {repo_name}", "git", "branches")

        if "commit" in function_name:
            message = _truncate(args.get("message", ""), 40)
            return (f'Commit: "{message}"', "git", "commit")

        if "push" in function_name:
            return ("Push changes to remote", "git", "push")

        if "pull" in function_name:
            return ("Pull latest changes", "git", "pull")

        return (f"Git {function_name.replace('git_', '')}", "git", function_name)

    @staticmethod
    def _format_code(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format code execution commands."""
        language = args.get("language", "python")
        code = args.get("code", "")
        file_path = _sanitize_path_like(args.get("file_path", ""))

        if file_path:
            filename = file_path.split("/")[-1]
            return (f"Run {filename}", "code", filename)

        # Get first meaningful line of code
        lines = [line.strip() for line in code.split("\n") if line.strip() and not line.strip().startswith("#")]
        first_line = _truncate(lines[0], 40) if lines else "code"

        if "install" in function_name:
            packages = args.get("packages", [])
            if packages:
                return (f"Install packages: {', '.join(packages[:3])}", "code", "install")
            return ("Install packages", "code", "install")

        return (f"Execute {language} code", "code", first_line)

    @staticmethod
    def _format_test(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format test runner commands."""
        test_path = _sanitize_path_like(args.get("test_path", args.get("file_path", args.get("suite_name", ""))))
        test_name = test_path.split("/")[-1] if test_path else "tests"

        return (f"Run tests: {test_name}", "test", test_name)

    @staticmethod
    def _format_message(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format message commands."""
        text = args.get("text", args.get("message", args.get("question", "")))
        truncated = _truncate(text, 60)

        if "ask" in function_name:
            return (truncated, "message", "Question")

        if "notify" in function_name:
            return (truncated, "message", "Notification")

        return (truncated, "message", "Message")

    @staticmethod
    def _format_deal(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format deal scraper commands."""
        if function_name == "deal_search":
            query = args.get("query", "")
            stores = args.get("stores", [])
            store_text = f" across {', '.join(stores[:3])}" if stores else ""
            return (f'Finding deals for "{_truncate(query, 60)}"{store_text}', "search", _truncate(query, 40))
        if function_name == "deal_compare_prices":
            urls = args.get("urls", [])
            return (f"Comparing prices across {len(urls)} stores", "search", f"{len(urls)} stores")
        if function_name == "deal_find_coupons":
            store = args.get("store_name", "")
            return (f"Finding coupons for {_truncate(store, 40)}", "search", _truncate(store, 30))
        return CommandFormatter._format_default(function_name, args)

    @staticmethod
    def _format_default(function_name: str, args: dict) -> tuple[str, str, str]:
        """Default formatter for unknown tools."""
        # Try to make it readable
        readable_name = function_name.replace("_", " ").title()

        # Get first arg value
        first_arg = ""
        for value in args.values():
            if isinstance(value, str) and len(value) < 60:
                first_arg = value
                break

        if first_arg:
            return (f"{readable_name}: {_truncate(first_arg, 50)}", "other", readable_name)

        return (readable_name, "other", readable_name)
