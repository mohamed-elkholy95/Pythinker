"""
Stuck detection for agent execution loops.

Detects when an agent is producing repetitive responses and provides
mechanisms to break out of stuck states. Includes semantic similarity
detection to catch loops where queries differ but results are similar.

Enhanced with OpenHands-inspired patterns:
- Action-observation loop detection
- Action-error loop detection
- Alternating pattern detection (A→B→A→B)
- Monologue detection (explaining without acting)
- Context window error loops
"""

import hashlib
import logging
import math
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


def compute_trigram_embedding(text: str, embedding_dim: int = 128) -> list[float]:
    """Compute a trigram-based embedding for text.

    Uses character trigram frequencies as a lightweight embedding approach.
    This avoids API calls while still capturing semantic similarity.

    Args:
        text: Text to embed
        embedding_dim: Dimension of the output embedding vector

    Returns:
        Normalized embedding vector of the specified dimension
    """
    if not text:
        return []

    text_lower = text.lower()
    text_len = len(text_lower)

    # Early exit for very short text
    if text_len < 3:
        return []

    # Count trigrams
    trigrams: dict[str, int] = {}
    for i in range(text_len - 2):
        trigram = text_lower[i : i + 3]
        trigrams[trigram] = trigrams.get(trigram, 0) + 1

    # Create fixed-size embedding from trigram frequencies
    embedding = [0.0] * embedding_dim

    total = sum(trigrams.values())
    if total > 0:
        inv_total = 1.0 / total  # Compute inverse once
        for trigram, count in trigrams.items():
            # Hash trigram to embedding dimension using deterministic hash
            # (hash() is randomized across Python processes via PYTHONHASHSEED)
            idx = (
                int.from_bytes(
                    hashlib.md5(trigram.encode(), usedforsecurity=False).digest()[:4],
                    "little",
                )
                % embedding_dim
            )
            embedding[idx] += count * inv_total

    # Normalize
    norm_sq = sum(x * x for x in embedding)
    if norm_sq > 0:
        inv_norm = 1.0 / math.sqrt(norm_sq)
        embedding = [x * inv_norm for x in embedding]

    return embedding


class LRUCache:
    """Simple LRU cache using OrderedDict for O(1) operations."""

    __slots__ = ("_cache", "_maxsize")

    def __init__(self, maxsize: int = 100):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Any | None:
        """Get item and move to end (most recently used)."""
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        """Put item, evicting oldest if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)  # Remove oldest
        self._cache[key] = value

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class LoopType(Enum):
    """Types of stuck loops that can be detected."""

    RESPONSE_REPETITION = "response_repetition"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    REPEATING_ACTION_OBSERVATION = "repeating_action_observation"
    REPEATING_ACTION_ERROR = "repeating_action_error"
    ALTERNATING_PATTERN = "alternating_pattern"
    MONOLOGUE = "monologue"
    TOOL_FAILURE_CASCADE = "tool_failure_cascade"
    # Browser-specific patterns
    BROWSER_SAME_PAGE_LOOP = "browser_same_page_loop"
    BROWSER_SCROLL_NO_PROGRESS = "browser_scroll_no_progress"
    BROWSER_CLICK_FAILURES = "browser_click_failures"
    # Enhanced detection patterns
    EXCESSIVE_SAME_TOOL = "excessive_same_tool"
    URL_REVISIT_PATTERN = "url_revisit_pattern"
    NO_PROGRESS = "no_progress"


class RecoveryStrategy(Enum):
    """Recovery strategies for stuck states."""

    PROMPT_VARIATION = "prompt_variation"
    TRY_ALTERNATIVE_APPROACH = "try_alternative_approach"
    ANALYZE_ERROR_PATTERN = "analyze_error_pattern"
    BREAK_ALTERNATING_CYCLE = "break_alternating_cycle"
    TAKE_CONCRETE_ACTION = "take_concrete_action"
    ESCALATE_TO_USER = "escalate_to_user"
    REPLAN_TASK = "replan_task"


@dataclass
class StuckAnalysis:
    """Detailed analysis of a stuck state."""

    loop_type: LoopType
    confidence: float
    repeat_count: int
    recovery_strategy: RecoveryStrategy
    details: str = ""
    affected_tools: list[str] = field(default_factory=list)


@dataclass
class ToolActionRecord:
    """Record of a tool action for pattern detection."""

    tool_name: str
    args_hash: str
    success: bool
    result_hash: str
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
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
    tool_calls: list[str] | None = None
    content_preview: str = ""
    embedding: list[float] | None = None  # For semantic similarity


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
        window_size: int = 5,  # Reduced from 10 for faster loop detection
        threshold: int = 3,  # Reduced from 5 for faster loop detection
        similarity_threshold: float = 0.95,
        semantic_threshold: float = 0.90,
        enable_semantic: bool = True,
    ):
        """
        Initialize the stuck detector.

        Args:
            window_size: Number of recent responses to track (default reduced for faster detection)
            threshold: Number of IDENTICAL responses to trigger stuck detection (default reduced)
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
        self._max_recovery_attempts = 3  # Align with prompt retry guidance
        self._semantic_stuck_detected = False

        # LRU embedding cache for efficiency (proper eviction instead of clear-all)
        self._embedding_cache: LRUCache = LRUCache(maxsize=100)

        # Enhanced: Tool action tracking for OpenHands-style pattern detection
        self._tool_action_history: deque[ToolActionRecord] = deque(maxlen=50)
        self._stuck_analysis: StuckAnalysis | None = None

    def track_response(self, response: dict[str, Any]) -> tuple[bool, float]:
        """
        Track a new LLM response and check if agent is stuck (Phase 4 P1).

        Performs both hash-based and semantic similarity checks with
        confidence scoring to reduce false positives.

        Args:
            response: The LLM response message dict

        Returns:
            Tuple of (is_stuck, confidence_score)
        """
        content = response.get("content", "") or ""
        tool_calls = response.get("tool_calls", [])

        # Create hash of response content and tool calls
        content_hash = self._hash_response(content, tool_calls)

        # Extract tool function names for tracking
        tool_names = []
        if tool_calls:
            tool_names = [tc.get("function", {}).get("name", "") for tc in tool_calls]

        # Get embedding for semantic comparison if enabled
        embedding = None
        if self._enable_semantic and content:
            embedding = self._get_simple_embedding(content)

        record = ResponseRecord(
            content_hash=content_hash,
            timestamp=datetime.now(),
            tool_calls=tool_names,
            content_preview=content[:100] if content else "",
            embedding=embedding,
        )

        self._response_history.append(record)

        # Check for hash-based stuck pattern
        is_hash_stuck = self._detect_stuck_pattern()

        # Check for semantic stuck pattern (uses embeddings from response history)
        is_semantic_stuck = False
        similarity_score = 0.0
        if self._enable_semantic and not is_hash_stuck:
            is_semantic_stuck, similarity_score = self.check_semantic_similarity()

        # Phase 4 P1: Calculate confidence score
        confidence = 0.0
        if is_hash_stuck:
            confidence = max(confidence, 0.8)  # Hash match is strong signal

        if similarity_score > 0:
            confidence += 0.3 * similarity_score  # Weight by similarity

        # Check for tool action patterns
        tool_pattern_conf = self._detect_action_patterns_confidence()
        confidence += 0.4 * (tool_pattern_conf or 0.0)
        confidence = min(confidence, 1.0)

        # Trigger only if confidence exceeds threshold
        is_stuck = confidence >= 0.7

        if is_stuck:
            self._stuck_count += 1
            stuck_type = "hash-based" if is_hash_stuck else "semantic"
            logger.warning(
                f"Stuck pattern detected ({stuck_type}, count: {self._stuck_count}, confidence: {confidence:.2f}). "
                f"Similar responses in last {self._window_size} turns."
            )
        else:
            # Reset stuck count if pattern broken
            if self._stuck_count > 0:
                logger.info("Stuck pattern broken, resetting counter")
                self._stuck_count = 0
                self._recovery_attempts = 0
                self._semantic_stuck_detected = False
                self._stuck_analysis = None

        # Phase 4 P1: Log detection check
        logger.debug(
            "Stuck detection check",
            extra={
                "is_stuck": is_stuck,
                "confidence": confidence,
                "hash_stuck": is_hash_stuck,
                "semantic_similarity": similarity_score if is_semantic_stuck else 0,
                "tool_pattern": tool_pattern_conf,
            },
        )

        return is_stuck, confidence

    def _hash_response(self, content: str, tool_calls: list[dict] | None) -> str:
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
                        arg_pairs = (
                            sorted(f"{k}={v}" for k, v in args_dict.items()) if isinstance(args_dict, dict) else [args]
                        )
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
        hash_counts: dict[str, int] = {}
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

    def _detect_action_patterns_confidence(self) -> float:
        """Detect tool action patterns and return confidence (Phase 4 P1).

        Returns:
            Confidence score (0.0-1.0) for action-based stuck patterns
        """
        if len(self._tool_action_history) < 3:
            return 0.0

        recent = list(self._tool_action_history)[-5:]

        # Check for repeated failed actions
        same_tool_count = 0
        failed_count = 0
        for i in range(len(recent) - 1):
            if recent[i].tool_name == recent[i + 1].tool_name:
                same_tool_count += 1
                if not recent[i].success:
                    failed_count += 1

        # Calculate confidence based on patterns
        confidence = 0.0

        # Same tool repeated multiple times
        if same_tool_count >= 2:
            confidence += 0.4

        # Same tool failing repeatedly
        if failed_count >= 2:
            confidence += 0.4

        # Recent actions mostly failures
        recent_failure_rate = sum(1 for r in recent if not r.success) / len(recent)
        if recent_failure_rate > 0.6:
            confidence += 0.2 * recent_failure_rate

        return min(confidence, 1.0)

    def _get_simple_embedding(self, text: str) -> list[float]:
        """
        Get a simple embedding for text using a lightweight approach.

        Uses character n-gram frequencies as a fast, local embedding.
        This avoids API calls while still capturing semantic similarity.

        Performance optimizations:
        - LRU cache with proper eviction (no full clear)
        - Pre-computed hash for cache key
        - Reuses compute_trigram_embedding function
        """
        if not text:
            return []

        # Check LRU cache first
        cache_key = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()
        cached = self._embedding_cache.get(cache_key)
        if cached is not None:
            return cached

        # Use the standalone trigram embedding function
        embedding = compute_trigram_embedding(text)
        if not embedding:
            return []

        # Cache result with LRU eviction
        self._embedding_cache.put(cache_key, embedding)

        return embedding

    def check_semantic_similarity(self, recent_responses: list[str] | None = None) -> tuple[bool, float]:
        """
        Check if recent responses are semantically similar.

        Uses lightweight embeddings to detect when responses are
        similar in meaning even if they differ textually.

        Performance optimizations:
        - Reuses embeddings already computed and stored in ResponseRecord
        - Early exit when threshold can't be reached
        - Only computes new embeddings for records that don't have them

        Args:
            recent_responses: Optional list of response texts (deprecated, uses history instead)

        Returns:
            Tuple of (is_semantically_stuck, max_similarity_score)
        """
        if not self._enable_semantic or len(self._response_history) < 3:
            return False, 0.0

        # Use embeddings from response history (already computed during track_response)
        recent_records = list(self._response_history)[-5:]

        # Filter records with valid embeddings
        embeddings = [r.embedding for r in recent_records if r.embedding]

        if len(embeddings) < 2:
            return False, 0.0

        latest = embeddings[-1]
        max_similarity = 0.0
        high_similarity_count = 0

        # Early exit optimization: stop checking once we've found enough similar responses
        for prev in embeddings[:-1]:
            sim = cosine_similarity(latest, prev)
            if sim > max_similarity:
                max_similarity = sim
            if sim >= self._semantic_threshold:
                high_similarity_count += 1
                # Early exit: if we already have enough similar, no need to check more
                if high_similarity_count >= 2:
                    break

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

    def check_simple_repetition(self, outputs: list[str]) -> bool:
        """Backward-compatible simple repetition check over raw outputs."""
        if len(outputs) < self._threshold:
            return False

        recent = outputs[-self._threshold :]
        normalized = [output.strip() for output in recent if output is not None]
        if len(normalized) < self._threshold:
            return False
        return len(set(normalized)) == 1

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
        if self._recovery_attempts == 1:
            return base_prompt + (
                "You've been prompted about this before. Please:\n"
                "1. Stop and assess what you've attempted\n"
                "2. Identify specifically why those attempts failed\n"
                "3. Choose a completely different strategy\n"
                "4. If the task cannot be completed, explain why and ask the user for guidance"
            )
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
        self._tool_action_history.clear()
        self._stuck_analysis = None
        logger.debug("Stuck detector reset")

    def get_stats(self) -> dict[str, Any]:
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
            "embedding_cache_size": len(self._embedding_cache),
            "tool_actions_tracked": len(self._tool_action_history),
            "current_analysis": self._stuck_analysis.loop_type.value if self._stuck_analysis else None,
        }

    # =========================================================================
    # Enhanced Action-Based Detection (OpenHands-inspired)
    # =========================================================================

    def track_tool_action(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        success: bool,
        result: str | None = None,
        error: str | None = None,
    ) -> StuckAnalysis | None:
        """
        Track a tool action and check for action-based stuck patterns.

        This provides more granular stuck detection than response-level tracking,
        catching patterns like:
        - Same tool call producing same result repeatedly
        - Same tool call producing errors repeatedly
        - Alternating between two approaches without progress

        Args:
            tool_name: Name of the tool called
            tool_args: Arguments passed to the tool
            success: Whether the tool call succeeded
            result: Result of the tool call (for hashing)
            error: Error message if failed

        Returns:
            StuckAnalysis if a stuck pattern is detected, None otherwise
        """
        args_hash = self._hash_dict(tool_args)
        result_hash = self._hash_content(result) if result else ""

        record = ToolActionRecord(
            tool_name=tool_name,
            args_hash=args_hash,
            success=success,
            result_hash=result_hash,
            error=error,
        )

        self._tool_action_history.append(record)

        # Check for action-based patterns
        analysis = self._detect_action_patterns()
        if analysis:
            self._stuck_analysis = analysis
            self._stuck_count += 1
            logger.warning(
                f"Action stuck pattern detected: {analysis.loop_type.value} (confidence: {analysis.confidence:.2f})"
            )

        return analysis

    def _detect_action_patterns(self) -> StuckAnalysis | None:
        """Detect stuck patterns in tool action history."""
        if len(self._tool_action_history) < 3:
            return None

        # Check browser-specific patterns first (more specific)
        if analysis := self._detect_browser_same_page_loop():
            return analysis

        if analysis := self._detect_browser_scroll_no_progress():
            return analysis

        if analysis := self._detect_browser_click_failures():
            return analysis

        # Check enhanced patterns (URL revisit, excessive same tool, no progress)
        if analysis := self._detect_url_revisit_pattern():
            return analysis

        if analysis := self._detect_excessive_same_tool():
            return analysis

        if analysis := self._detect_no_progress():
            return analysis

        # Check generic patterns in order of severity
        if analysis := self._detect_action_error_loop():
            return analysis

        if analysis := self._detect_action_observation_loop():
            return analysis

        if analysis := self._detect_alternating_pattern():
            return analysis

        if analysis := self._detect_tool_failure_cascade():
            return analysis

        return None

    def _detect_action_error_loop(self) -> StuckAnalysis | None:
        """
        Detect: Same action producing errors repeatedly.

        Pattern: tool_call(args) → error → tool_call(args) → error → ...
        """
        error_threshold = 3
        if len(self._tool_action_history) < error_threshold:
            return None

        recent = list(self._tool_action_history)[-error_threshold:]

        # Check if all are the same action with errors
        first = recent[0]
        all_same_failed = all(
            r.tool_name == first.tool_name and r.args_hash == first.args_hash and not r.success for r in recent
        )

        if all_same_failed:
            return StuckAnalysis(
                loop_type=LoopType.REPEATING_ACTION_ERROR,
                confidence=0.95,
                repeat_count=error_threshold,
                recovery_strategy=RecoveryStrategy.ANALYZE_ERROR_PATTERN,
                details=f"Tool '{first.tool_name}' failed {error_threshold} times with same arguments",
                affected_tools=[first.tool_name],
            )

        return None

    def _detect_action_observation_loop(self) -> StuckAnalysis | None:
        """
        Detect: Same action producing same result repeatedly.

        Pattern: tool_call(args) → result → tool_call(args) → same_result → ...
        """
        repeat_threshold = 4
        if len(self._tool_action_history) < repeat_threshold:
            return None

        recent = list(self._tool_action_history)[-repeat_threshold:]

        # Check if all are the same successful action with same result
        first = recent[0]
        all_same = all(
            r.tool_name == first.tool_name
            and r.args_hash == first.args_hash
            and r.success
            and r.result_hash == first.result_hash
            for r in recent
        )

        if all_same and first.success:
            return StuckAnalysis(
                loop_type=LoopType.REPEATING_ACTION_OBSERVATION,
                confidence=0.90,
                repeat_count=repeat_threshold,
                recovery_strategy=RecoveryStrategy.TRY_ALTERNATIVE_APPROACH,
                details=f"Tool '{first.tool_name}' called {repeat_threshold} times with same result",
                affected_tools=[first.tool_name],
            )

        return None

    def _detect_alternating_pattern(self) -> StuckAnalysis | None:
        """
        Detect: Alternating between two approaches without progress.

        Pattern: A → B → A → B → A → B
        """
        min_history = 6
        if len(self._tool_action_history) < min_history:
            return None

        recent = list(self._tool_action_history)[-min_history:]

        # Get signatures (tool + args hash)
        signatures = [(r.tool_name, r.args_hash) for r in recent]

        # Check for A-B-A-B-A-B pattern
        even_sigs = signatures[0::2]  # A positions
        odd_sigs = signatures[1::2]  # B positions

        even_same = len(set(even_sigs)) == 1
        odd_same = len(set(odd_sigs)) == 1
        different = even_sigs[0] != odd_sigs[0]

        if even_same and odd_same and different:
            return StuckAnalysis(
                loop_type=LoopType.ALTERNATING_PATTERN,
                confidence=0.85,
                repeat_count=3,
                recovery_strategy=RecoveryStrategy.BREAK_ALTERNATING_CYCLE,
                details=f"Alternating between '{signatures[0][0]}' and '{signatures[1][0]}'",
                affected_tools=[signatures[0][0], signatures[1][0]],
            )

        return None

    def _detect_tool_failure_cascade(self) -> StuckAnalysis | None:
        """
        Detect: Multiple different tools all failing.

        This indicates a systemic issue (environment, permissions, etc.)
        """
        if len(self._tool_action_history) < 5:
            return None

        recent = list(self._tool_action_history)[-5:]

        # Check if all recent actions failed
        all_failed = all(not r.success for r in recent)

        # And they're different tools
        unique_tools = {r.tool_name for r in recent}

        if all_failed and len(unique_tools) >= 3:
            return StuckAnalysis(
                loop_type=LoopType.TOOL_FAILURE_CASCADE,
                confidence=0.80,
                repeat_count=5,
                recovery_strategy=RecoveryStrategy.ESCALATE_TO_USER,
                details=f"Multiple tools failing: {', '.join(unique_tools)}",
                affected_tools=list(unique_tools),
            )

        return None

    # =========================================================================
    # Browser-Specific Stuck Detection
    # =========================================================================

    def _detect_browser_same_page_loop(self) -> StuckAnalysis | None:
        """
        Detect: Navigating to the same URL repeatedly.

        Pattern: browser_navigate(url) → browser_navigate(same_url) → ...

        Conservative thresholds to reduce false positives from legitimate retries:
        - Minimum 3 navigations before checking
        - Window of last 4 navigations
        - Triggers on 3 same-URL navigations
        """
        browser_nav_tools = {"browser_navigate", "browsing"}

        recent = [r for r in self._tool_action_history if r.tool_name in browser_nav_tools]

        if len(recent) < 3:
            return None

        # Check last 4 browser navigations
        recent = recent[-4:]

        # Check if most have the same args hash (same URL)
        first_hash = recent[0].args_hash
        same_url_count = sum(1 for r in recent if r.args_hash == first_hash)

        if same_url_count >= 3:
            return StuckAnalysis(
                loop_type=LoopType.BROWSER_SAME_PAGE_LOOP,
                confidence=0.90,
                repeat_count=same_url_count,
                recovery_strategy=RecoveryStrategy.TRY_ALTERNATIVE_APPROACH,
                details="Navigating to the same URL repeatedly - page content won't change",
                affected_tools=["browser_navigate"],
            )

        return None

    def _detect_browser_scroll_no_progress(self) -> StuckAnalysis | None:
        """
        Detect: Repeated scrolling without extracting or processing content.

        Pattern: scroll_down → scroll_down → scroll_down (without browser_view/content extraction)
        """
        scroll_tools = {"browser_scroll_down", "browser_scroll_up"}
        content_tools = {"browser_view", "browser_get_content", "browsing"}

        recent = list(self._tool_action_history)[-8:]

        if len(recent) < 5:
            return None

        # Count consecutive scrolls without content extraction
        consecutive_scrolls = 0
        for record in reversed(recent):
            if record.tool_name in scroll_tools:
                consecutive_scrolls += 1
            elif record.tool_name in content_tools:
                break  # Content was extracted, reset
            else:
                # Other tool used, continue checking
                pass

        if consecutive_scrolls >= 4:
            return StuckAnalysis(
                loop_type=LoopType.BROWSER_SCROLL_NO_PROGRESS,
                confidence=0.85,
                repeat_count=consecutive_scrolls,
                recovery_strategy=RecoveryStrategy.TAKE_CONCRETE_ACTION,
                details=f"Scrolled {consecutive_scrolls} times without extracting content - use browser_view to see results",
                affected_tools=["browser_scroll_down", "browser_scroll_up"],
            )

        return None

    def _detect_browser_click_failures(self) -> StuckAnalysis | None:
        """
        Detect: Repeated failed click attempts.

        Pattern: browser_click(index) → fail → browser_click(same_index) → fail
        """
        if len(self._tool_action_history) < 3:
            return None

        click_actions = [r for r in self._tool_action_history if r.tool_name == "browser_click"]

        if len(click_actions) < 3:
            return None

        # Check last 4 click attempts
        recent_clicks = click_actions[-4:]
        failed_clicks = [r for r in recent_clicks if not r.success]

        if len(failed_clicks) >= 3:
            # Check if same element being clicked
            same_target = len({r.args_hash for r in failed_clicks}) == 1

            return StuckAnalysis(
                loop_type=LoopType.BROWSER_CLICK_FAILURES,
                confidence=0.90 if same_target else 0.75,
                repeat_count=len(failed_clicks),
                recovery_strategy=RecoveryStrategy.TRY_ALTERNATIVE_APPROACH,
                details=(
                    "Clicking the same missing element repeatedly - use browser_view to get fresh element indices"
                    if same_target
                    else "Multiple click failures - elements may have changed, refresh with browser_view"
                ),
                affected_tools=["browser_click"],
            )

        return None

    def _detect_excessive_same_tool(self) -> StuckAnalysis | None:
        """Detect when the same tool is called excessively within a sliding window.

        Pattern: search → search → search → ... (8+ times in last 10 without a different tool)
        Catches rotating search patterns that hash-based detection misses.
        """
        window = 10
        threshold = 8

        if len(self._tool_action_history) < threshold:
            return None

        recent = list(self._tool_action_history)[-window:]

        # Count tool frequencies in the window
        tool_counts: dict[str, int] = {}
        for r in recent:
            tool_counts[r.tool_name] = tool_counts.get(r.tool_name, 0) + 1

        # Check if any single tool dominates the window
        for tool_name, count in tool_counts.items():
            if count >= threshold:
                # Verify these are search/browser tools (not legitimate repeated file reads)
                repetitive_tools = {
                    "info_search_web",
                    "wide_research",
                    "search",
                    "browser_navigate",
                    "browser_get_content",
                }
                if tool_name in repetitive_tools:
                    return StuckAnalysis(
                        loop_type=LoopType.EXCESSIVE_SAME_TOOL,
                        confidence=0.85,
                        repeat_count=count,
                        recovery_strategy=RecoveryStrategy.TRY_ALTERNATIVE_APPROACH,
                        details=(
                            f"Tool '{tool_name}' called {count} times in last {window} actions. "
                            "You likely have enough information — synthesize your findings and move on."
                        ),
                        affected_tools=[tool_name],
                    )

        return None

    def _detect_url_revisit_pattern(self) -> StuckAnalysis | None:
        """Detect when the agent revisits URLs already tracked in TaskState.

        Cross-references tool args against TaskState.visited_urls to catch
        the agent re-visiting pages it already extracted content from.
        """
        revisit_threshold = 3
        window = 10

        if len(self._tool_action_history) < 3:
            return None

        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            tsm = get_task_state_manager()
            visited = tsm.get_visited_urls()
            if not visited:
                return None
        except Exception:
            return None

        recent = list(self._tool_action_history)[-window:]
        url_tools = {"search", "browser_navigate", "browser_get_content"}

        # Count how many recent search/browser calls match
        # same args_hash (indicating same URL) appearing multiple times
        args_counts: dict[str, int] = {}
        for record in recent:
            if record.tool_name in url_tools:
                key = f"{record.tool_name}:{record.args_hash}"
                args_counts[key] = args_counts.get(key, 0) + 1

        # If any URL tool + args combo appears 3+ times, likely revisiting
        for key, count in args_counts.items():
            if count >= revisit_threshold:
                tool_name = key.split(":")[0]
                return StuckAnalysis(
                    loop_type=LoopType.URL_REVISIT_PATTERN,
                    confidence=0.80,
                    repeat_count=count,
                    recovery_strategy=RecoveryStrategy.TRY_ALTERNATIVE_APPROACH,
                    details=(
                        f"Same URL visited {count} times via '{tool_name}'. "
                        "Content hasn't changed — extract what you need and move to the next step."
                    ),
                    affected_tools=[tool_name],
                )

        return None

    def _detect_no_progress(self) -> StuckAnalysis | None:
        """Detect when no new key findings are added after many iterations.

        Checks TaskState.key_findings count vs iteration count to detect
        when the agent is spinning without making meaningful progress.
        """
        no_progress_threshold = 15

        if len(self._tool_action_history) < no_progress_threshold:
            return None

        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            tsm = get_task_state_manager()
            metrics = tsm.get_progress_metrics()
            if not metrics:
                return None

            # Check if stall count (no-progress counter) exceeds threshold
            if metrics.stall_count >= no_progress_threshold:
                return StuckAnalysis(
                    loop_type=LoopType.NO_PROGRESS,
                    confidence=0.75,
                    repeat_count=metrics.stall_count,
                    recovery_strategy=RecoveryStrategy.REPLAN_TASK,
                    details=(
                        f"No meaningful progress detected in {metrics.stall_count} consecutive actions. "
                        "Consider completing the current step with available information or moving on."
                    ),
                    affected_tools=[],
                )
        except Exception:
            logger.debug("Failed to analyze stuck state metrics", exc_info=True)

        return None

    def get_recovery_guidance(self) -> str:
        """
        Get detailed recovery guidance based on current stuck analysis.

        Returns context-specific advice based on the detected pattern type.
        """
        if not self._stuck_analysis:
            return self.get_recovery_prompt()

        guidance_map = {
            LoopType.RESPONSE_REPETITION: (
                "You are generating similar responses repeatedly.\n"
                "RECOVERY STEPS:\n"
                "1. Re-read the original task requirements\n"
                "2. Identify what specific progress is needed\n"
                "3. Take a different action - use a different tool or approach\n"
                "4. If blocked, clearly explain the blocker"
            ),
            LoopType.SEMANTIC_SIMILARITY: (
                "Your responses are semantically similar despite variations.\n"
                "RECOVERY STEPS:\n"
                "1. The current approach isn't working - try something fundamentally different\n"
                "2. If searching, use different queries or sources\n"
                "3. If coding, try an alternative implementation strategy\n"
                "4. Consider breaking the problem into smaller sub-tasks"
            ),
            LoopType.REPEATING_ACTION_OBSERVATION: (
                f"You're calling the same tool with the same arguments and getting the same result.\n"
                f"Affected tools: {', '.join(self._stuck_analysis.affected_tools)}\n"
                "RECOVERY STEPS:\n"
                "1. The result won't change - you already have this data\n"
                "2. Process the result you have instead of re-fetching\n"
                "3. If the result is incomplete, try different parameters\n"
                "4. Move on to the next step in your plan"
            ),
            LoopType.REPEATING_ACTION_ERROR: (
                f"The same tool call keeps failing.\n"
                f"Affected tools: {', '.join(self._stuck_analysis.affected_tools)}\n"
                "RECOVERY STEPS:\n"
                "1. ANALYZE the error message - what is it telling you?\n"
                "2. Common causes: missing dependencies, wrong parameters, permissions\n"
                "3. Try fixing the root cause before retrying\n"
                "4. If the tool is unavailable, use an alternative approach"
            ),
            LoopType.ALTERNATING_PATTERN: (
                f"You're oscillating between two approaches without progress.\n"
                f"Alternating between: {', '.join(self._stuck_analysis.affected_tools)}\n"
                "RECOVERY STEPS:\n"
                "1. STOP - this back-and-forth isn't productive\n"
                "2. Pick ONE approach and commit to it\n"
                "3. Or try a completely different third approach\n"
                "4. If truly stuck, ask the user for guidance"
            ),
            LoopType.TOOL_FAILURE_CASCADE: (
                f"Multiple tools are failing: {', '.join(self._stuck_analysis.affected_tools)}\n"
                "This suggests a systemic issue.\n"
                "RECOVERY STEPS:\n"
                "1. Check environment setup (dependencies, permissions, network)\n"
                "2. Verify the sandbox is functioning correctly\n"
                "3. Try simpler operations to diagnose the issue\n"
                "4. Escalate to the user - they may need to intervene"
            ),
            LoopType.MONOLOGUE: (
                "You're explaining or describing without taking action.\n"
                "RECOVERY STEPS:\n"
                "1. Stop explaining - START DOING\n"
                "2. Use tools to make concrete progress\n"
                "3. Users want results, not descriptions of what you'll do\n"
                "4. Execute the next logical action immediately"
            ),
            # Browser-specific recovery
            LoopType.BROWSER_SAME_PAGE_LOOP: (
                "You're navigating to the same URL repeatedly.\n"
                "RECOVERY STEPS:\n"
                "1. The page content is already loaded - don't re-navigate\n"
                "2. Use browser_view to see current page content\n"
                "3. Interact with elements (click, input) instead of reloading\n"
                "4. If page is stale, use browser_restart for a fresh session"
            ),
            LoopType.BROWSER_SCROLL_NO_PROGRESS: (
                "You're scrolling repeatedly without extracting content.\n"
                "RECOVERY STEPS:\n"
                "1. Use browser_view after scrolling to see new content\n"
                "2. Extract the information you need from the visible elements\n"
                "3. Scrolling loads content but you must VIEW it to use it\n"
                "4. Check scroll position - you may have reached the bottom already"
            ),
            LoopType.BROWSER_CLICK_FAILURES: (
                "Click attempts are failing - elements may not exist.\n"
                "RECOVERY STEPS:\n"
                "1. Use browser_view to get FRESH interactive element indices\n"
                "2. Element indices change after page updates - always refresh\n"
                "3. The element may be off-screen - try scrolling first\n"
                "4. Consider using browser_scroll_down if element is below viewport"
            ),
            # Enhanced detection recovery
            LoopType.EXCESSIVE_SAME_TOOL: (
                f"You've been calling the same tool excessively.\n"
                f"Affected tools: {', '.join(self._stuck_analysis.affected_tools)}\n"
                "RECOVERY STEPS:\n"
                "1. STOP searching/browsing — you likely have enough information\n"
                "2. Synthesize the information you've already gathered\n"
                "3. Write up your findings and complete the current step\n"
                "4. If you truly need more data, use DIFFERENT search queries"
            ),
            LoopType.URL_REVISIT_PATTERN: (
                "You're revisiting URLs you already extracted content from.\n"
                "RECOVERY STEPS:\n"
                "1. The content at these URLs hasn't changed\n"
                "2. Review the information you already extracted\n"
                "3. Visit NEW URLs or use different search queries\n"
                "4. If you have enough information, complete the current step"
            ),
            LoopType.NO_PROGRESS: (
                "No meaningful progress has been made in many iterations.\n"
                "RECOVERY STEPS:\n"
                "1. STOP and assess what you've accomplished so far\n"
                "2. Write a summary of findings with what you have\n"
                "3. Complete the current step — partial results are better than infinite loops\n"
                "4. If truly stuck, skip this step and move to the next one"
            ),
        }

        return guidance_map.get(self._stuck_analysis.loop_type, self.get_recovery_prompt())

    def get_analysis(self) -> StuckAnalysis | None:
        """Get the current stuck analysis if available."""
        return self._stuck_analysis

    def _hash_dict(self, d: dict[str, Any]) -> str:
        """Create a stable hash of a dictionary."""
        import json

        try:
            serialized = json.dumps(d, sort_keys=True, default=str)
            return hashlib.md5(serialized.encode(), usedforsecurity=False).hexdigest()[:16]
        except Exception:
            return hashlib.md5(str(d).encode(), usedforsecurity=False).hexdigest()[:16]

    def _hash_content(self, content: str) -> str:
        """Hash content for comparison."""
        if not content:
            return ""
        normalized = " ".join(content.split())[:1000]  # Limit to first 1000 chars
        return hashlib.md5(normalized.encode(), usedforsecurity=False).hexdigest()[:16]
