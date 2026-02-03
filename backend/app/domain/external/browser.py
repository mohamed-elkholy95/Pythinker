from typing import Protocol

from app.domain.models.tool_result import ToolResult


class Browser(Protocol):
    """Browser service gateway interface

    Defines the contract for browser automation implementations.
    Supports page navigation, element interaction, and optional
    performance optimizations like resource blocking.
    """

    async def initialize(self) -> bool:
        """Initialize browser connection

        Returns:
            bool: True if initialization succeeded
        """
        ...

    async def cleanup(self) -> None:
        """Clean up browser resources"""
        ...

    async def view_page(self, wait_for_load: bool = True) -> ToolResult:
        """View current page content

        Args:
            wait_for_load: Whether to wait for page load before extracting
        """
        ...

    async def navigate(self, url: str) -> ToolResult:
        """Navigate to specified URL"""
        ...

    async def restart(self, url: str) -> ToolResult:
        """Restart browser and navigate to specified URL"""
        ...

    async def click(
        self, index: int | None = None, coordinate_x: float | None = None, coordinate_y: float | None = None
    ) -> ToolResult:
        """Click element"""
        ...

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: int | None = None,
        coordinate_x: float | None = None,
        coordinate_y: float | None = None,
    ) -> ToolResult:
        """Input text"""
        ...

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        """Move mouse"""
        ...

    async def press_key(self, key: str) -> ToolResult:
        """Simulate key press"""
        ...

    async def select_option(self, index: int, option: int) -> ToolResult:
        """Select dropdown option"""
        ...

    async def scroll_up(self, to_top: bool | None = None) -> ToolResult:
        """Scroll up"""
        ...

    async def scroll_down(self, to_bottom: bool | None = None) -> ToolResult:
        """Scroll down"""
        ...

    async def screenshot(self, full_page: bool | None = False) -> bytes:
        """Take a screenshot of the current page"""
        ...

    async def console_exec(self, javascript: str) -> ToolResult:
        """Execute JavaScript code"""
        ...

    async def console_view(self, max_lines: int | None = None) -> ToolResult:
        """View console output"""
        ...

    async def set_resource_blocking(self, enabled: bool, resource_types: set[str] | None = None) -> None:
        """Enable or disable resource blocking for performance

        Args:
            enabled: Whether to enable blocking
            resource_types: Set of resource types to block (e.g., {"image", "font"})
        """
        ...

    def is_connected(self) -> bool:
        """Check if browser connection is healthy

        Returns:
            bool: True if connection appears healthy
        """
        ...
