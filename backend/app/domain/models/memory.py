import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.domain.models.tool_result import ToolResult


logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """Configuration for memory management"""
    max_messages: int = 100
    auto_compact_threshold: int = 50
    compactable_functions: List[str] = None
    preserve_recent: int = 10

    def __post_init__(self):
        if self.compactable_functions is None:
            self.compactable_functions = [
                "browser_view",
                "browser_navigate",
                "shell_exec",
                "file_read",
                "file_list",
            ]


class Memory(BaseModel):
    """
    Memory class, defining the basic behavior of memory
    """
    messages: List[Dict[str, Any]] = []
    # Exclude config from serialization - it's runtime-only configuration
    config: MemoryConfig = Field(default_factory=MemoryConfig, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def model_post_init(self, __context) -> None:
        """Ensure config is always initialized after deserialization"""
        if self.config is None:
            object.__setattr__(self, 'config', MemoryConfig())

    def get_message_role(self, message: Dict[str, Any]) -> str:
        """Get the role of the message"""
        return message.get("role")

    def add_message(self, message: Dict[str, Any]) -> None:
        """Add message to memory"""
        self.messages.append(message)
        self._check_auto_compact()

    def add_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Add messages to memory"""
        self.messages.extend(messages)
        self._check_auto_compact()

    def _check_auto_compact(self) -> None:
        """Check if auto-compaction should be triggered"""
        if len(self.messages) >= self.config.auto_compact_threshold:
            logger.debug(f"Auto-compacting memory at {len(self.messages)} messages")
            self.smart_compact()

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all message history"""
        return self.messages

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get the last message"""
        if len(self.messages) > 0:
            return self.messages[-1]
        return None

    def roll_back(self) -> None:
        """Roll back memory"""
        self.messages = self.messages[:-1]

    def compact(self) -> None:
        """Compact memory (legacy method, use smart_compact for better results)"""
        for message in self.messages:
            if message.get("role") == "tool":
                if message.get("function_name") in ["browser_view", "browser_navigate"]:
                    message["content"] = ToolResult(success=True, data='(removed)').model_dump_json()
                    logger.debug(f"Removed tool result from memory: {message['function_name']}")

    def smart_compact(self, preserve_recent: Optional[int] = None) -> int:
        """
        Smart compaction with configurable options.

        Compacts tool results from verbose functions while preserving
        recent messages that may be needed for context.

        Args:
            preserve_recent: Number of recent messages to preserve (uses config default if None)

        Returns:
            Number of messages compacted
        """
        preserve_count = preserve_recent if preserve_recent is not None else self.config.preserve_recent
        compacted = 0

        # Calculate which messages to potentially compact
        compact_until = len(self.messages) - preserve_count

        for i, message in enumerate(self.messages):
            # Skip recent messages
            if i >= compact_until:
                break

            # Only compact tool messages
            if message.get("role") != "tool":
                continue

            function_name = message.get("function_name", "")

            # Check if this function should be compacted
            if function_name in self.config.compactable_functions:
                # Check if already compacted
                content = message.get("content", "")
                if "(removed)" not in content and "(compacted)" not in content:
                    # Compact the content
                    message["content"] = ToolResult(
                        success=True,
                        data='(compacted)'
                    ).model_dump_json()
                    compacted += 1
                    logger.debug(f"Smart-compacted tool result: {function_name}")

        if compacted > 0:
            logger.info(f"Smart-compacted {compacted} tool results")

        return compacted

    def estimate_tokens(self, chars_per_token: int = 4) -> int:
        """
        Estimate token count for memory.

        Uses a simple character-based estimation. For accurate counts,
        use TokenManager with tiktoken.

        Args:
            chars_per_token: Average characters per token

        Returns:
            Estimated token count
        """
        total_chars = 0

        for message in self.messages:
            content = message.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)

            # Count tool calls
            tool_calls = message.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                total_chars += len(func.get("name", ""))
                total_chars += len(str(func.get("arguments", "")))

        return total_chars // chars_per_token

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        role_counts = {}
        for msg in self.messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "total_messages": len(self.messages),
            "role_counts": role_counts,
            "estimated_tokens": self.estimate_tokens(),
            "auto_compact_threshold": self.config.auto_compact_threshold,
        }

    @property
    def empty(self) -> bool:
        """Check if memory is empty"""
        return len(self.messages) == 0
