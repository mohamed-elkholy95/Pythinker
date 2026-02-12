"""
Token management for context window handling.

Provides accurate token counting and intelligent message trimming
to stay within model context limits. Includes pressure monitoring
for proactive context management.
"""

import logging
from dataclasses import dataclass
from typing import Any, ClassVar

from app.domain.models.pressure import PressureLevel

logger = logging.getLogger(__name__)


@dataclass
class PressureStatus:
    """Status of context pressure with recommendations"""

    level: PressureLevel
    usage_percent: float
    current_tokens: int
    max_tokens: int
    available_tokens: int
    recommendations: list[str]

    def to_context_signal(self) -> str | None:
        """Generate context signal to inject into prompts"""
        if self.level == PressureLevel.NORMAL:
            return None

        signal_parts = [
            f"CONTEXT PRESSURE: {self.usage_percent:.0%} used ({self.current_tokens:,}/{self.max_tokens:,} tokens)."
        ]

        if self.recommendations:
            signal_parts.append("Consider:")
            signal_parts.extend(f"- {rec}" for rec in self.recommendations)

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

    Performance optimizations:
    - LRU cache for repeated token counts on identical content
    - Message-level caching with content hashing
    - Batch counting for message lists
    """

    # Approximate tokens per character for fallback estimation
    CHARS_PER_TOKEN = 4

    # Token overhead per message (role, separators, etc.)
    MESSAGE_OVERHEAD = 4

    # Context pressure thresholds (fraction of max tokens)
    # Research recommends 64-75% for early compaction (Anthropic 2025, ArXiv 2601.06007)
    # Priority 4: Optimized thresholds for better context utilization
    PRESSURE_THRESHOLDS: ClassVar[dict[str, float]] = {
        "early_warning": 0.60,  # 60% - early notice for planning
        "warning": 0.70,  # 70% - suggest planning for summarization
        "critical": 0.80,  # 80% - begin proactive trimming (raised from 0.70)
        "overflow": 0.90,  # 90% - force summarization (raised from 0.85)
    }

    # Default model context limits
    MODEL_LIMITS: ClassVar[dict[str, int]] = {
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
        "claude-sonnet": 200000,
        "claude-opus": 200000,
        "deepseek": 128000,  # DeepSeek V3.2 supports 128K context
        "gemini": 1000000,  # Gemini 2.5 Flash supports 1M tokens
        "gemini-flash": 1000000,
        "gemini-pro": 1000000,
        "qwen": 32768,  # Qwen models typically support 32K
        "llama": 128000,  # Llama 3 supports 128K
        "mistral": 32768,  # Mistral models
        "default": 32768,  # Increased default for modern models
    }

    # Safety margin (reserve tokens for response) — ensures completion buffer for final answers
    # Priority 4: Reduced from 4096 to 2048 (most responses under 2K tokens)
    # Can be overridden via config
    SAFETY_MARGIN = 2048  # Default, will use config value if available

    # Token count cache settings
    TOKEN_CACHE_MAX_SIZE = 1000  # Max cached entries
    TOKEN_CACHE_TTL = 300  # 5 minutes

    def __init__(
        self,
        model_name: str = "gpt-4",
        max_context_tokens: int | None = None,
        safety_margin: int | None = None,
        enable_cache: bool = True,
        session_id: str | None = None,
    ):
        """
        Initialize the token manager.

        Args:
            model_name: Name of the model for token counting
            max_context_tokens: Override for max context tokens
            safety_margin: Override for safety margin
            enable_cache: Enable token count caching (default: True)
            session_id: Optional session ID for logging/metrics context
        """
        self._model_name = model_name
        self._encoding = self._get_encoding(model_name)

        # Determine context limit
        self._max_tokens = max_context_tokens or self._get_model_limit(model_name)
        # Priority 4: Use config value for safety margin if not explicitly provided
        if safety_margin is None:
            from app.core.config import get_settings

            settings = get_settings()
            configured_margin = getattr(settings, "token_safety_margin", self.SAFETY_MARGIN)
            safety_margin = self.SAFETY_MARGIN if configured_margin is None else int(configured_margin)
        self._safety_margin = safety_margin
        self._effective_limit = self._max_tokens - self._safety_margin
        # Backward-compatible alias used by some tests/callers.
        self._max_effective_tokens = self._effective_limit

        # Token count cache (content_hash -> token_count)
        self._enable_cache = enable_cache
        self._token_cache: dict[str, int] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        # Phase 4 P1: Graceful compaction control
        self._compaction_allowed = True  # Gate for compaction timing
        self._session_id: str | None = session_id  # For logging context

        # Predictive context management: growth rate tracking
        self._growth_history: list[tuple[float, int]] = []  # (timestamp, token_count)
        self._max_growth_samples = 20  # Keep last 20 measurements
        self._prediction_horizon_steps = 3  # Predict 3 steps ahead
        self._default_growth_rate = 2000  # Default tokens per step if no history

        logger.info(
            f"TokenManager initialized for {model_name}: "
            f"max={self._max_tokens}, effective={self._effective_limit}, "
            f"cache={'enabled' if enable_cache else 'disabled'}"
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

    def _get_content_hash(self, text: str) -> str:
        """Generate a hash for content to use as cache key."""
        import hashlib

        return hashlib.md5(text.encode()).hexdigest()  # noqa: S324 - MD5 used for non-security cache key, not cryptographic

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in a text string.

        Uses LRU-style caching to avoid recounting identical content.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        if not text:
            return 0

        # Check cache first
        if self._enable_cache:
            cache_key = self._get_content_hash(text)
            if cache_key in self._token_cache:
                self._cache_hits += 1
                # Move to end for LRU ordering
                self._token_cache[cache_key] = self._token_cache.pop(cache_key)
                return self._token_cache[cache_key]
            self._cache_misses += 1

        # Count tokens
        count = len(self._encoding.encode(text)) if self._encoding else len(text) // self.CHARS_PER_TOKEN

        # Store in cache
        if self._enable_cache:
            self._token_cache[cache_key] = count
            # Evict single oldest entry (LRU) when cache is full
            if len(self._token_cache) > self.TOKEN_CACHE_MAX_SIZE:
                oldest_key = next(iter(self._token_cache))
                del self._token_cache[oldest_key]

        return count

    def count_message_tokens(self, message: dict[str, Any]) -> TokenCount:
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
            overhead_tokens=self.MESSAGE_OVERHEAD,
        )

    def count_messages_tokens(self, messages: list[dict[str, Any]]) -> int:
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

    def is_within_limit(self, messages: list[dict[str, Any]], buffer: int = 0) -> bool:
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
        self, messages: list[dict[str, Any]], preserve_system: bool = True, preserve_recent: int = 4
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Trim messages to fit within context limit.

        Preserves system prompts and recent messages, removing older
        messages from the middle. Ensures tool_call/tool_response pairs
        are kept together to maintain valid message sequences.

        If system + recent messages exceed the limit, dynamically reduces
        preserve_recent to fit within available space.

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

        logger.warning(f"Context ({total_tokens} tokens) exceeds limit ({self._effective_limit}). Trimming messages...")

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

        # Calculate system tokens (fixed overhead we can't reduce)
        system_tokens = sum(self.count_message_tokens(m).total for group in system_groups for _, m in group)

        # Check if system alone exceeds limit (edge case - can't do much here)
        if system_tokens >= self._effective_limit:
            logger.error(f"System messages alone ({system_tokens} tokens) exceed limit ({self._effective_limit})")
            # Keep only system messages as a last resort
            all_kept = [msg for group in system_groups for msg in group]
            all_kept.sort(key=lambda x: x[0])
            trimmed_messages = [msg for _, msg in all_kept]
            return trimmed_messages, total_tokens - self.count_messages_tokens(trimmed_messages)

        # Available tokens for non-system messages
        available_for_others = self._effective_limit - system_tokens

        # Dynamically adjust preserve_recent if we need to
        # Start with requested preserve_recent and reduce if necessary
        actual_preserve_recent = preserve_recent
        recent_groups: list[list[tuple[int, dict[str, Any]]]] = []
        trimmable_groups: list[list[tuple[int, dict[str, Any]]]] = []
        available_tokens = 0
        preserve_reduction_steps = 0
        recent_tokens = 0

        while actual_preserve_recent >= 0:
            # Preserve recent groups (count by original message count)
            recent_msg_count = 0
            recent_groups = []
            for group in reversed(other_groups):
                group_msg_count = len(group)
                if recent_msg_count + group_msg_count <= actual_preserve_recent:
                    recent_groups.insert(0, group)
                    recent_msg_count += group_msg_count
                elif recent_msg_count > 0 and self._group_contains_tool_sequence(group):
                    # Pair-aware guard: if we are at the preserve boundary and the next
                    # group is a tool sequence, include it atomically to avoid cutting
                    # assistant/tool context apart.
                    recent_groups.insert(0, group)
                    recent_msg_count += group_msg_count
                    break
                else:
                    break

            trimmable_groups = other_groups[: len(other_groups) - len(recent_groups)] if recent_groups else other_groups

            # Calculate recent tokens
            recent_tokens = sum(self.count_message_tokens(m).total for group in recent_groups for _, m in group)

            # Calculate available tokens for trimmable groups
            available_tokens = available_for_others - recent_tokens

            if available_tokens >= 0:
                # We have room - this configuration works
                break

            # Recent messages alone exceed available space - reduce preserve_recent
            preserve_reduction_steps += 1
            actual_preserve_recent -= 1

        if preserve_reduction_steps > 0:
            logger.warning(
                "Reduced preserve_recent from %d to %d during compaction (recent=%d tokens, available=%d tokens)",
                preserve_recent,
                max(actual_preserve_recent, 0),
                recent_tokens,
                available_for_others,
            )

        # If we had to reduce preserve_recent below 0, something is very wrong
        if actual_preserve_recent < 0:
            logger.error("Cannot fit any messages - keeping only system messages")
            recent_groups = []
            trimmable_groups = other_groups
            available_tokens = available_for_others

        # Trim from oldest trimmable groups (keep groups intact)
        # Iterate from newest to oldest, keeping as many as fit
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

        # Validate: remove orphaned tool responses whose assistant tool_call was trimmed
        trimmed_messages = self._remove_orphaned_tool_responses(trimmed_messages)

        tokens_removed = total_tokens - self.count_messages_tokens(trimmed_messages)

        logger.info(
            f"Trimmed {len(messages) - len(trimmed_messages)} messages ({tokens_removed} tokens), "
            f"preserve_recent: {preserve_recent} -> {actual_preserve_recent}"
        )

        return trimmed_messages, tokens_removed

    def _remove_orphaned_tool_responses(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove tool responses whose parent assistant tool_call is missing.

        Also removes assistant messages with tool_calls that have no
        corresponding tool responses (reverse orphans that break strict APIs).
        """
        # Collect all tool_call IDs from assistant messages
        valid_tool_call_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id")
                    if tc_id:
                        valid_tool_call_ids.add(tc_id)

        # Collect all tool_call_ids that have actual tool responses
        responded_tool_call_ids: set[str] = set()
        for msg in messages:
            if msg.get("role") == "tool":
                tcid = msg.get("tool_call_id")
                if tcid:
                    responded_tool_call_ids.add(tcid)

        # Filter out tool responses that reference missing tool_calls
        cleaned = []
        orphan_count = 0
        for msg in messages:
            if msg.get("role") == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id and tool_call_id not in valid_tool_call_ids:
                    orphan_count += 1
                    continue
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Remove tool_call entries that have no matching response
                original_calls = msg["tool_calls"]
                kept_calls = [tc for tc in original_calls if tc.get("id") in responded_tool_call_ids]
                if len(kept_calls) < len(original_calls):
                    orphan_count += len(original_calls) - len(kept_calls)
                    if kept_calls:
                        msg = {**msg, "tool_calls": [dict(tc) for tc in kept_calls]}
                    else:
                        # All tool_calls lost their responses — strip tool_calls
                        msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                        # If the message has no content either, skip it entirely
                        if not msg.get("content"):
                            orphan_count += 1
                            continue
            cleaned.append(msg)

        if orphan_count > 0:
            logger.warning(f"Removed {orphan_count} orphaned tool messages during trimming")

        return cleaned

    @staticmethod
    def _group_contains_tool_sequence(group: list[tuple[int, dict[str, Any]]]) -> bool:
        """Return True when a message group contains tool-call sequencing."""
        for _, msg in group:
            if msg.get("role") == "tool":
                return True
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                return True
        return False

    def _group_tool_messages(self, messages: list[dict[str, Any]]) -> list[list[tuple[int, dict[str, Any]]]]:
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
                pending_tool_call_ids = {tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")}
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

    def get_stats(self) -> dict[str, Any]:
        """Get token manager statistics including cache performance."""
        cache_total = self._cache_hits + self._cache_misses
        cache_hit_rate = self._cache_hits / cache_total if cache_total > 0 else 0.0

        return {
            "model": self._model_name,
            "max_tokens": self._max_tokens,
            "safety_margin": self._safety_margin,
            "effective_limit": self._effective_limit,
            "tiktoken_available": TIKTOKEN_AVAILABLE,
            "cache": {
                "enabled": self._enable_cache,
                "size": len(self._token_cache),
                "max_size": self.TOKEN_CACHE_MAX_SIZE,
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": round(cache_hit_rate, 4),
            },
        }

    def clear_cache(self) -> int:
        """Clear the token count cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._token_cache)
        self._token_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.debug(f"Token cache cleared ({count} entries)")
        return count

    def get_context_pressure(self, messages: list[dict[str, Any]]) -> PressureStatus:
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

        level = self._pressure_level_for_usage(usage_ratio)

        # Generate recommendations based on level
        recommendations = self._get_pressure_recommendations(level, usage_ratio)

        return PressureStatus(
            level=level,
            usage_percent=usage_ratio,
            current_tokens=current_tokens,
            max_tokens=self._effective_limit,
            available_tokens=available,
            recommendations=recommendations,
        )

    def _pressure_level_for_usage(self, usage_ratio: float) -> PressureLevel:
        """Map a usage ratio to a canonical pressure level."""
        if usage_ratio >= self.PRESSURE_THRESHOLDS["overflow"]:
            return PressureLevel.OVERFLOW
        if usage_ratio >= self.PRESSURE_THRESHOLDS["critical"]:
            return PressureLevel.CRITICAL
        if usage_ratio >= self.PRESSURE_THRESHOLDS["warning"]:
            return PressureLevel.WARNING
        if usage_ratio >= self.PRESSURE_THRESHOLDS["early_warning"]:
            return PressureLevel.EARLY_WARNING
        return PressureLevel.NORMAL

    def _get_pressure_recommendations(self, level: PressureLevel, usage_ratio: float) -> list[str]:
        """Generate recommendations based on pressure level"""
        if level == PressureLevel.NORMAL:
            return []

        recommendations = []

        if level == PressureLevel.WARNING:
            recommendations = [
                "Summarizing completed work to save tokens",
                "Saving detailed findings to files for reference",
                "Focusing on remaining essential steps",
            ]
        elif level == PressureLevel.CRITICAL:
            recommendations = [
                "Immediately save important findings to files",
                "Complete current step and summarize progress",
                "Remove verbose tool outputs from context",
            ]
        elif level == PressureLevel.OVERFLOW:
            recommendations = [
                "URGENT: Context overflow imminent",
                "Force-save all critical data to files NOW",
                "Aggressive context trimming will occur",
            ]

        return recommendations

    def should_trigger_compaction(self, messages: list[dict[str, Any]]) -> bool:
        """Check if context pressure warrants compaction"""
        pressure = self.get_context_pressure(messages)
        return pressure.level in (PressureLevel.CRITICAL, PressureLevel.OVERFLOW)

    # Predictive Context Management Methods

    def track_token_snapshot(self, messages: list[dict[str, Any]]) -> None:
        """Track token count at a point in time for growth rate analysis.

        Call this after each LLM interaction to build growth history
        for predictive pressure estimation.

        Args:
            messages: Current conversation messages
        """
        import time

        current_tokens = self.count_messages_tokens(messages)
        timestamp = time.time()

        self._growth_history.append((timestamp, current_tokens))

        # Keep only recent samples
        if len(self._growth_history) > self._max_growth_samples:
            self._growth_history = self._growth_history[-self._max_growth_samples :]

        logger.debug(f"Token snapshot: {current_tokens:,} tokens (history size: {len(self._growth_history)})")

    def estimate_growth_rate(self) -> float:
        """Estimate tokens added per step based on history.

        Analyzes the growth history to determine average token
        consumption rate per interaction/step.

        Returns:
            Average tokens per step, or default estimate if insufficient data
        """
        if len(self._growth_history) < 2:
            return self._default_growth_rate

        # Calculate deltas between consecutive snapshots
        deltas = []
        for i in range(1, len(self._growth_history)):
            prev_tokens = self._growth_history[i - 1][1]
            curr_tokens = self._growth_history[i][1]
            delta = curr_tokens - prev_tokens

            # Only include positive growth (ignore compaction/trimming)
            if delta > 0:
                deltas.append(delta)

        if not deltas:
            return self._default_growth_rate

        return sum(deltas) / len(deltas)

    def predict_pressure(
        self,
        messages: list[dict[str, Any]],
        steps_ahead: int | None = None,
    ) -> PressureStatus:
        """Predict future context pressure.

        Estimates what the context pressure will be after a number
        of additional steps, helping enable proactive compression.

        Args:
            messages: Current messages
            steps_ahead: Steps to predict ahead (default: 3)

        Returns:
            Predicted PressureStatus
        """
        steps = steps_ahead or self._prediction_horizon_steps
        current_tokens = self.count_messages_tokens(messages)
        growth_rate = self.estimate_growth_rate()

        predicted_tokens = current_tokens + int(growth_rate * steps)
        predicted_ratio = predicted_tokens / self._effective_limit

        # Determine predicted level (Priority 4: added EARLY_WARNING threshold)
        if predicted_ratio >= self.PRESSURE_THRESHOLDS["overflow"]:
            level = PressureLevel.OVERFLOW
        elif predicted_ratio >= self.PRESSURE_THRESHOLDS["critical"]:
            level = PressureLevel.CRITICAL
        elif predicted_ratio >= self.PRESSURE_THRESHOLDS["warning"]:
            level = PressureLevel.WARNING
        elif predicted_ratio >= self.PRESSURE_THRESHOLDS["early_warning"]:
            level = PressureLevel.EARLY_WARNING
        else:
            level = PressureLevel.NORMAL

        # Priority 4: Log and emit metrics for early warning and higher
        if level in (
            PressureLevel.EARLY_WARNING,
            PressureLevel.WARNING,
            PressureLevel.CRITICAL,
            PressureLevel.OVERFLOW,
        ):
            logger.warning(
                f"Token pressure: {level.value} ({predicted_ratio:.1%}) - "
                f"{predicted_tokens:,}/{self._effective_limit:,} tokens, "
                f"growth: ~{int(growth_rate):,} tokens/step"
            )

        # Generate predictive recommendations
        recommendations = self._get_predictive_recommendations(level, predicted_ratio, steps, growth_rate)

        return PressureStatus(
            level=level,
            usage_percent=predicted_ratio,
            current_tokens=predicted_tokens,
            max_tokens=self._effective_limit,
            available_tokens=max(0, self._effective_limit - predicted_tokens),
            recommendations=recommendations,
        )

    def _get_predictive_recommendations(
        self,
        level: PressureLevel,
        predicted_ratio: float,
        steps_ahead: int,
        growth_rate: float,
    ) -> list[str]:
        """Generate recommendations based on predicted pressure."""
        if level == PressureLevel.NORMAL:
            return []

        recommendations = [
            f"Predicted {predicted_ratio:.0%} usage in {steps_ahead} steps (growth rate: ~{int(growth_rate):,} tokens/step)"
        ]

        if level == PressureLevel.WARNING:
            recommendations.append("Consider summarizing completed steps soon")
            recommendations.append("Save verbose outputs to files")
        elif level == PressureLevel.CRITICAL:
            recommendations.append("Summarize now to avoid forced trimming")
            recommendations.append("Save important findings to files immediately")
        elif level == PressureLevel.OVERFLOW:
            recommendations.append("URGENT: Summarize immediately")
            recommendations.append("Context overflow predicted - action required now")

        return recommendations

    def should_trigger_proactive_compression(self, messages: list[dict[str, Any]]) -> bool:
        """Check if proactive compression should be triggered.

        Uses prediction to trigger compression BEFORE hitting critical pressure,
        allowing for more graceful context management.

        Args:
            messages: Current messages

        Returns:
            True if proactive compression is recommended
        """
        # Check current pressure first
        current = self.get_context_pressure(messages)
        if current.level in (PressureLevel.CRITICAL, PressureLevel.OVERFLOW):
            return True

        # Check predicted pressure
        predicted = self.predict_pressure(messages)

        # Trigger proactive compression if predicted to hit critical/overflow
        return predicted.level in (PressureLevel.CRITICAL, PressureLevel.OVERFLOW)

    def get_growth_stats(self) -> dict[str, Any]:
        """Get growth tracking statistics.

        Returns:
            Dict with growth rate, history size, and prediction info
        """
        growth_rate = self.estimate_growth_rate()
        steps_to_warning = None
        steps_to_critical = None

        if self._growth_history and growth_rate > 0:
            current_tokens = self._growth_history[-1][1] if self._growth_history else 0

            # Calculate steps until thresholds
            warning_threshold = self.PRESSURE_THRESHOLDS["warning"]
            critical_threshold = self.PRESSURE_THRESHOLDS["critical"]

            tokens_to_warning = (warning_threshold * self._effective_limit) - current_tokens
            tokens_to_critical = (critical_threshold * self._effective_limit) - current_tokens

            if tokens_to_warning > 0:
                steps_to_warning = int(tokens_to_warning / growth_rate)
            if tokens_to_critical > 0:
                steps_to_critical = int(tokens_to_critical / growth_rate)

        return {
            "growth_rate_tokens_per_step": int(growth_rate),
            "history_size": len(self._growth_history),
            "steps_to_warning": steps_to_warning,
            "steps_to_critical": steps_to_critical,
            "prediction_horizon": self._prediction_horizon_steps,
        }

    def mark_step_executing(self) -> None:
        """Mark that an execution step is starting (Phase 4 P1).

        Disables compaction during execution to prevent quality degradation.
        """
        self._compaction_allowed = False
        logger.debug("Compaction disabled during execution step", extra={"session_id": self._session_id})

    def mark_step_completed(self) -> None:
        """Mark that an execution step has completed (Phase 4 P1).

        Re-enables compaction after step completion.
        """
        self._compaction_allowed = True
        logger.debug("Compaction re-enabled after step completion", extra={"session_id": self._session_id})

    def set_session_id(self, session_id: str) -> None:
        """Set session ID for logging context (Phase 4 P1)."""
        self._session_id = session_id

    def check_pressure(self, messages: list[dict[str, Any]] | int) -> PressureStatus | PressureLevel:
        """Check token pressure and log metrics (Phase 4 P1).

        Args:
            messages: List of messages to check, or raw token count for compatibility

        Returns:
            PressureStatus with current pressure information, or PressureLevel when
            called with a raw integer token count.
        """
        if isinstance(messages, int):
            usage_ratio = messages / self._effective_limit if self._effective_limit > 0 else 1.0
            return self._pressure_level_for_usage(usage_ratio)

        status = self.get_context_pressure(messages)

        # Record metric via domain port
        from app.domain.external.observability import get_metrics

        metrics = get_metrics()
        metrics.update_token_budget(
            used=status.current_tokens,
            remaining=status.available_tokens,
        )

        # Log critical pressure
        if status.level == PressureLevel.CRITICAL:
            if self._compaction_allowed:
                logger.warning(
                    "Token pressure critical - compaction recommended",
                    extra={
                        "session_id": self._session_id,
                        "usage_percent": status.usage_percent,
                        "current_tokens": status.current_tokens,
                        "max_tokens": status.max_tokens,
                    },
                )
            else:
                logger.warning(
                    "Token pressure critical - waiting for step completion",
                    extra={
                        "session_id": self._session_id,
                        "usage_percent": status.usage_percent,
                        "current_tokens": status.current_tokens,
                        "max_tokens": status.max_tokens,
                    },
                )

        return status

    def compact_if_needed(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Perform compaction if needed and allowed (Phase 4 P1).

        Args:
            messages: Messages to potentially compact

        Returns:
            Compacted messages or original if compaction not allowed
        """
        # Check if compaction is safe
        if not self._compaction_allowed:
            # Check pressure level — OVERFLOW should be visible even when compaction is deferred
            pressure = self.get_context_pressure(messages)
            if pressure.level == PressureLevel.OVERFLOW:
                logger.warning(
                    "Context at OVERFLOW pressure but compaction deferred — "
                    f"usage={pressure.usage_percent:.0%}, tokens={pressure.current_tokens}/{pressure.max_tokens}",
                    extra={"session_id": self._session_id},
                )
            else:
                logger.debug("Compaction deferred - execution in progress", extra={"session_id": self._session_id})
            return messages

        # Check if compaction is needed
        if not self.should_trigger_compaction(messages):
            return messages

        # Proceed with compaction
        logger.info(
            "Performing context compaction",
            extra={
                "session_id": self._session_id,
                "message_count": len(messages),
            },
        )

        # Use existing trim_messages method
        compacted, _ = self.trim_messages(messages)

        logger.info(
            "Context compaction completed",
            extra={
                "session_id": self._session_id,
                "original_count": len(messages),
                "compacted_count": len(compacted),
            },
        )

        return compacted
