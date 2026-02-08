"""Handler for enriching tool events with action metadata.

This module extracts tool-specific metadata from ToolEvent instances,
following the Strategy pattern for clean separation of concerns.
"""

import logging
from collections.abc import Callable

from app.domain.models.event import ToolEvent

logger = logging.getLogger(__name__)


class ToolEventHandler:
    """Enriches ToolEvents with action-specific metadata.

    Responsible for:
    - Setting action_type based on tool_name
    - Extracting command, file_path, cwd from function_args
    - Setting observation_type for completed tool calls
    - Determining if events need file caching or preview content
    """

    # File operations that modify content and need diff tracking
    _FILE_WRITE_OPERATIONS: frozenset[str] = frozenset({"file_write", "file_str_replace"})

    def enrich_action_metadata(self, event: ToolEvent) -> None:
        """Enrich event with action metadata based on tool type.

        Sets action_type, command, cwd, and file_path fields in-place.

        Args:
            event: The ToolEvent to enrich
        """
        handler = self._get_action_handler(event.tool_name)
        if handler:
            handler(event)

    def enrich_observation_metadata(self, event: ToolEvent) -> None:
        """Enrich event with observation metadata for completed calls.

        Sets observation_type field in-place.

        Args:
            event: The ToolEvent to enrich
        """
        handler = self._get_observation_handler(event.tool_name)
        if handler:
            handler(event)

    def needs_file_cache(self, event: ToolEvent) -> bool:
        """Check if event needs file content caching for diff generation.

        Args:
            event: The ToolEvent to check

        Returns:
            True if the event is a file write operation that needs caching
        """
        return event.tool_name == "file" and event.function_name in self._FILE_WRITE_OPERATIONS

    def needs_preview_content(self, event: ToolEvent) -> bool:
        """Check if event needs preview content for streaming UI.

        Args:
            event: The ToolEvent to check

        Returns:
            True if the event should show preview content during execution
        """
        return event.tool_name == "file" and event.function_name == "file_write"

    def _get_action_handler(self, tool_name: str) -> Callable[[ToolEvent], None] | None:
        """Get the action metadata handler for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Handler method or None if no handler exists
        """
        handlers = {
            "shell": self._handle_shell_action,
            "code_executor": self._handle_code_executor_action,
            "file": self._handle_file_action,
            "browser": self._handle_browser_action,
            "browser_agent": self._handle_browser_action,
            "browsing": self._handle_browser_action,
            "search": self._handle_search_action,
            "mcp": self._handle_mcp_action,
        }
        return handlers.get(tool_name)

    def _get_observation_handler(self, tool_name: str) -> Callable[[ToolEvent], None] | None:
        """Get the observation metadata handler for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Handler method or None if no handler exists
        """
        handlers = {
            "shell": self._handle_shell_observation,
            "file": self._handle_file_observation,
            "code_executor": self._handle_code_executor_observation,
        }
        return handlers.get(tool_name)

    # --- Action Handlers ---

    def _handle_shell_action(self, event: ToolEvent) -> None:
        """Handle shell tool action metadata."""
        event.action_type = "run"
        event.command = event.function_args.get("command")
        event.cwd = event.function_args.get("exec_dir")

    def _handle_code_executor_action(self, event: ToolEvent) -> None:
        """Handle code_executor tool action metadata."""
        event.action_type = "run"
        event.command = event.function_args.get("code") or event.function_args.get("command")

    def _handle_file_action(self, event: ToolEvent) -> None:
        """Handle file tool action metadata."""
        event.file_path = event.function_args.get("file")

        # Map function names to action types
        action_map = {
            "file_read": "read",
            "file_write": "write",
            "file_str_replace": "edit",
        }
        event.action_type = action_map.get(event.function_name, "edit")

    def _handle_browser_action(self, event: ToolEvent) -> None:
        """Handle browser/browser_agent tool action metadata."""
        event.action_type = "browse"

    def _handle_search_action(self, event: ToolEvent) -> None:
        """Handle search tool action metadata.

        Search now uses browser, so action type is browse.
        """
        event.action_type = "browse"

    def _handle_mcp_action(self, event: ToolEvent) -> None:
        """Handle MCP tool action metadata."""
        event.action_type = "call_tool"

    async def log_tool_to_vectors(
        self,
        tool_name: str,
        input_summary: str,
        outcome: str,
        error_type: str | None,
        session_id: str,
        user_id: str,
    ) -> None:
        """Log tool execution to vector store for cross-session learning.

        Wraps in try/except — tool logging must never block execution.
        """
        try:
            import uuid

            from app.domain.repositories.vector_repos import (
                get_embedding_provider,
                get_tool_log_repository,
            )

            tool_repo = get_tool_log_repository()
            embedding_provider = get_embedding_provider()
            if not tool_repo or not embedding_provider:
                return

            embedding = await embedding_provider.embed(f"{tool_name}: {input_summary[:500]}")

            await tool_repo.log_tool_execution(
                log_id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                embedding=embedding,
                outcome=outcome,
                input_summary=input_summary[:500],
                error_type=error_type,
            )
        except Exception as e:
            logger.debug(f"Tool vector logging failed (non-critical): {e}")

    # --- Observation Handlers ---

    def _handle_shell_observation(self, event: ToolEvent) -> None:
        """Handle shell tool observation metadata."""
        event.observation_type = "run"

    def _handle_file_observation(self, event: ToolEvent) -> None:
        """Handle file tool observation metadata."""
        event.observation_type = "edit"

    def _handle_code_executor_observation(self, event: ToolEvent) -> None:
        """Handle code_executor tool observation metadata."""
        event.observation_type = "run"
