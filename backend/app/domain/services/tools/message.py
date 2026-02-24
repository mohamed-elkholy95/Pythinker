from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool


class MessageTool(BaseTool):
    """Message tool class, providing message sending functions for user interaction"""

    name: str = "message"

    def __init__(self):
        """Initialize message tool class"""
        super().__init__()

    @tool(
        name="message_notify_user",
        description="Send a message to user without requiring a response. Use for acknowledging receipt of messages, providing progress updates, reporting task completion, or explaining changes in approach.",
        parameters={
            "text": {"type": "string", "description": "Message text to display to user"},
            "attachments": {
                "anyOf": [{"type": "string"}, {"items": {"type": "string"}, "type": "array"}],
                "description": "(Optional) List of attachments to show to user, can be file paths or URLs",
            },
        },
        required=["text"],
    )
    async def message_notify_user(self, text: str, attachments: str | list[str] | None = None) -> ToolResult:
        """Send notification message to user, no response needed

        Args:
            text: Message text to display to user
            attachments: (Optional) List of attachments to show to user

        Returns:
            Message sending result
        """

        # Return success result, actual UI display logic implemented by caller
        return ToolResult(success=True, data="Continue")

    @tool(
        name="message_ask_user",
        description="Ask user a question and wait for response. Use for requesting clarification, asking for confirmation, or gathering additional information.",
        parameters={
            "text": {"type": "string", "description": "Question text to present to user"},
            "attachments": {
                "anyOf": [{"type": "string"}, {"items": {"type": "string"}, "type": "array"}],
                "description": "(Optional) List of question-related files or reference materials",
            },
            "suggest_user_takeover": {
                "type": "string",
                "enum": ["none", "browser"],
                "description": "(Optional) Suggested operation for user takeover",
            },
            "wait_reason": {
                "type": "string",
                "enum": ["user_input", "captcha", "login", "2fa", "payment", "verification", "other"],
                "description": "(Optional) Structured reason this prompt requires user intervention",
            },
        },
        required=["text"],
    )
    async def message_ask_user(
        self,
        text: str,
        attachments: str | list[str] | None = None,
        suggest_user_takeover: str | None = None,
        wait_reason: str | None = None,
    ) -> ToolResult:
        """Ask user a question and wait for response

        Args:
            text: Question text to present to user
            attachments: List of question-related files or reference materials
            suggest_user_takeover: Suggested operation for user takeover
            wait_reason: Structured reason for waiting on user interaction

        Returns:
            Question asking result with user response
        """

        # Return success result, actual UI interaction logic implemented by caller
        return ToolResult(success=True)
