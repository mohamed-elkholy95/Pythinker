import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class MemoryConfig:
    """Configuration for memory management"""

    max_messages: int = 100
    auto_compact_threshold: int = 50
    # Token-based threshold for smart compaction (default: 60k tokens — leave buffer for response)
    auto_compact_token_threshold: int = 60000
    # Use token-based compaction instead of message count
    use_token_threshold: bool = True
    compactable_functions: list[str] = None
    preserve_recent: int = 8

    def __post_init__(self):
        if self.compactable_functions is None:
            self.compactable_functions = [
                "browser_view",
                "browser_navigate",
                "browser_get_content",
                "shell_exec",
                "shell_view",
                "file_read",
                "file_list",
                "file_list_directory",
                "code_execute",
                "code_run_artifact",
            ]


class Memory(BaseModel):
    """
    Memory class, defining the basic behavior of memory
    """

    messages: list[dict[str, Any]] = Field(default_factory=list)
    # Exclude config from serialization - it's runtime-only configuration
    config: MemoryConfig = Field(default_factory=MemoryConfig, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context) -> None:
        """Ensure config is always initialized after deserialization"""
        if self.config is None:
            object.__setattr__(self, "config", MemoryConfig())

    def get_message_role(self, message: dict[str, Any]) -> str:
        """Get the role of the message"""
        return message.get("role")

    def add_message(self, message: dict[str, Any]) -> None:
        """Add message to memory"""
        self.messages.append(message)
        self._check_auto_compact()

    def add_messages(self, messages: list[dict[str, Any]]) -> None:
        """Add messages to memory"""
        self.messages.extend(messages)
        self._check_auto_compact()

    def _check_auto_compact(self) -> None:
        """Check if auto-compaction should be triggered based on token or message count"""
        if self.config.use_token_threshold:
            # Token-based compaction
            estimated_tokens = self.estimate_tokens()
            if estimated_tokens >= self.config.auto_compact_token_threshold:
                logger.debug(
                    f"Auto-compacting memory at {estimated_tokens} tokens "
                    f"(threshold: {self.config.auto_compact_token_threshold})"
                )
                self.smart_compact()
        else:
            # Legacy message-count based compaction
            if len(self.messages) >= self.config.auto_compact_threshold:
                logger.debug(f"Auto-compacting memory at {len(self.messages)} messages")
                self.smart_compact()

    def get_messages(self) -> list[dict[str, Any]]:
        """Get all message history"""
        return self.messages

    def get_last_message(self) -> dict[str, Any] | None:
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
            if message.get("role") == "tool" and message.get("function_name") in ["browser_view", "browser_navigate"]:
                message["content"] = ToolResult(success=True, data="(removed)").model_dump_json()
                logger.debug(f"Removed tool result from memory: {message['function_name']}")

    def smart_compact(self, preserve_recent: int | None = None) -> int:
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

            content = message.get("content", "")

            # Check if this function should be compacted (replace with stub)
            if function_name in self.config.compactable_functions:
                if "(removed)" not in content and "(compacted)" not in content:
                    message["content"] = ToolResult(success=True, data="(compacted)").model_dump_json()
                    compacted += 1
                    logger.debug(f"Smart-compacted tool result: {function_name}")
            elif function_name and len(content) > 8000 and "(compacted)" not in content and "(removed)" not in content:
                head = content[:3000]
                tail = content[-1000:]
                chars_removed = len(content) - 4000
                message["content"] = f"{head}\n\n... [truncated {chars_removed} chars] ...\n\n{tail}"
                compacted += 1
                logger.debug(
                    f"Truncated large tool result: {function_name} ({len(content)} -> {len(message['content'])} chars)"
                )

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

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics"""
        role_counts = {}
        for msg in self.messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        estimated_tokens = self.estimate_tokens()
        stats = {
            "total_messages": len(self.messages),
            "role_counts": role_counts,
            "estimated_tokens": estimated_tokens,
            "auto_compact_threshold": self.config.auto_compact_threshold,
            "use_token_threshold": self.config.use_token_threshold,
        }

        if self.config.use_token_threshold:
            stats["token_threshold"] = self.config.auto_compact_token_threshold
            stats["token_usage_percent"] = (
                estimated_tokens / self.config.auto_compact_token_threshold * 100
                if self.config.auto_compact_token_threshold > 0
                else 0
            )

        return stats

    @property
    def empty(self) -> bool:
        """Check if memory is empty"""
        return len(self.messages) == 0

    def fork(self, preserve_messages: int | None = None) -> "Memory":
        """Create a fork of this memory for isolated exploration.

        This supports Tree-of-Thoughts pattern where multiple paths
        need independent memory contexts.

        Args:
            preserve_messages: Number of recent messages to include (default: all)

        Returns:
            New Memory instance with copied messages
        """
        if preserve_messages is None:
            # Copy all messages
            forked_messages = [msg.copy() for msg in self.messages]
        else:
            # Copy only recent messages
            forked_messages = [msg.copy() for msg in self.messages[-preserve_messages:]]

        # Create new memory with copied config
        forked_memory = Memory(messages=forked_messages)
        forked_memory.config = MemoryConfig(
            max_messages=self.config.max_messages,
            auto_compact_threshold=self.config.auto_compact_threshold,
            auto_compact_token_threshold=self.config.auto_compact_token_threshold,
            use_token_threshold=self.config.use_token_threshold,
            compactable_functions=self.config.compactable_functions.copy()
            if self.config.compactable_functions
            else None,
            preserve_recent=self.config.preserve_recent,
        )

        return forked_memory

    def merge_from(self, other: "Memory", deduplicate: bool = True) -> int:
        """Merge messages from another memory into this one.

        This supports aggregating results from forked paths.

        Args:
            other: Memory to merge from
            deduplicate: Whether to skip duplicate messages

        Returns:
            Number of messages added
        """
        added = 0
        existing_ids = set()

        if deduplicate:
            # Build set of existing message signatures
            for msg in self.messages:
                sig = f"{msg.get('role')}:{msg.get('content', '')[:100]}"
                existing_ids.add(sig)

        for msg in other.messages:
            sig = f"{msg.get('role')}:{msg.get('content', '')[:100]}"
            if not deduplicate or sig not in existing_ids:
                self.messages.append(msg.copy())
                existing_ids.add(sig)
                added += 1

        return added
