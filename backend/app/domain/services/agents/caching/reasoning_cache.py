"""
Reasoning Pattern Caching module.

This module provides caching for successful reasoning patterns
to enable faster decision-making on similar problems.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.models.thought import Decision, ThoughtChain

logger = logging.getLogger(__name__)


@dataclass
class CachedReasoning:
    """A cached reasoning pattern."""

    cache_key: str
    problem_hash: str
    problem_summary: str
    thought_chain: ThoughtChain
    decision: Decision
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime | None = None
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(hours=24))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate when this pattern is used."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    def is_expired(self) -> bool:
        """Check if the cached reasoning has expired."""
        return datetime.now(UTC) > self.expires_at

    def is_reliable(self, min_uses: int = 3, min_success_rate: float = 0.6) -> bool:
        """Check if this pattern is reliable enough to use."""
        total = self.success_count + self.failure_count
        return total >= min_uses and self.success_rate >= min_success_rate

    def record_use(self, success: bool) -> None:
        """Record a use of this pattern."""
        self.last_used = datetime.now(UTC)
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1


@dataclass
class ReasoningMatch:
    """A match result from the reasoning cache."""

    cached_reasoning: CachedReasoning
    similarity_score: float
    confidence: float
    should_use: bool
    reason: str


class ReasoningCache:
    """Cache for successful reasoning patterns.

    Stores reasoning chains and decisions that led to successful
    outcomes, enabling pattern reuse for similar problems.
    """

    # Maximum cache entries
    MAX_ENTRIES = 500
    # Minimum similarity score to consider a match
    MIN_SIMILARITY = 0.6
    # Minimum confidence to suggest using cached reasoning
    MIN_CONFIDENCE = 0.5

    def __init__(
        self,
        max_entries: int | None = None,
    ) -> None:
        """Initialize the reasoning cache.

        Args:
            max_entries: Maximum cache entries
        """
        self._cache: dict[str, CachedReasoning] = {}
        self._max_entries = max_entries or self.MAX_ENTRIES
        self._total_hits = 0
        self._total_misses = 0

    def store(
        self,
        problem: str,
        thought_chain: ThoughtChain,
        decision: Decision,
        context: dict[str, Any] | None = None,
        ttl_hours: int = 24,
    ) -> CachedReasoning:
        """Store a reasoning pattern.

        Args:
            problem: The problem that was solved
            thought_chain: The reasoning chain used
            decision: The decision made
            context: Optional context
            ttl_hours: Time to live in hours

        Returns:
            The cached reasoning entry
        """
        # Evict if needed
        if len(self._cache) >= self._max_entries:
            self._evict_least_used()

        cache_key = self._generate_key(problem)
        problem_hash = self._hash_problem(problem)

        cached = CachedReasoning(
            cache_key=cache_key,
            problem_hash=problem_hash,
            problem_summary=problem[:200],
            thought_chain=thought_chain,
            decision=decision,
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
            metadata=context or {},
        )

        self._cache[cache_key] = cached

        logger.debug(f"Cached reasoning pattern: {cache_key[:20]}...")
        return cached

    def find_similar(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        min_similarity: float | None = None,
    ) -> ReasoningMatch | None:
        """Find similar cached reasoning for a problem.

        Args:
            problem: The problem to find reasoning for
            context: Optional context for matching
            min_similarity: Minimum similarity threshold

        Returns:
            Match result if found, None otherwise
        """
        min_similarity = min_similarity or self.MIN_SIMILARITY

        # First try exact match
        cache_key = self._generate_key(problem)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                self._total_hits += 1
                return ReasoningMatch(
                    cached_reasoning=cached,
                    similarity_score=1.0,
                    confidence=cached.success_rate,
                    should_use=cached.is_reliable(),
                    reason="Exact match found",
                )

        # Find similar problems
        best_match = None
        best_score = 0.0

        for cached in self._cache.values():
            if cached.is_expired():
                continue

            similarity = self._calculate_similarity(problem, cached.problem_summary)
            if similarity > best_score and similarity >= min_similarity:
                best_score = similarity
                best_match = cached

        if not best_match:
            self._total_misses += 1
            return None

        self._total_hits += 1

        # Calculate confidence based on similarity and success rate
        confidence = best_score * best_match.success_rate

        should_use = confidence >= self.MIN_CONFIDENCE and best_match.is_reliable()

        return ReasoningMatch(
            cached_reasoning=best_match,
            similarity_score=best_score,
            confidence=confidence,
            should_use=should_use,
            reason=f"Similar pattern found (similarity={best_score:.2f})",
        )

    def record_outcome(
        self,
        cache_key: str,
        success: bool,
    ) -> None:
        """Record the outcome of using cached reasoning.

        Args:
            cache_key: Key of the cached reasoning
            success: Whether using it was successful
        """
        if cache_key in self._cache:
            self._cache[cache_key].record_use(success)

    def get_pattern_for_type(
        self,
        problem_type: str,
        min_success_rate: float = 0.7,
    ) -> CachedReasoning | None:
        """Get the best pattern for a problem type.

        Args:
            problem_type: Type of problem
            min_success_rate: Minimum success rate

        Returns:
            Best matching pattern if found
        """
        best_pattern = None
        best_score = 0.0

        for cached in self._cache.values():
            if cached.is_expired():
                continue

            if problem_type.lower() not in cached.problem_summary.lower():
                continue

            if cached.success_rate < min_success_rate:
                continue

            # Score based on success rate and usage
            score = cached.success_rate * (1 + 0.1 * min(cached.success_count, 10))
            if score > best_score:
                best_score = score
                best_pattern = cached

        return best_pattern

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        expired = [key for key, cached in self._cache.items() if cached.is_expired()]

        for key in expired:
            del self._cache[key]

        return len(expired)

    def cleanup_low_performing(
        self,
        min_uses: int = 5,
        min_success_rate: float = 0.3,
    ) -> int:
        """Remove low-performing patterns.

        Args:
            min_uses: Minimum uses before evaluating
            min_success_rate: Minimum success rate to keep

        Returns:
            Number of entries removed
        """
        to_remove = []

        for key, cached in self._cache.items():
            total = cached.success_count + cached.failure_count
            if total >= min_uses and cached.success_rate < min_success_rate:
                to_remove.append(key)

        for key in to_remove:
            del self._cache[key]

        return len(to_remove)

    def get_statistics(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._total_hits + self._total_misses
        hit_rate = self._total_hits / total if total > 0 else 0

        reliable_count = sum(1 for c in self._cache.values() if c.is_reliable())

        return {
            "total_entries": len(self._cache),
            "reliable_entries": reliable_count,
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "hit_rate": hit_rate,
            "average_success_rate": self._average_success_rate(),
        }

    def _generate_key(self, problem: str) -> str:
        """Generate a cache key for a problem."""
        # Normalize the problem
        normalized = problem.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _hash_problem(self, problem: str) -> str:
        """Generate a hash of the problem."""
        return hashlib.md5(problem.encode()).hexdigest()  # noqa: S324 - MD5 used for non-security cache key, not cryptographic

    def _calculate_similarity(self, problem1: str, problem2: str) -> float:
        """Calculate similarity between two problems."""
        words1 = set(problem1.lower().split())
        words2 = set(problem2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _evict_least_used(self) -> None:
        """Evict the least used entry."""
        if not self._cache:
            return

        # Find entry with lowest usage and oldest last_used
        worst_key = None
        worst_score = float("inf")

        for key, cached in self._cache.items():
            total_uses = cached.success_count + cached.failure_count
            recency = (datetime.now(UTC) - (cached.last_used or cached.created_at)).total_seconds()
            score = total_uses - (recency / 3600)  # Penalize old entries

            if score < worst_score:
                worst_score = score
                worst_key = key

        if worst_key:
            del self._cache[worst_key]

    def _average_success_rate(self) -> float:
        """Calculate average success rate across all patterns."""
        if not self._cache:
            return 0.0

        rates = [c.success_rate for c in self._cache.values()]
        return sum(rates) / len(rates)


# Global reasoning cache instance
_cache: ReasoningCache | None = None


def get_reasoning_cache() -> ReasoningCache:
    """Get or create the global reasoning cache."""
    global _cache
    if _cache is None:
        _cache = ReasoningCache()
    return _cache


def reset_reasoning_cache() -> None:
    """Reset the global reasoning cache."""
    global _cache
    _cache = None
