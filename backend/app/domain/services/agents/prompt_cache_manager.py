"""
Prompt cache management for KV-cache optimization.

Implements caching strategies for both OpenAI and Anthropic APIs
to reduce token costs by ~90% on repeated system prompts.
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

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
        self._prompt_versions: dict[str, str] = {}
        self._cached_prefix_hash: str | None = None
        logger.info(f"PromptCacheManager initialized for provider: {self._provider.value}")

    def _detect_provider(self, provider_name: str) -> LLMProvider:
        """Detect LLM provider from model/API name"""
        provider_lower = provider_name.lower()

        if any(term in provider_lower for term in ['openai', 'gpt', 'o1', 'o3']):
            return LLMProvider.OPENAI
        if any(term in provider_lower for term in ['anthropic', 'claude']):
            return LLMProvider.ANTHROPIC
        return LLMProvider.UNKNOWN

    def prepare_messages_for_caching(
        self,
        messages: list[dict[str, Any]],
        dynamic_content: str | None = None
    ) -> list[dict[str, Any]]:
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
        if self._provider == LLMProvider.OPENAI:
            return self._prepare_openai_caching(messages, dynamic_content)
        return messages

    def _prepare_openai_caching(
        self,
        messages: list[dict[str, Any]],
        dynamic_content: str | None = None
    ) -> list[dict[str, Any]]:
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
        messages: list[dict[str, Any]],
        dynamic_content: str | None = None
    ) -> list[dict[str, Any]]:
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
        dynamic_sections: list[str] | None = None
    ) -> tuple[str, str]:
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

    def get_cache_control_params(self) -> dict[str, Any]:
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

    def get_metrics(self) -> dict[str, Any]:
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


# =============================================================================
# Semantic Response Cache
# =============================================================================

@dataclass
class CachedResponse:
    """A cached LLM response with metadata."""
    response: str
    prompt_hash: str
    created_at: float
    hit_count: int = 0
    semantic_key: str | None = None


class SemanticResponseCache:
    """Semantic caching for LLM responses.

    Caches responses based on semantic similarity of prompts,
    not just exact matches. This provides:
    - 8x speedup on repeated/similar queries (per LangChain research)
    - Reduced API costs
    - Consistent responses for similar questions

    Usage:
        cache = SemanticResponseCache(ttl_seconds=900)

        # Check cache before LLM call
        cached = cache.get("What is Python?")
        if cached:
            return cached

        # After LLM call
        cache.put("What is Python?", response)
    """

    def __init__(
        self,
        ttl_seconds: int = 900,  # 15 minutes
        max_entries: int = 1000,
        similarity_threshold: float = 0.85,
    ):
        """Initialize the semantic cache.

        Args:
            ttl_seconds: Time-to-live for cache entries
            max_entries: Maximum number of cached entries
            similarity_threshold: Minimum similarity for cache hit (0-1)
        """
        self._cache: dict[str, CachedResponse] = {}
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._similarity_threshold = similarity_threshold
        self._metrics = CacheMetrics()

        logger.info(
            f"SemanticResponseCache initialized: "
            f"ttl={ttl_seconds}s, max_entries={max_entries}"
        )

    def _hash_prompt(self, prompt: str) -> str:
        """Create a hash of the prompt for exact matching."""
        # Normalize: lowercase, remove extra whitespace
        normalized = " ".join(prompt.lower().split())
        return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()

    def _extract_semantic_key(self, prompt: str) -> str:
        """Extract semantic key from prompt for similarity matching.

        Uses a simplified approach: extracts key nouns/verbs for matching.
        For production, consider using embeddings.
        """
        import re

        # Remove common filler words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "to", "of", "in",
            "for", "on", "with", "at", "by", "from", "as", "into", "through",
            "during", "before", "after", "above", "below", "between", "under",
            "again", "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "few", "more", "most", "other", "some",
            "such", "no", "nor", "not", "only", "own", "same", "so", "than",
            "too", "very", "just", "and", "but", "if", "or", "because", "until",
            "while", "although", "please", "help", "me", "i", "you", "we", "they",
            "it", "this", "that", "these", "those", "what", "which", "who",
        }

        # Extract words, lowercase, filter
        words = re.findall(r'\b[a-z]+\b', prompt.lower())
        key_words = [w for w in words if w not in stop_words and len(w) > 2]

        # Sort for consistent ordering
        key_words = sorted(set(key_words))[:10]  # Limit to 10 key words

        return " ".join(key_words)

    def _calculate_similarity(self, key1: str, key2: str) -> float:
        """Calculate similarity between two semantic keys.

        Uses Jaccard similarity for speed. For better accuracy,
        consider using embedding cosine similarity.
        """
        words1 = set(key1.split())
        words2 = set(key2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def get(self, prompt: str) -> str | None:
        """Get a cached response for a prompt.

        Args:
            prompt: The user prompt

        Returns:
            Cached response if found and valid, None otherwise
        """
        import time
        current_time = time.time()

        # Clean expired entries periodically
        if len(self._cache) > self._max_entries:
            self._evict_expired(current_time)

        # Try exact match first (fastest)
        prompt_hash = self._hash_prompt(prompt)
        if prompt_hash in self._cache:
            entry = self._cache[prompt_hash]
            if current_time - entry.created_at < self._ttl:
                entry.hit_count += 1
                self._metrics.record_hit()
                logger.debug(f"Cache hit (exact): {prompt_hash[:8]}...")
                return entry.response

        # Try semantic match
        semantic_key = self._extract_semantic_key(prompt)
        best_match: CachedResponse | None = None
        best_similarity = 0.0

        for entry in self._cache.values():
            if current_time - entry.created_at >= self._ttl:
                continue

            if entry.semantic_key:
                similarity = self._calculate_similarity(semantic_key, entry.semantic_key)
                if similarity > best_similarity and similarity >= self._similarity_threshold:
                    best_similarity = similarity
                    best_match = entry

        if best_match:
            best_match.hit_count += 1
            self._metrics.record_hit()
            logger.debug(
                f"Cache hit (semantic): similarity={best_similarity:.2f}, "
                f"key={semantic_key[:30]}..."
            )
            return best_match.response

        self._metrics.record_miss()
        return None

    def put(self, prompt: str, response: str) -> None:
        """Cache a response for a prompt.

        Args:
            prompt: The user prompt
            response: The LLM response to cache
        """
        import time

        # Evict if at capacity
        if len(self._cache) >= self._max_entries:
            self._evict_lru()

        prompt_hash = self._hash_prompt(prompt)
        semantic_key = self._extract_semantic_key(prompt)

        self._cache[prompt_hash] = CachedResponse(
            response=response,
            prompt_hash=prompt_hash,
            created_at=time.time(),
            hit_count=0,
            semantic_key=semantic_key,
        )

        logger.debug(f"Cached response: {prompt_hash[:8]}... (key: {semantic_key[:30]}...)")

    def _evict_expired(self, current_time: float) -> int:
        """Remove expired entries.

        Returns:
            Number of entries evicted
        """
        expired = [
            k for k, v in self._cache.items()
            if current_time - v.created_at >= self._ttl
        ]
        for k in expired:
            del self._cache[k]

        if expired:
            logger.debug(f"Evicted {len(expired)} expired cache entries")

        return len(expired)

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        # Find entry with lowest hit count (approximation of LRU)
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].hit_count)
        del self._cache[lru_key]
        logger.debug(f"Evicted LRU cache entry: {lru_key[:8]}...")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.info("Semantic response cache cleared")

    def get_metrics(self) -> dict[str, Any]:
        """Get cache performance metrics."""
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl,
            **self._metrics.__dict__,
            "hit_rate": f"{self._metrics.hit_rate:.2%}",
        }


# Singleton instances for global access
_cache_manager: PromptCacheManager | None = None
_response_cache: SemanticResponseCache | None = None


def get_prompt_cache_manager(provider: str = "openai") -> PromptCacheManager:
    """Get or create the global prompt cache manager"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = PromptCacheManager(provider)
    return _cache_manager


def get_semantic_cache(
    ttl_seconds: int = 900,
    max_entries: int = 1000,
) -> SemanticResponseCache:
    """Get or create the global semantic response cache.

    Args:
        ttl_seconds: Cache TTL (15 minutes default)
        max_entries: Maximum cache entries

    Returns:
        SemanticResponseCache instance
    """
    global _response_cache
    if _response_cache is None:
        _response_cache = SemanticResponseCache(
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )
    return _response_cache
