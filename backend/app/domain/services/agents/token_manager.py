"""
Token management for context window handling.

Provides accurate token counting and intelligent message trimming
to stay within model context limits. Includes pressure monitoring
for proactive context management.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PressureLevel(str, Enum):
    """Context pressure levels for proactive management"""
    NORMAL = "normal"      # < 75% - operating normally
    WARNING = "warning"    # 75-85% - consider summarizing
    CRITICAL = "critical"  # 85-95% - begin proactive trimming
    OVERFLOW = "overflow"  # > 95% - force immediate action


@dataclass
class PressureStatus:
    """Status of context pressure with recommendations"""
    level: PressureLevel
    usage_percent: float
    current_tokens: int
    max_tokens: int
    available_tokens: int
    recommendations: List[str]

    def to_context_signal(self) -> Optional[str]:
        """Generate context signal to inject into prompts"""
        if self.level == PressureLevel.NORMAL:
            return None

        signal_parts = [
            f"CONTEXT PRESSURE: {self.usage_percent:.0%} used ({self.current_tokens:,}/{self.max_tokens:,} tokens)."
        ]

        if self.recommendations:
            signal_parts.append("Consider:")
            for rec in self.recommendations:
                signal_parts.append(f"- {rec}")

        return "\n".join(signal_parts)

# Try to import tiktoken for accurate counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not available, using approximate token counting")


@dataclass
class TokenCount:
    """Token count breakdown for a message or conversation"""
    total: int
    content_tokens: int
    tool_tokens: int
    overhead_tokens: int


class TokenManager:
    """
    Manages token counting and context trimming for LLM interactions.

    Uses tiktoken for accurate counting when available, falls back to
    approximate counting otherwise. Includes pressure monitoring for
    proactive context management.
    """

    # Approximate tokens per character for fallback estimation
    CHARS_PER_TOKEN = 4

    # Token overhead per message (role, separators, etc.)
    MESSAGE_OVERHEAD = 4

    # Context pressure thresholds (fraction of max tokens)
    PRESSURE_THRESHOLDS = {
        "warning": 0.75,   # 75% - suggest planning for summarization
        "critical": 0.85,  # 85% - begin proactive trimming
        "overflow": 0.95,  # 95% - force summarization
    }

    # Default model context limits
    MODEL_LIMITS = {
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-5": 128000,
        "gpt-5.2": 128000,
        "gpt-5-nano": 128000,
        "gpt-5-mini": 128000,
        "o1": 128000,
        "o1-mini": 128000,
        "o3-mini": 128000,
        "claude-3": 200000,
        "default": 8192
    }

    # Safety margin (reserve tokens for response) - reduced from 4096 for better context utilization
    SAFETY_MARGIN = 2048

    def __init__(
        self,
        model_name: str = "gpt-4",
        max_context_tokens: Optional[int] = None,
        safety_margin: Optional[int] = None
    ):
        """
        Initialize the token manager.

        Args:
            model_name: Name of the model for token counting
            max_context_tokens: Override for max context tokens
            safety_margin: Override for safety margin
        """
        self._model_name = model_name
        self._encoding = self._get_encoding(model_name)

        # Determine context limit
        self._max_tokens = max_context_tokens or self._get_model_limit(model_name)
        self._safety_margin = safety_margin or self.SAFETY_MARGIN
        self._effective_limit = self._max_tokens - self._safety_margin

        logger.info(
            f"TokenManager initialized for {model_name}: "
            f"max={self._max_tokens}, effective={self._effective_limit}"
        )

    def _get_encoding(self, model_name: str):
        """Get tiktoken encoding for the model"""
        if not TIKTOKEN_AVAILABLE:
            return None

        try:
            # Try to get encoding for specific model
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fall back to cl100k_base (used by GPT-4, GPT-3.5-turbo)
            return tiktoken.get_encoding("cl100k_base")

    def _get_model_limit(self, model_name: str) -> int:
        """Get context limit for a model"""
        model_lower = model_name.lower()

        for key, limit in self.MODEL_LIMITS.items():
            if key in model_lower:
                return limit

        return self.MODEL_LIMITS["default"]

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        if not text:
            return 0

        if self._encoding:
            return len(self._encoding.encode(text))

        # Fallback: approximate by character count
        return len(text) // self.CHARS_PER_TOKEN

    def count_message_tokens(self, message: Dict[str, Any]) -> TokenCount:
        """
        Count tokens in a single message.

        Args:
            message: Message dict with role, content, etc.

        Returns:
            TokenCount with breakdown
        """
        content_tokens = 0
        tool_tokens = 0

        # Count content
        content = message.get("content", "")
        if content:
            if isinstance(content, str):
                content_tokens = self.count_tokens(content)
            elif isinstance(content, list):
                # Handle content array (multimodal)
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        content_tokens += self.count_tokens(item["text"])

        # Count tool calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_tokens += self.count_tokens(func.get("name", ""))
                tool_tokens += self.count_tokens(func.get("arguments", ""))

        # Tool responses
        if message.get("role") == "tool":
            tool_tokens += self.count_tokens(message.get("function_name", ""))
            tool_tokens += self.count_tokens(message.get("tool_call_id", ""))

        return TokenCount(
            total=content_tokens + tool_tokens + self.MESSAGE_OVERHEAD,
            content_tokens=content_tokens,
            tool_tokens=tool_tokens,
            overhead_tokens=self.MESSAGE_OVERHEAD
        )

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Count total tokens across all messages.

        Args:
            messages: List of message dicts

        Returns:
            Total token count
        """
        total = 0
        for msg in messages:
            count = self.count_message_tokens(msg)
            total += count.total

        # Add base overhead for the conversation
        total += 3  # Every reply is primed with <|start|>assistant<|message|>

        return total

    def is_within_limit(self, messages: List[Dict[str, Any]], buffer: int = 0) -> bool:
        """
        Check if messages are within the context limit.

        Args:
            messages: List of message dicts
            buffer: Additional buffer tokens to reserve

        Returns:
            True if within limit
        """
        total_tokens = self.count_messages_tokens(messages)
        limit = self._effective_limit - buffer
        return total_tokens <= limit

    def trim_messages(
        self,
        messages: List[Dict[str, Any]],
        preserve_system: bool = True,
        preserve_recent: int = 4
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Trim messages to fit within context limit.

        Preserves system prompts and recent messages, removing older
        messages from the middle. Ensures tool_call/tool_response pairs
        are kept together to maintain valid message sequences.

        Args:
            messages: List of message dicts
            preserve_system: Keep system messages at start
            preserve_recent: Number of recent messages to always keep

        Returns:
            Tuple of (trimmed messages, tokens removed)
        """
        if not messages:
            return [], 0

        total_tokens = self.count_messages_tokens(messages)

        if total_tokens <= self._effective_limit:
            return messages, 0

        logger.warning(
            f"Context ({total_tokens} tokens) exceeds limit ({self._effective_limit}). "
            "Trimming messages..."
        )

        # Group messages: tool_calls must stay with their tool responses
        message_groups = self._group_tool_messages(messages)

        # Separate groups into categories
        system_groups = []
        other_groups = []

        for group in message_groups:
            first_msg = group[0][1]
            if first_msg.get("role") == "system" and preserve_system:
                system_groups.append(group)
            else:
                other_groups.append(group)

        # Preserve recent groups (count by original message count)
        recent_msg_count = 0
        recent_groups = []
        for group in reversed(other_groups):
            group_msg_count = len(group)
            if recent_msg_count + group_msg_count <= preserve_recent:
                recent_groups.insert(0, group)
                recent_msg_count += group_msg_count
            else:
                break

        trimmable_groups = other_groups[:len(other_groups) - len(recent_groups)] if recent_groups else other_groups

        # Calculate tokens we need to remove
        system_tokens = sum(
            self.count_message_tokens(m).total
            for group in system_groups for _, m in group
        )
        recent_tokens = sum(
            self.count_message_tokens(m).total
            for group in recent_groups for _, m in group
        )
        available_tokens = self._effective_limit - system_tokens - recent_tokens

        # Trim from oldest trimmable groups (keep groups intact)
        kept_groups = []
        kept_tokens = 0

        for group in reversed(trimmable_groups):
            group_tokens = sum(self.count_message_tokens(m).total for _, m in group)
            if kept_tokens + group_tokens <= available_tokens:
                kept_groups.insert(0, group)
                kept_tokens += group_tokens

        # Reconstruct message list
        all_kept_groups = system_groups + kept_groups + recent_groups
        all_kept = [msg for group in all_kept_groups for msg in group]
        all_kept.sort(key=lambda x: x[0])  # Restore original order

        trimmed_messages = [msg for _, msg in all_kept]
        tokens_removed = total_tokens - self.count_messages_tokens(trimmed_messages)

        logger.info(f"Trimmed {len(messages) - len(trimmed_messages)} messages ({tokens_removed} tokens)")

        return trimmed_messages, tokens_removed

    def _group_tool_messages(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[List[Tuple[int, Dict[str, Any]]]]:
        """
        Group messages so tool_calls stay with their tool responses.

        An assistant message with tool_calls must be followed by all its
        tool responses before the next user/assistant message.

        Returns:
            List of message groups, where each group is a list of (index, message) tuples
        """
        groups = []
        current_group = []
        pending_tool_call_ids = set()

        for i, msg in enumerate(messages):
            role = msg.get("role", "")

            if role == "assistant" and msg.get("tool_calls"):
                # Start new group with assistant message that has tool_calls
                if current_group:
                    groups.append(current_group)
                current_group = [(i, msg)]
                # Track expected tool responses
                pending_tool_call_ids = {
                    tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")
                }
            elif role == "tool":
                # Add tool response to current group
                current_group.append((i, msg))
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id in pending_tool_call_ids:
                    pending_tool_call_ids.discard(tool_call_id)
                # If all tool responses received, close the group
                if not pending_tool_call_ids and current_group:
                    groups.append(current_group)
                    current_group = []
            else:
                # Regular message - close current group and start new one
                if current_group:
                    groups.append(current_group)
                current_group = [(i, msg)]
                groups.append(current_group)
                current_group = []
                pending_tool_call_ids = set()

        # Don't forget the last group
        if current_group:
            groups.append(current_group)

        return groups

    def estimate_response_tokens(self, prompt_tokens: int) -> int:
        """
        Estimate available tokens for response.

        Args:
            prompt_tokens: Tokens used by the prompt

        Returns:
            Estimated tokens available for response
        """
        return max(0, self._max_tokens - prompt_tokens - 100)  # 100 token buffer

    def get_stats(self) -> Dict[str, Any]:
        """Get token manager statistics"""
        return {
            "model": self._model_name,
            "max_tokens": self._max_tokens,
            "safety_margin": self._safety_margin,
            "effective_limit": self._effective_limit,
            "tiktoken_available": TIKTOKEN_AVAILABLE
        }

    def get_context_pressure(
        self,
        messages: List[Dict[str, Any]]
    ) -> PressureStatus:
        """
        Get current context pressure status with recommendations.

        Analyzes current token usage and provides actionable guidance
        for managing context before it overflows.

        Args:
            messages: Current conversation messages

        Returns:
            PressureStatus with level, metrics, and recommendations
        """
        current_tokens = self.count_messages_tokens(messages)
        usage_ratio = current_tokens / self._effective_limit
        available = self._effective_limit - current_tokens

        # Determine pressure level
        if usage_ratio >= self.PRESSURE_THRESHOLDS["overflow"]:
            level = PressureLevel.OVERFLOW
        elif usage_ratio >= self.PRESSURE_THRESHOLDS["critical"]:
            level = PressureLevel.CRITICAL
        elif usage_ratio >= self.PRESSURE_THRESHOLDS["warning"]:
            level = PressureLevel.WARNING
        else:
            level = PressureLevel.NORMAL

        # Generate recommendations based on level
        recommendations = self._get_pressure_recommendations(level, usage_ratio)

        return PressureStatus(
            level=level,
            usage_percent=usage_ratio,
            current_tokens=current_tokens,
            max_tokens=self._effective_limit,
            available_tokens=available,
            recommendations=recommendations
        )

    def _get_pressure_recommendations(
        self,
        level: PressureLevel,
        usage_ratio: float
    ) -> List[str]:
        """Generate recommendations based on pressure level"""
        if level == PressureLevel.NORMAL:
            return []

        recommendations = []

        if level == PressureLevel.WARNING:
            recommendations = [
                "Summarizing completed work to save tokens",
                "Saving detailed findings to files for reference",
                "Focusing on remaining essential steps"
            ]
        elif level == PressureLevel.CRITICAL:
            recommendations = [
                "Immediately save important findings to files",
                "Complete current step and summarize progress",
                "Remove verbose tool outputs from context"
            ]
        elif level == PressureLevel.OVERFLOW:
            recommendations = [
                "URGENT: Context overflow imminent",
                "Force-save all critical data to files NOW",
                "Aggressive context trimming will occur"
            ]

        return recommendations

    def should_trigger_compaction(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if context pressure warrants compaction"""
        pressure = self.get_context_pressure(messages)
        return pressure.level in (PressureLevel.CRITICAL, PressureLevel.OVERFLOW)
