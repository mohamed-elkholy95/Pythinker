"""Validator for custom skill content.

This module provides validation and sanitization for user-created skills
to prevent prompt injection and ensure content quality.
"""

import re
from typing import ClassVar

from app.domain.models.skill import Skill


class SkillValidator:
    """Validates and sanitizes custom skill content.

    Performs security checks to prevent prompt injection attacks
    and validates that skill configurations are within acceptable limits.
    """

    # Patterns that could indicate prompt injection attempts
    BLOCKED_PATTERNS: ClassVar[list[str]] = [
        r"ignore.*previous.*instructions",
        r"ignore.*system.*prompt",
        r"you.*are.*now",
        r"forget.*everything",
        r"jailbreak",
        r"disregard.*instructions",
        r"override.*system",
        r"new.*persona",
        r"pretend.*to.*be",
        r"act.*as.*if",
        r"bypass.*safety",
        r"ignore.*guidelines",
        r"discard.*rules",
    ]

    # Maximum length for system prompt addition
    MAX_PROMPT_LENGTH = 4000

    # Maximum number of tools a skill can reference
    MAX_TOOLS = 15

    # Tools that custom skills are allowed to use
    ALLOWED_TOOLS: ClassVar[set[str]] = {
        # Search tools
        "info_search_web",
        # Browser tools
        "browser_navigate",
        "browser_view",
        "browser_get_content",
        "browser_click",
        "browser_input",
        "browser_scroll_down",
        "browser_scroll_up",
        "browser_restart",
        "browser_press_key",
        "browser_select_option",
        "browser_move_mouse",
        "browser_console_exec",
        "browser_console_view",
        "browser_agent_run",
        "browser_agent_extract",
        # File tools
        "file_read",
        "file_write",
        "file_str_replace",
        "file_find_in_content",
        "file_find_by_name",
        # Code execution
        "code_execute",
        "code_execute_python",
        "code_execute_javascript",
        # Shell
        "shell_exec",
        # Communication
        "message_notify_user",
        "message_ask_user",
        # Idle/standby
        "idle_standby",
    }

    @classmethod
    def validate(cls, skill: Skill) -> list[str]:
        """Validate a custom skill.

        Performs all validation checks on the skill and returns a list
        of error messages. An empty list means validation passed.

        Args:
            skill: The Skill to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # Check name
        if not skill.name or len(skill.name.strip()) < 2:
            errors.append("Skill name must be at least 2 characters")
        elif len(skill.name) > 100:
            errors.append("Skill name must be less than 100 characters")

        # Check description
        if not skill.description or len(skill.description.strip()) < 10:
            errors.append("Description must be at least 10 characters")
        elif len(skill.description) > 500:
            errors.append("Description must be less than 500 characters")

        # Check system prompt length
        if skill.system_prompt_addition:
            if len(skill.system_prompt_addition) > cls.MAX_PROMPT_LENGTH:
                errors.append(f"System prompt too long (max {cls.MAX_PROMPT_LENGTH} characters)")

            # Check for blocked patterns (prompt injection)
            prompt_lower = skill.system_prompt_addition.lower()
            for pattern in cls.BLOCKED_PATTERNS:
                if re.search(pattern, prompt_lower, re.IGNORECASE):
                    errors.append("System prompt contains blocked content that may be unsafe")
                    break

        # Validate tools
        all_tools = set(skill.required_tools + skill.optional_tools)

        # Check for invalid tools
        invalid_tools = all_tools - cls.ALLOWED_TOOLS
        if invalid_tools:
            errors.append(f"Invalid tools: {', '.join(sorted(invalid_tools))}")

        # Check tool count
        if len(all_tools) > cls.MAX_TOOLS:
            errors.append(f"Too many tools specified ({len(all_tools)} > {cls.MAX_TOOLS})")

        # Check for duplicate tools
        all_tools_list = skill.required_tools + skill.optional_tools
        if len(all_tools_list) != len(set(all_tools_list)):
            errors.append("Duplicate tools found in required and optional lists")

        return errors

    @classmethod
    def sanitize_prompt(cls, prompt: str) -> str:
        """Sanitize a system prompt addition.

        Removes or escapes potentially dangerous content while preserving
        the intended functionality.

        Args:
            prompt: The raw prompt text

        Returns:
            Sanitized prompt text
        """
        if not prompt:
            return ""

        # Strip leading/trailing whitespace
        sanitized = prompt.strip()

        # Normalize whitespace (collapse multiple spaces/newlines)
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        sanitized = re.sub(r" {2,}", " ", sanitized)

        # Truncate if too long
        if len(sanitized) > cls.MAX_PROMPT_LENGTH:
            sanitized = sanitized[: cls.MAX_PROMPT_LENGTH]
            # Try to cut at a sentence boundary
            last_period = sanitized.rfind(".")
            if last_period > cls.MAX_PROMPT_LENGTH * 0.8:
                sanitized = sanitized[: last_period + 1]

        return sanitized

    @classmethod
    def is_safe_prompt(cls, prompt: str) -> bool:
        """Check if a prompt is safe (no blocked patterns).

        Args:
            prompt: The prompt text to check

        Returns:
            True if safe, False if contains blocked content
        """
        if not prompt:
            return True

        prompt_lower = prompt.lower()
        return all(not re.search(pattern, prompt_lower, re.IGNORECASE) for pattern in cls.BLOCKED_PATTERNS)
