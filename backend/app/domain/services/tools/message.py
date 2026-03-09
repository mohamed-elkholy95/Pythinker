from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, tool

_TELEGRAM_CALLBACK_DATA_MAX_BYTES = 64
_TELEGRAM_ACTION_TYPES = frozenset(
    {
        "edit_text",
        "edit_buttons",
        "delete",
        "react",
        "poll",
        "topic_create",
        "sticker",
        "pin",
        "unpin",
    }
)


def _normalize_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _normalize_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_string_list(value: object, *, min_items: int = 1, max_items: int | None = None) -> list[str] | None:
    if not isinstance(value, list):
        return None
    normalized: list[str] = []
    for item in value:
        text = _normalize_non_empty_string(item)
        if text:
            normalized.append(text)
    if len(normalized) < min_items:
        return None
    if max_items is not None and len(normalized) > max_items:
        return None
    return normalized


def normalize_message_notify_buttons(value: object) -> list[list[dict[str, str]]] | None:
    """Normalize Telegram inline-button rows from a tool-call payload."""
    if not isinstance(value, list):
        return None

    rows: list[list[dict[str, str]]] = []
    for row in value:
        if not isinstance(row, list):
            continue

        normalized_row: list[dict[str, str]] = []
        for button in row:
            if not isinstance(button, Mapping):
                continue

            text = button.get("text")
            callback_data = button.get("callback_data")
            if not isinstance(text, str) or not isinstance(callback_data, str):
                continue

            normalized_text = text.strip()
            normalized_callback_data = callback_data.strip()
            if not normalized_text or not normalized_callback_data:
                continue
            if len(normalized_callback_data.encode("utf-8")) > _TELEGRAM_CALLBACK_DATA_MAX_BYTES:
                continue

            normalized_row.append(
                {
                    "text": normalized_text,
                    "callback_data": normalized_callback_data,
                }
            )

        if normalized_row:
            rows.append(normalized_row)

    return rows or None


def normalize_message_notify_telegram_action(value: object) -> dict[str, Any] | None:
    """Normalize a bounded Telegram action payload from a tool-call payload."""
    if not isinstance(value, Mapping):
        return None

    action_type = str(value.get("type", "") or "").strip().lower()
    if action_type not in _TELEGRAM_ACTION_TYPES:
        return None

    normalized: dict[str, Any] = {"type": action_type}

    if action_type in {"edit_text", "edit_buttons", "delete", "react"}:
        message_id = _normalize_positive_int(value.get("message_id"))
        if message_id is None:
            return None
        normalized["message_id"] = message_id

    if action_type == "react":
        remove = bool(value.get("remove"))
        if remove:
            normalized["remove"] = True
            return normalized

        emoji = str(value.get("emoji", "") or "").strip()
        if not emoji:
            return None
        normalized["emoji"] = emoji
        return normalized

    if action_type == "poll":
        question = _normalize_non_empty_string(value.get("question"))
        options = _normalize_string_list(value.get("options"), min_items=2, max_items=10)
        if not question or not options:
            return None
        normalized["question"] = question
        normalized["options"] = options
        if "allows_multiple_answers" in value:
            normalized["allows_multiple_answers"] = bool(value.get("allows_multiple_answers"))
        if "is_anonymous" in value:
            normalized["is_anonymous"] = bool(value.get("is_anonymous"))
        open_period = _normalize_positive_int(value.get("open_period"))
        if open_period is not None:
            normalized["open_period"] = open_period
        return normalized

    if action_type == "topic_create":
        name = _normalize_non_empty_string(value.get("name"))
        if not name:
            return None
        normalized["name"] = name
        icon_color = _normalize_positive_int(value.get("icon_color"))
        if icon_color is not None:
            normalized["icon_color"] = icon_color
        icon_custom_emoji_id = _normalize_non_empty_string(value.get("icon_custom_emoji_id"))
        if icon_custom_emoji_id:
            normalized["icon_custom_emoji_id"] = icon_custom_emoji_id
        return normalized

    if action_type == "sticker":
        file_id = _normalize_non_empty_string(value.get("file_id"))
        if not file_id:
            return None
        normalized["file_id"] = file_id
        return normalized

    if action_type in {"pin", "unpin"}:
        message_id = _normalize_positive_int(value.get("message_id"))
        if message_id is None:
            return None
        normalized["message_id"] = message_id
        if action_type == "pin" and "disable_notification" in value:
            normalized["disable_notification"] = bool(value.get("disable_notification"))
        return normalized

    return normalized


def build_message_notify_delivery_metadata(function_args: Mapping[str, Any]) -> dict[str, Any] | None:
    """Extract normalized delivery metadata for `message_notify_user` tool events."""
    metadata: dict[str, Any] = {}
    buttons = normalize_message_notify_buttons(function_args.get("buttons"))
    if buttons:
        metadata["reply_markup"] = {
            "inline_keyboard": buttons,
        }

    quote_text = _normalize_non_empty_string(function_args.get("quote_text"))
    if quote_text:
        metadata["quote_text"] = quote_text

    telegram_action = normalize_message_notify_telegram_action(function_args.get("telegram_action"))
    if telegram_action:
        metadata["telegram_action"] = telegram_action

    return metadata or None


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
            "buttons": {
                "type": "array",
                "description": "(Optional) Telegram inline keyboard rows as [[{text, callback_data}]].",
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "callback_data": {"type": "string"},
                        },
                        "required": ["text", "callback_data"],
                    },
                },
            },
            "quote_text": {
                "type": "string",
                "description": "(Optional) Text to quote from the replied-to message (Telegram reply_parameters.quote).",
            },
            "telegram_action": {
                "type": "object",
                "description": (
                    "(Optional) Telegram-native action envelope. Supported types: "
                    "edit_text, edit_buttons, delete, react, poll, topic_create, sticker."
                ),
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "edit_text",
                            "edit_buttons",
                            "delete",
                            "react",
                            "poll",
                            "topic_create",
                            "sticker",
                            "pin",
                            "unpin",
                        ],
                    },
                    "message_id": {"type": "integer"},
                    "emoji": {"type": "string"},
                    "remove": {"type": "boolean"},
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "allows_multiple_answers": {"type": "boolean"},
                    "is_anonymous": {"type": "boolean"},
                    "open_period": {"type": "integer"},
                    "name": {"type": "string"},
                    "icon_color": {"type": "integer"},
                    "icon_custom_emoji_id": {"type": "string"},
                    "file_id": {"type": "string"},
                },
            },
        },
        required=["text"],
    )
    async def message_notify_user(
        self,
        text: str,
        attachments: str | list[str] | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
        quote_text: str | None = None,
        telegram_action: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Send notification message to user, no response needed

        Args:
            text: Message text to display to user
            attachments: (Optional) List of attachments to show to user
            buttons: (Optional) Telegram inline keyboard rows
            quote_text: (Optional) Text to quote from the replied-to message
            telegram_action: (Optional) Telegram-native delivery action

        Returns:
            Message sending result
        """
        del buttons, quote_text, telegram_action

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
