"""
Stuck detection for agent execution loops.

Detects when an agent is producing repetitive responses and provides
mechanisms to break out of stuck states.
"""

import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ResponseRecord:
    """Record of an LLM response for stuck detection"""
    content_hash: str
    timestamp: datetime
    tool_calls: Optional[List[str]] = None
    content_preview: str = ""


class StuckDetector:
    """
    Detects when an agent is stuck in a repetitive loop.

    Tracks LLM response patterns using content hashes and detects
    when the agent produces too many similar responses in succession.
    """

    def __init__(
        self,
        window_size: int = 5,
        threshold: int = 3,
        similarity_threshold: float = 0.9
    ):
        """
        Initialize the stuck detector.

        Args:
            window_size: Number of recent responses to track
            threshold: Number of similar responses to trigger stuck detection
            similarity_threshold: Minimum similarity ratio to consider responses similar
        """
        self._window_size = window_size
        self._threshold = threshold
        self._similarity_threshold = similarity_threshold
        self._response_history: deque[ResponseRecord] = deque(maxlen=window_size)
        self._stuck_count = 0
        self._recovery_attempts = 0
        self._max_recovery_attempts = 3

    def track_response(self, response: Dict[str, Any]) -> bool:
        """
        Track a new LLM response and check if agent is stuck.

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

        record = ResponseRecord(
            content_hash=content_hash,
            timestamp=datetime.now(),
            tool_calls=tool_names,
            content_preview=content[:100] if content else ""
        )

        self._response_history.append(record)

        # Check for stuck pattern
        is_stuck = self._detect_stuck_pattern()

        if is_stuck:
            self._stuck_count += 1
            logger.warning(
                f"Stuck pattern detected (count: {self._stuck_count}). "
                f"Similar responses in last {self._window_size} turns."
            )
        else:
            # Reset stuck count if pattern broken
            if self._stuck_count > 0:
                logger.info("Stuck pattern broken, resetting counter")
                self._stuck_count = 0
                self._recovery_attempts = 0

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

        # Include tool call structure
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                func_name = func.get("name", "")
                # Include function name and argument keys (not values, as values might vary slightly)
                args = func.get("arguments", "")
                if isinstance(args, str):
                    try:
                        import json
                        args_dict = json.loads(args)
                        arg_keys = sorted(args_dict.keys()) if isinstance(args_dict, dict) else []
                    except:
                        arg_keys = []
                else:
                    arg_keys = sorted(args.keys()) if isinstance(args, dict) else []

                hash_components.append(f"{func_name}:{','.join(arg_keys)}")

        combined = "|".join(hash_components)
        return hashlib.md5(combined.encode()).hexdigest()

    def _detect_stuck_pattern(self) -> bool:
        """
        Detect if recent responses show a stuck pattern.

        Returns True if threshold number of similar responses detected.
        """
        if len(self._response_history) < self._threshold:
            return False

        # Count occurrences of each hash in the window
        hash_counts: Dict[str, int] = {}
        for record in self._response_history:
            hash_counts[record.content_hash] = hash_counts.get(record.content_hash, 0) + 1

        # Check if any hash appears threshold times or more
        max_count = max(hash_counts.values()) if hash_counts else 0
        return max_count >= self._threshold

    def is_stuck(self) -> bool:
        """Check if currently in stuck state"""
        return self._stuck_count > 0

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
        logger.debug("Stuck detector reset")

    def get_stats(self) -> Dict[str, Any]:
        """Get current detector statistics"""
        return {
            "window_size": self._window_size,
            "threshold": self._threshold,
            "responses_tracked": len(self._response_history),
            "stuck_count": self._stuck_count,
            "recovery_attempts": self._recovery_attempts,
            "is_stuck": self.is_stuck(),
            "can_recover": self.can_attempt_recovery()
        }
