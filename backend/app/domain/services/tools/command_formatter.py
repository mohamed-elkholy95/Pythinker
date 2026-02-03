"""Human-readable command formatting for tool calls."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CommandFormatter:
    """Formats tool calls as human-readable commands for UI display."""

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
        """
        # Route to specific formatter
        formatters = {
            "search": CommandFormatter._format_search,
            "browser": CommandFormatter._format_browser,
            "shell": CommandFormatter._format_shell,
            "file": CommandFormatter._format_file,
            "mcp": CommandFormatter._format_mcp,
        }

        for prefix, formatter in formatters.items():
            if tool_name.startswith(prefix) or function_name.startswith(prefix):
                return formatter(function_name, function_args)

        # Default formatting
        return (f"{function_name}({', '.join(f'{k}={v}' for k, v in function_args.items())})", "other", function_name)

    @staticmethod
    def _format_search(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format search commands"""
        query = args.get("query", "")

        if "web" in function_name:
            return (f"Searching '{query}'", "search", f"Search: {query[:40]}")
        return (f"Search: {query}", "search", f"Search: {query[:40]}")

    @staticmethod
    def _format_browser(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format browser commands"""
        if "navigate" in function_name:
            url = args.get("url", "")
            domain = url.split("/")[2] if "//" in url else url[:30]
            return (f"Browsing {domain}", "browse", f"Browse: {domain}")

        if "click" in function_name:
            selector = args.get("selector", "element")
            return (f"Clicking {selector}", "browse", f"Click: {selector[:30]}")

        if "type" in function_name or "input" in function_name:
            text = args.get("text", args.get("value", ""))
            return (f"Typing '{text[:30]}...'", "browse", f"Type: {text[:20]}")

        return (f"Browser: {function_name}", "browse", function_name)

    @staticmethod
    def _format_shell(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format shell commands"""
        language = args.get("language", "bash")
        code = args.get("code", "")

        # Extract first meaningful line
        lines = [line.strip() for line in code.split("\n") if line.strip() and not line.strip().startswith("#")]
        first_line = lines[0] if lines else code[:50]

        return (f"Running {language}: {first_line}", "shell", f"{language}: {first_line[:30]}")

    @staticmethod
    def _format_file(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format file commands"""
        path = args.get("path", args.get("file_path", ""))

        if "read" in function_name:
            return (f"Reading {path}", "file", f"Read: {path.split('/')[-1]}")

        if "write" in function_name or "create" in function_name:
            return (f"Creating {path}", "file", f"Create: {path.split('/')[-1]}")

        if "list" in function_name:
            directory = path or args.get("directory", ".")
            return (f"Listing files in {directory}", "file", f"List: {directory}")

        return (f"File operation: {path}", "file", path.split("/")[-1])

    @staticmethod
    def _format_mcp(function_name: str, args: dict) -> tuple[str, str, str]:
        """Format MCP tool commands"""
        server = args.get("server", "")
        resource = args.get("resource", "")

        return (f"MCP: {server}/{resource}", "mcp", f"{server}: {resource}")
