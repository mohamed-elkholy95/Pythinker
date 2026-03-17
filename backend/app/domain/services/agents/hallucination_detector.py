"""Tool Hallucination Detection

Detects when the LLM attempts to call non-existent tools and provides
helpful corrections with similar tool suggestions.

Also validates tool parameters against schemas to catch parameter
hallucinations (wrong types, missing required params, invalid values).
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


@dataclass
class HallucinationEvent:
    """Record of a tool hallucination attempt"""

    attempted_tool: str
    suggested_tools: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: str | None = None


@dataclass
class ToolValidationResult:
    """Result of validating a tool call (name + parameters)."""

    is_valid: bool
    """Whether the tool call is valid."""

    error_message: str | None = None
    """Error message if validation failed."""

    error_type: str | None = None
    """Type of error: 'tool_not_found', 'missing_params', 'invalid_type', etc."""

    suggestions: list[str] = field(default_factory=list)
    """Suggested corrections if validation failed."""


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

    # High-risk parameter patterns for semantic validation
    # Maps function_name -> param_name -> list of regex patterns
    HIGH_RISK_PATTERNS: ClassVar[dict[str, dict[str, list[str]]]] = {
        "file_write": {
            "file": [
                r"^/etc/",  # System config files
                r"^/usr/",  # System binaries
                r"^/bin/",  # System binaries
                r"^/sbin/",  # System admin binaries
                r"\.env$",  # Environment files
                r"/\.ssh/",  # SSH config
                r"/\.aws/",  # AWS credentials
            ],
            "path": [
                r"^/etc/",
                r"^/usr/",
                r"^/bin/",
                r"^/sbin/",
                r"\.env$",
                r"/\.ssh/",
                r"/\.aws/",
            ],
        },
        "shell_exec": {
            "command": [
                r"rm\s+-rf\s+/",  # Dangerous rm
                r"rm\s+-rf\s+\*",  # Dangerous rm wildcard
                r"(?<!\d)>\s*/dev/(?!null)",  # Device writes (allows 2>/dev/null, >/dev/null)
                r"sudo\s+",  # Privilege escalation
                r"chmod\s+777",  # Overly permissive
                r"mkfs\.",  # Filesystem format
                r"dd\s+if=.*of=/dev/",  # Direct disk write
                r":;\s*\(\)\s*\{",  # Fork bomb pattern
            ],
        },
        "browser_goto": {
            "url": [
                r"^file://",  # Local file access
                r"localhost.*admin",  # Admin panels
                r"127\.0\.0\.1.*admin",  # Admin panels
                r"0\.0\.0\.0",  # Bind to all interfaces
            ],
        },
        "execute_command": {
            "command": [
                r"rm\s+-rf\s+/",
                r"rm\s+-rf\s+\*",
                r"(?<!\d)>\s*/dev/(?!null)",  # Device writes (allows 2>/dev/null, >/dev/null)
                r"sudo\s+",
                r"chmod\s+777",
                r"mkfs\.",
                r"dd\s+if=.*of=/dev/",
                r":;\s*\(\)\s*\{",
            ],
        },
        "run_terminal_cmd": {
            "command": [
                r"rm\s+-rf\s+/",
                r"rm\s+-rf\s+\*",
                r"(?<!\d)>\s*/dev/(?!null)",  # Device writes (allows 2>/dev/null, >/dev/null)
                r"sudo\s+",
                r"chmod\s+777",
                r"mkfs\.",
                r"dd\s+if=.*of=/dev/",
                r":;\s*\(\)\s*\{",
            ],
        },
    }

    def __init__(
        self,
        available_tools: list[str],
        similarity_threshold: float = 0.6,
        max_suggestions: int = 3,
        hallucination_threshold: int = 3,
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

        # Tool schemas for parameter validation
        self._tool_schemas: dict[str, dict[str, Any]] = {}

    def update_available_tools(self, tools: list[str]) -> None:
        """Update the set of available tools.

        Call this when MCP tools are loaded or refreshed.
        """
        self.available_tools = set(tools)

    def update_tool_schemas(self, schemas: dict[str, dict[str, Any]]) -> None:
        """Update tool schemas for parameter validation.

        Args:
            schemas: Dict mapping tool names to their JSON schemas.
                     Each schema should have 'required' (list) and 'properties' (dict) keys.
        """
        self._tool_schemas = schemas

    def validate_parameter_semantics(
        self,
        function_name: str,
        param_name: str,
        param_value: Any,
        context: str | None = None,
    ) -> ToolValidationResult:
        """Validate parameter values are semantically reasonable.

        Detects parameters that are syntactically valid but semantically wrong
        or potentially dangerous.

        Examples of semantic issues:
        - file_path="/etc/passwd" when task is about user files
        - command="rm -rf /" which is dangerous in any context
        - url="file://..." for external research

        Args:
            function_name: Tool function being called
            param_name: Parameter being validated
            param_value: Value to validate
            context: Optional task context for relevance checking

        Returns:
            ToolValidationResult with is_valid and optional error details
        """
        # Get patterns for this function and parameter
        function_patterns = self.HIGH_RISK_PATTERNS.get(function_name, {})
        param_patterns = function_patterns.get(param_name, [])

        # Check value against each pattern
        value_str = str(param_value)
        for pattern in param_patterns:
            if re.search(pattern, value_str, re.IGNORECASE):
                context_msg = f" (task context: {context})" if context else ""
                return ToolValidationResult(
                    is_valid=False,
                    error_message=(
                        f"Parameter '{param_name}' value may be dangerous or inappropriate: "
                        f"'{param_value}' matches risk pattern '{pattern}'.{context_msg}"
                    ),
                    error_type="semantic_violation",
                    suggestions=[
                        f"Please confirm this action is intended for the current task{context_msg}",
                        "Consider using a safer alternative or more specific path/command",
                    ],
                )

        return ToolValidationResult(is_valid=True)

    def validate_tool_call(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        context: str | None = None,
    ) -> ToolValidationResult:
        """Validate both tool name AND parameters.

        This is the comprehensive validation method that should be used
        instead of just detect() for full anti-hallucination defense.

        Args:
            tool_name: The tool name the LLM attempted to call
            parameters: The parameters passed to the tool
            context: Optional context about what the LLM was trying to do

        Returns:
            ToolValidationResult with validation status and any errors
        """
        # First check if tool exists
        name_error = self.detect(tool_name, context)
        if name_error:
            similar = self._find_similar_tools(tool_name)
            return ToolValidationResult(
                is_valid=False,
                error_message=name_error,
                error_type="tool_not_found",
                suggestions=similar,
            )

        # Get schema for this tool
        schema = self._tool_schemas.get(tool_name)
        if not schema:
            # No schema available, can't validate parameters
            return ToolValidationResult(is_valid=True)

        # Check for missing required parameters
        required_params = schema.get("required", [])
        missing_params = [p for p in required_params if p not in parameters]

        if missing_params:
            return ToolValidationResult(
                is_valid=False,
                error_message=f"Missing required parameters for '{tool_name}': {missing_params}",
                error_type="missing_params",
                suggestions=[f"Required: {required_params}"],
            )

        # Check parameter types (basic type checking)
        properties = schema.get("properties", {})
        type_errors = []

        for param_name, param_value in parameters.items():
            if param_name not in properties:
                continue  # Skip unknown params for now

            expected_type = properties[param_name].get("type")
            if not expected_type:
                continue

            actual_type = self._get_json_type(param_value)
            if not self._types_compatible(expected_type, actual_type):
                type_errors.append(f"'{param_name}': expected {expected_type}, got {actual_type}")

        if type_errors:
            return ToolValidationResult(
                is_valid=False,
                error_message=f"Parameter type errors for '{tool_name}': {'; '.join(type_errors)}",
                error_type="invalid_type",
                suggestions=["Check parameter types against schema"],
            )

        # Check semantic validity of parameters
        for param_name, param_value in parameters.items():
            semantic_result = self.validate_parameter_semantics(
                function_name=tool_name,
                param_name=param_name,
                param_value=param_value,
                context=context,
            )
            if not semantic_result.is_valid:
                return semantic_result

        return ToolValidationResult(is_valid=True)

    def _get_json_type(self, value: Any) -> str:
        """Get the JSON Schema type for a Python value."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "unknown"

    def _types_compatible(self, expected: str, actual: str) -> bool:
        """Check if actual type is compatible with expected JSON Schema type."""
        if expected == actual:
            return True
        # 'number' accepts both int and float
        if expected == "number" and actual in ("integer", "number"):
            return True
        # Some schemas use 'integer' but 'number' is also ok
        return expected == "integer" and actual == "number"

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
        event = HallucinationEvent(attempted_tool=tool_name, suggested_tools=similar, context=context)
        self.hallucination_history.append(event)

        # Limit history size
        if len(self.hallucination_history) > 100:
            self.hallucination_history = self.hallucination_history[-50:]

        logger.warning(
            f"Tool hallucination detected: '{tool_name}' (suggestions: {similar}, count: {self.hallucination_count})"
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
        sorted_tools = sorted(similarities.keys(), key=lambda t: similarities[t], reverse=True)

        return sorted_tools[: self.max_suggestions]

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
        sample_tools = sorted(self.available_tools)[:10]
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
        sample_tools = sorted(self.available_tools)[:15]

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

    def get_statistics(self) -> dict[str, Any]:
        """Get hallucination statistics.

        Returns:
            Dictionary with hallucination stats
        """
        if not self.hallucination_history:
            return {"total_hallucinations": 0, "unique_hallucinations": 0, "most_common": [], "recovery_rate": 1.0}

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
            "current_streak": self.hallucination_count,
        }
