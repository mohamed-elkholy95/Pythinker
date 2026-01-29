"""Tool Hallucination Detection

Detects when the LLM attempts to call non-existent tools and provides
helpful corrections with similar tool suggestions.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class HallucinationEvent:
    """Record of a tool hallucination attempt"""
    attempted_tool: str
    suggested_tools: list[str]
    timestamp: datetime = field(default_factory=datetime.now)
    context: str | None = None


class ToolHallucinationDetector:
    """Detects and handles tool hallucinations in LLM responses.

    When the LLM attempts to call a tool that doesn't exist, this detector:
    1. Records the hallucination attempt
    2. Finds similar tools that might be what the LLM intended
    3. Provides a correction message for the agent to retry

    Usage:
        detector = ToolHallucinationDetector(available_tools)
        correction = detector.detect("non_existent_tool")
        if correction:
            # Tool was hallucinated, use correction message
            return ToolResult(success=False, error=correction)
    """

    def __init__(
        self,
        available_tools: list[str],
        similarity_threshold: float = 0.6,
        max_suggestions: int = 3,
        hallucination_threshold: int = 3
    ):
        """Initialize the hallucination detector.

        Args:
            available_tools: List of valid tool names
            similarity_threshold: Minimum similarity ratio for suggestions (0.0-1.0)
            max_suggestions: Maximum number of similar tools to suggest
            hallucination_threshold: Number of hallucinations before injecting correction prompt
        """
        self.available_tools: set[str] = set(available_tools)
        self.similarity_threshold = similarity_threshold
        self.max_suggestions = max_suggestions
        self.hallucination_threshold = hallucination_threshold

        # Track hallucination history
        self.hallucination_count = 0
        self.hallucination_history: list[HallucinationEvent] = []

    def update_available_tools(self, tools: list[str]) -> None:
        """Update the set of available tools.

        Call this when MCP tools are loaded or refreshed.
        """
        self.available_tools = set(tools)

    def detect(self, tool_name: str, context: str | None = None) -> str | None:
        """Detect if a tool call is a hallucination and return correction message.

        Args:
            tool_name: The tool name the LLM attempted to call
            context: Optional context about what the LLM was trying to do

        Returns:
            Correction message if tool is hallucinated, None if valid
        """
        # Valid tool - no hallucination
        if tool_name in self.available_tools:
            return None

        self.hallucination_count += 1

        # Find similar tools
        similar = self._find_similar_tools(tool_name)

        # Record the event
        event = HallucinationEvent(
            attempted_tool=tool_name,
            suggested_tools=similar,
            context=context
        )
        self.hallucination_history.append(event)

        # Limit history size
        if len(self.hallucination_history) > 100:
            self.hallucination_history = self.hallucination_history[-50:]

        logger.warning(
            f"Tool hallucination detected: '{tool_name}' "
            f"(suggestions: {similar}, count: {self.hallucination_count})"
        )

        # Generate correction message
        return self._generate_correction(tool_name, similar)

    def _find_similar_tools(self, name: str) -> list[str]:
        """Find tools with similar names using sequence matching.

        Args:
            name: The hallucinated tool name

        Returns:
            List of similar valid tool names, sorted by similarity
        """
        similarities: dict[str, float] = {}

        name_lower = name.lower()

        for tool in self.available_tools:
            # Calculate similarity ratio
            ratio = SequenceMatcher(None, name_lower, tool.lower()).ratio()

            # Also check for substring matches
            if name_lower in tool.lower() or tool.lower() in name_lower:
                ratio = max(ratio, 0.7)  # Boost substring matches

            if ratio >= self.similarity_threshold:
                similarities[tool] = ratio

        # Sort by similarity and return top matches
        sorted_tools = sorted(
            similarities.keys(),
            key=lambda t: similarities[t],
            reverse=True
        )

        return sorted_tools[:self.max_suggestions]

    def _generate_correction(self, tool_name: str, similar: list[str]) -> str:
        """Generate a helpful correction message.

        Args:
            tool_name: The hallucinated tool name
            similar: List of similar valid tools

        Returns:
            Correction message for the agent
        """
        if similar:
            suggestions = ", ".join(f"'{t}'" for t in similar)
            return (
                f"Tool '{tool_name}' does not exist. "
                f"Did you mean one of these: {suggestions}? "
                f"Please use the exact tool name from the available tools list."
            )

        # No similar tools found - provide a subset of available tools
        sample_tools = sorted(list(self.available_tools))[:10]
        tools_list = ", ".join(f"'{t}'" for t in sample_tools)

        return (
            f"Tool '{tool_name}' does not exist. "
            f"Available tools include: {tools_list}. "
            f"Please check the available tools and use an exact tool name."
        )

    def should_inject_correction_prompt(self) -> bool:
        """Check if we should inject a correction prompt to help the LLM.

        Returns True after multiple consecutive hallucinations to help
        the LLM understand what tools are actually available.
        """
        return self.hallucination_count >= self.hallucination_threshold

    def get_correction_prompt(self) -> str:
        """Get a correction prompt to inject after multiple hallucinations.

        Returns:
            A prompt explaining the available tools
        """
        recent_attempts = [e.attempted_tool for e in self.hallucination_history[-5:]]
        sample_tools = sorted(list(self.available_tools))[:15]

        return (
            f"IMPORTANT: You have attempted to use non-existent tools: {recent_attempts}. "
            f"Please only use tools from this list: {sample_tools}. "
            f"If you need a capability not listed, explain what you're trying to do."
        )

    def reset(self) -> None:
        """Reset the hallucination counter.

        Call this at the start of a new task or after successful recovery.
        """
        self.hallucination_count = 0

    def get_statistics(self) -> dict[str, any]:
        """Get hallucination statistics.

        Returns:
            Dictionary with hallucination stats
        """
        if not self.hallucination_history:
            return {
                "total_hallucinations": 0,
                "unique_hallucinations": 0,
                "most_common": [],
                "recovery_rate": 1.0
            }

        attempted = [e.attempted_tool for e in self.hallucination_history]
        unique = set(attempted)

        # Count occurrences
        counts = {}
        for tool in attempted:
            counts[tool] = counts.get(tool, 0) + 1

        most_common = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_hallucinations": len(self.hallucination_history),
            "unique_hallucinations": len(unique),
            "most_common": most_common,
            "current_streak": self.hallucination_count
        }
