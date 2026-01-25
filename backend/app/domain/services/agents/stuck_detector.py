"""
Stuck detection for agent execution loops.

Detects when an agent is producing repetitive responses and provides
mechanisms to break out of stuck states. Includes semantic similarity
detection to catch loops where queries differ but results are similar.
"""

import hashlib
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


@dataclass
class ResponseRecord:
    """Record of an LLM response for stuck detection"""
    content_hash: str
    timestamp: datetime
    tool_calls: Optional[List[str]] = None
    content_preview: str = ""
    embedding: Optional[List[float]] = None  # For semantic similarity


class StuckDetector:
    """
    Detects when an agent is stuck in a repetitive loop.

    Tracks LLM response patterns using content hashes and detects
    when the agent produces too many similar responses in succession.
    Also uses semantic similarity to catch loops where queries differ
    textually but produce similar results.
    """

    def __init__(
        self,
        window_size: int = 10,
        threshold: int = 5,
        similarity_threshold: float = 0.95,
        semantic_threshold: float = 0.90,
        enable_semantic: bool = True
    ):
        """
        Initialize the stuck detector.

        Args:
            window_size: Number of recent responses to track
            threshold: Number of IDENTICAL responses to trigger stuck detection
            similarity_threshold: Minimum similarity ratio to consider responses similar
            semantic_threshold: Threshold for semantic similarity detection (0-1)
            enable_semantic: Whether to enable semantic similarity checking
        """
        self._window_size = window_size
        self._threshold = threshold
        self._similarity_threshold = similarity_threshold
        self._semantic_threshold = semantic_threshold
        self._enable_semantic = enable_semantic
        self._response_history: deque[ResponseRecord] = deque(maxlen=window_size)
        self._stuck_count = 0
        self._recovery_attempts = 0
        self._max_recovery_attempts = 5  # More recovery attempts before giving up
        self._semantic_stuck_detected = False

        # Lightweight embedding cache for efficiency
        self._embedding_cache: Dict[str, List[float]] = {}

    def track_response(self, response: Dict[str, Any]) -> bool:
        """
        Track a new LLM response and check if agent is stuck.

        Performs both hash-based and semantic similarity checks.

        Args:
            response: The LLM response message dict

        Returns:
            True if agent is detected as stuck, False otherwise
        """
        content = response.get("content", "") or ""
        tool_calls = response.get("tool_calls", [])

        # Create hash of response content and tool calls
        content_hash = self._hash_response(content, tool_calls)

        # Extract tool function names for tracking
        tool_names = []
        if tool_calls:
            tool_names = [
                tc.get("function", {}).get("name", "")
                for tc in tool_calls
            ]

        # Get embedding for semantic comparison if enabled
        embedding = None
        if self._enable_semantic and content:
            embedding = self._get_simple_embedding(content)

        record = ResponseRecord(
            content_hash=content_hash,
            timestamp=datetime.now(),
            tool_calls=tool_names,
            content_preview=content[:100] if content else "",
            embedding=embedding
        )

        self._response_history.append(record)

        # Check for hash-based stuck pattern
        is_hash_stuck = self._detect_stuck_pattern()

        # Check for semantic stuck pattern
        is_semantic_stuck = False
        if self._enable_semantic and not is_hash_stuck:
            recent_texts = [
                r.content_preview for r in self._response_history
                if r.content_preview
            ]
            is_semantic_stuck, _ = self.check_semantic_similarity(recent_texts)

        is_stuck = is_hash_stuck or is_semantic_stuck

        if is_stuck:
            self._stuck_count += 1
            stuck_type = "hash-based" if is_hash_stuck else "semantic"
            logger.warning(
                f"Stuck pattern detected ({stuck_type}, count: {self._stuck_count}). "
                f"Similar responses in last {self._window_size} turns."
            )
        else:
            # Reset stuck count if pattern broken
            if self._stuck_count > 0:
                logger.info("Stuck pattern broken, resetting counter")
                self._stuck_count = 0
                self._recovery_attempts = 0
                self._semantic_stuck_detected = False

        return is_stuck

    def _hash_response(self, content: str, tool_calls: Optional[List[Dict]]) -> str:
        """
        Create a hash representing the response content and structure.

        Uses both content and tool call information to detect similar actions.
        """
        hash_components = []

        # Include content (normalized)
        if content:
            # Normalize whitespace and case for better matching
            normalized_content = " ".join(content.lower().split())
            hash_components.append(normalized_content)

        # Include tool call structure with argument values for better differentiation
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                func_name = func.get("name", "")
                # Include function name AND argument values to differentiate different searches
                args = func.get("arguments", "")
                if isinstance(args, str):
                    try:
                        import json
                        args_dict = json.loads(args)
                        # Include key=value pairs, sorted for consistency
                        arg_pairs = sorted(f"{k}={v}" for k, v in args_dict.items()) if isinstance(args_dict, dict) else [args]
                    except (json.JSONDecodeError, TypeError, ValueError):
                        arg_pairs = [args] if args else []
                else:
                    arg_pairs = sorted(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else []

                hash_components.append(f"{func_name}:{','.join(arg_pairs)}")

        combined = "|".join(hash_components)
        return hashlib.md5(combined.encode(), usedforsecurity=False).hexdigest()

    def _detect_stuck_pattern(self) -> bool:
        """
        Detect if recent responses show a stuck pattern.

        Returns True if threshold number of IDENTICAL responses detected.
        Uses a conservative approach to avoid false positives.
        """
        if len(self._response_history) < self._threshold:
            return False

        # Count occurrences of each hash in the window
        hash_counts: Dict[str, int] = {}
        for record in self._response_history:
            hash_counts[record.content_hash] = hash_counts.get(record.content_hash, 0) + 1

        # Check if any hash appears threshold times or more
        max_count = max(hash_counts.values()) if hash_counts else 0

        # Additional check: require the repeated hash to be in the most recent responses
        # This prevents old patterns from triggering false positives
        if max_count >= self._threshold:
            recent_hashes = [r.content_hash for r in list(self._response_history)[-3:]]
            most_common_hash = max(hash_counts, key=hash_counts.get)
            # Only flag as stuck if the repeated pattern includes recent responses
            recent_matches = sum(1 for h in recent_hashes if h == most_common_hash)
            return recent_matches >= 2  # At least 2 of last 3 are the repeated pattern

        return False

    def _get_simple_embedding(self, text: str) -> List[float]:
        """
        Get a simple embedding for text using a lightweight approach.

        Uses character n-gram frequencies as a fast, local embedding.
        This avoids API calls while still capturing semantic similarity.
        """
        if not text:
            return []

        # Check cache
        cache_key = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:16]
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # Simple character trigram frequency embedding
        # More sophisticated: could use sentence transformers or API
        text_lower = text.lower()
        trigrams = {}

        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i+3]
            trigrams[trigram] = trigrams.get(trigram, 0) + 1

        # Create fixed-size embedding from trigram frequencies
        # Use a simple hash-based approach for consistent dimensions
        embedding_dim = 128
        embedding = [0.0] * embedding_dim

        total = sum(trigrams.values())
        if total > 0:
            for trigram, count in trigrams.items():
                # Hash trigram to embedding dimension
                idx = hash(trigram) % embedding_dim
                embedding[idx] += count / total

        # Normalize
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]

        # Cache result
        if len(self._embedding_cache) > 100:  # Limit cache size
            self._embedding_cache.clear()
        self._embedding_cache[cache_key] = embedding

        return embedding

    def check_semantic_similarity(self, recent_responses: List[str]) -> Tuple[bool, float]:
        """
        Check if recent responses are semantically similar.

        Uses lightweight embeddings to detect when responses are
        similar in meaning even if they differ textually.

        Args:
            recent_responses: List of recent response texts

        Returns:
            Tuple of (is_semantically_stuck, max_similarity_score)
        """
        if not self._enable_semantic or len(recent_responses) < 3:
            return False, 0.0

        # Get embeddings for recent responses
        embeddings = [self._get_simple_embedding(r) for r in recent_responses[-5:]]

        # Check similarity between last response and previous ones
        if len(embeddings) < 2:
            return False, 0.0

        latest = embeddings[-1]
        max_similarity = 0.0
        high_similarity_count = 0

        for prev in embeddings[:-1]:
            sim = cosine_similarity(latest, prev)
            max_similarity = max(max_similarity, sim)
            if sim >= self._semantic_threshold:
                high_similarity_count += 1

        # Stuck if multiple previous responses are semantically similar
        is_stuck = high_similarity_count >= 2

        if is_stuck:
            logger.debug(
                f"Semantic similarity detected: {high_similarity_count} similar responses, "
                f"max similarity: {max_similarity:.3f}"
            )
            self._semantic_stuck_detected = True

        return is_stuck, max_similarity

    def is_stuck(self) -> bool:
        """Check if currently in stuck state (hash-based or semantic)"""
        return self._stuck_count > 0 or self._semantic_stuck_detected

    def can_attempt_recovery(self) -> bool:
        """Check if recovery attempts are available"""
        return self._recovery_attempts < self._max_recovery_attempts

    def record_recovery_attempt(self) -> None:
        """Record a recovery attempt"""
        self._recovery_attempts += 1
        logger.info(f"Recovery attempt {self._recovery_attempts}/{self._max_recovery_attempts}")

    def get_recovery_prompt(self) -> str:
        """
        Generate a recovery prompt to help break the stuck loop.

        The prompt varies based on recovery attempt number to try
        different approaches.
        """
        base_prompt = (
            "IMPORTANT: You appear to be repeating similar actions without making progress. "
            "Please take a different approach.\n\n"
        )

        if self._recovery_attempts == 0:
            return base_prompt + (
                "Suggestions:\n"
                "1. Re-read the original task and identify what's actually needed\n"
                "2. If a tool isn't working, try an alternative approach\n"
                "3. Break the problem into smaller steps\n"
                "4. If you're blocked, explain what's preventing progress"
            )
        elif self._recovery_attempts == 1:
            return base_prompt + (
                "You've been prompted about this before. Please:\n"
                "1. Stop and assess what you've attempted\n"
                "2. Identify specifically why those attempts failed\n"
                "3. Choose a completely different strategy\n"
                "4. If the task cannot be completed, explain why and ask the user for guidance"
            )
        else:
            return base_prompt + (
                "This is the final recovery attempt. Please either:\n"
                "1. Complete the task using a new approach, OR\n"
                "2. Clearly explain what is blocking progress and what user input is needed\n\n"
                "Do not repeat previous actions."
            )

    def reset(self) -> None:
        """Reset the detector state"""
        self._response_history.clear()
        self._stuck_count = 0
        self._recovery_attempts = 0
        self._semantic_stuck_detected = False
        self._embedding_cache.clear()
        logger.debug("Stuck detector reset")

    def get_stats(self) -> Dict[str, Any]:
        """Get current detector statistics"""
        return {
            "window_size": self._window_size,
            "threshold": self._threshold,
            "semantic_threshold": self._semantic_threshold,
            "semantic_enabled": self._enable_semantic,
            "responses_tracked": len(self._response_history),
            "stuck_count": self._stuck_count,
            "recovery_attempts": self._recovery_attempts,
            "is_stuck": self.is_stuck(),
            "semantic_stuck": self._semantic_stuck_detected,
            "can_recover": self.can_attempt_recovery(),
            "embedding_cache_size": len(self._embedding_cache)
        }
