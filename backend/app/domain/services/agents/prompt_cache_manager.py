"""
Prompt cache management for KV-cache optimization.

Implements caching strategies for both OpenAI and Anthropic APIs
to reduce token costs by ~90% on repeated system prompts.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers with caching capabilities"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    UNKNOWN = "unknown"


@dataclass
class CacheMetrics:
    """Metrics for cache performance tracking"""
    cache_hits: int = 0
    cache_misses: int = 0
    tokens_saved: int = 0
    total_requests: int = 0

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.cache_hits / self.total_requests

    def record_hit(self, tokens: int = 0) -> None:
        self.cache_hits += 1
        self.total_requests += 1
        self.tokens_saved += tokens

    def record_miss(self) -> None:
        self.cache_misses += 1
        self.total_requests += 1


@dataclass
class PromptSection:
    """A section of the prompt with caching metadata"""
    content: str
    cacheable: bool = True
    stable: bool = True  # Whether content changes between requests
    section_id: str = ""

    @property
    def hash(self) -> str:
        return hashlib.md5(self.content.encode(), usedforsecurity=False).hexdigest()[:12]


class PromptCacheManager:
    """
    Manages prompt caching for LLM API calls.

    Separates system prompts into cacheable prefix (stable) and
    dynamic suffix (changes per request) to maximize KV-cache hits.

    OpenAI: Uses automatic prefix caching (no explicit markers needed,
            but structuring prompts correctly improves hit rate)
    Anthropic: Uses cache_control markers with ephemeral type
    """

    def __init__(self, provider: str = "openai"):
        """
        Initialize the cache manager.

        Args:
            provider: LLM provider name (openai, anthropic, etc.)
        """
        self._provider = self._detect_provider(provider)
        self._metrics = CacheMetrics()
        self._prompt_versions: Dict[str, str] = {}
        self._cached_prefix_hash: Optional[str] = None
        logger.info(f"PromptCacheManager initialized for provider: {self._provider.value}")

    def _detect_provider(self, provider_name: str) -> LLMProvider:
        """Detect LLM provider from model/API name"""
        provider_lower = provider_name.lower()

        if any(term in provider_lower for term in ['openai', 'gpt', 'o1', 'o3']):
            return LLMProvider.OPENAI
        elif any(term in provider_lower for term in ['anthropic', 'claude']):
            return LLMProvider.ANTHROPIC
        else:
            return LLMProvider.UNKNOWN

    def prepare_messages_for_caching(
        self,
        messages: List[Dict[str, Any]],
        dynamic_content: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Prepare messages with optimal structure for caching.

        Args:
            messages: Original message list
            dynamic_content: Optional dynamic content to append

        Returns:
            Messages structured for optimal cache performance
        """
        if self._provider == LLMProvider.ANTHROPIC:
            return self._prepare_anthropic_caching(messages, dynamic_content)
        elif self._provider == LLMProvider.OPENAI:
            return self._prepare_openai_caching(messages, dynamic_content)
        else:
            return messages

    def _prepare_openai_caching(
        self,
        messages: List[Dict[str, Any]],
        dynamic_content: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Prepare messages for OpenAI automatic prefix caching.

        OpenAI automatically caches identical prefixes. To maximize hits:
        1. Keep system message first and stable
        2. Minimize changes to early messages
        3. Put dynamic content at the end

        Note: For explicit cache control, use structured system messages
        with stable prefix + dynamic suffix pattern.
        """
        if not messages:
            return messages

        optimized = []
        system_messages = []
        other_messages = []

        for msg in messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        # Combine system messages into single cacheable block
        if system_messages:
            combined_system = "\n\n".join(
                msg.get("content", "") for msg in system_messages
            )

            if dynamic_content:
                # Separate stable prefix from dynamic suffix
                system_msg = {
                    "role": "system",
                    "content": combined_system + "\n\n---\n\n" + dynamic_content
                }
            else:
                system_msg = {"role": "system", "content": combined_system}

            optimized.append(system_msg)
            self._update_prefix_hash(combined_system)

        optimized.extend(other_messages)

        return optimized

    def _prepare_anthropic_caching(
        self,
        messages: List[Dict[str, Any]],
        dynamic_content: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Prepare messages for Anthropic cache_control API.

        Uses cache_control: {"type": "ephemeral"} markers on
        cacheable content blocks.
        """
        if not messages:
            return messages

        optimized = []

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Mark system prompt as cacheable
                if dynamic_content and i == 0:
                    # Split into cacheable prefix + dynamic suffix
                    optimized.append({
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": {"type": "ephemeral"}
                            },
                            {
                                "type": "text",
                                "text": dynamic_content
                            }
                        ]
                    })
                else:
                    optimized.append({
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    })
                self._update_prefix_hash(content)
            else:
                # Keep other messages as-is
                optimized.append(msg)

        return optimized

    def _update_prefix_hash(self, content: str) -> None:
        """Update cached prefix hash and track metrics"""
        new_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()

        if self._cached_prefix_hash == new_hash:
            self._metrics.record_hit(tokens=len(content) // 4)  # Approximate
        else:
            self._metrics.record_miss()
            self._cached_prefix_hash = new_hash

    def split_prompt(
        self,
        full_prompt: str,
        dynamic_sections: Optional[List[str]] = None
    ) -> Tuple[str, str]:
        """
        Split a prompt into cacheable prefix and dynamic suffix.

        Args:
            full_prompt: Complete prompt text
            dynamic_sections: List of section identifiers to treat as dynamic

        Returns:
            Tuple of (cacheable_prefix, dynamic_suffix)
        """
        if not dynamic_sections:
            return full_prompt, ""

        lines = full_prompt.split('\n')
        prefix_lines = []
        suffix_lines = []
        in_dynamic = False

        for line in lines:
            if any(section in line for section in dynamic_sections):
                in_dynamic = True

            if in_dynamic:
                suffix_lines.append(line)
            else:
                prefix_lines.append(line)

        return '\n'.join(prefix_lines), '\n'.join(suffix_lines)

    def track_prompt_version(self, prompt_id: str, content: str) -> bool:
        """
        Track prompt version for cache invalidation detection.

        Args:
            prompt_id: Identifier for the prompt
            content: Current prompt content

        Returns:
            True if content changed (cache invalidated)
        """
        content_hash = hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()
        previous_hash = self._prompt_versions.get(prompt_id)

        self._prompt_versions[prompt_id] = content_hash

        if previous_hash is None:
            return False  # First time seeing this prompt
        return previous_hash != content_hash

    def get_cache_control_params(self) -> Dict[str, Any]:
        """
        Get provider-specific cache control parameters.

        Returns parameters to add to the LLM API call for caching.
        """
        if self._provider == LLMProvider.ANTHROPIC:
            return {
                "extra_headers": {
                    "anthropic-beta": "prompt-caching-2024-07-31"
                }
            }
        # OpenAI: automatic caching, no special params needed
        return {}

    def get_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics"""
        return {
            "provider": self._provider.value,
            "cache_hits": self._metrics.cache_hits,
            "cache_misses": self._metrics.cache_misses,
            "hit_rate": f"{self._metrics.hit_rate:.2%}",
            "tokens_saved_estimate": self._metrics.tokens_saved,
            "tracked_prompts": len(self._prompt_versions)
        }

    def reset_metrics(self) -> None:
        """Reset cache metrics"""
        self._metrics = CacheMetrics()


# Singleton instance for global access
_cache_manager: Optional[PromptCacheManager] = None


def get_prompt_cache_manager(provider: str = "openai") -> PromptCacheManager:
    """Get or create the global prompt cache manager"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = PromptCacheManager(provider)
    return _cache_manager
