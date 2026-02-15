"""Command Registry for /command invocation.

Maps user-friendly commands to skill invocations.
Custom commands can be registered programmatically via register_command().
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandMapping:
    """Maps a command to a skill invocation."""

    command: str  # Command name (without leading slash)
    skill_id: str  # Skill to invoke
    description: str  # Help text
    aliases: list[str]  # Alternative command names


# Command mappings start empty - register custom commands via register_command()


class CommandRegistry:
    """Registry for mapping commands to skill invocations."""

    def __init__(self) -> None:
        self._command_map: dict[str, str] = {}  # command -> skill_id
        self._skill_commands: dict[str, str] = {}  # skill_id -> primary command
        self._command_help: dict[str, str] = {}  # command -> description
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure registry is initialized (empty by default)."""
        if self._initialized:
            return

        self._initialized = True
        logger.info("✓ CommandRegistry initialized (no default commands)")

    def parse_command(self, message: str) -> tuple[str | None, str]:
        """Parse a message for command syntax.

        Args:
            message: User message that may start with /command

        Returns:
            Tuple of (skill_id, remaining_message)
            - skill_id: Skill to invoke (None if no command found)
            - remaining_message: Rest of message after command
        """
        self._ensure_initialized()

        # Match /command at start of message
        # Pattern: /command-name followed by space or end of string
        pattern = r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$"
        match = re.match(pattern, message.strip(), re.DOTALL)

        if not match:
            return None, message

        command = match.group(1).lower()
        remaining = match.group(2) or ""

        skill_id = self._command_map.get(command)
        if skill_id:
            logger.info(f"Parsed command /{command} → skill '{skill_id}'")
            return skill_id, remaining.strip()

        logger.debug(f"Unknown command: /{command}")
        return None, message

    def get_skill_command(self, skill_id: str) -> str | None:
        """Get the primary command for a skill.

        Args:
            skill_id: Skill ID

        Returns:
            Primary command name (without leading slash), or None
        """
        self._ensure_initialized()
        return self._skill_commands.get(skill_id)

    def get_available_commands(self) -> list[tuple[str, str, str]]:
        """Get list of available commands with help text.

        Returns:
            List of (command, skill_id, description) tuples
        """
        self._ensure_initialized()

        commands = []
        seen_skills = set()

        # Build list from registered commands
        for command, skill_id in self._command_map.items():
            if skill_id not in seen_skills and command == self._skill_commands.get(skill_id):
                # Only include primary commands, not aliases
                description = self._command_help.get(command, "")
                commands.append((command, skill_id, description))
                seen_skills.add(skill_id)

        return commands

    def get_command_map(self) -> dict[str, str]:
        """Get full mapping of command/alias -> skill_id for slash command detection.

        Includes both primary commands and aliases so frontend can identify
        any valid /command string and resolve it to the correct skill.

        Returns:
            Dict mapping command name (lowercase, no leading slash) to skill_id
        """
        self._ensure_initialized()
        return dict(self._command_map)

    def get_command_help(self, command: str) -> str | None:
        """Get help text for a command.

        Args:
            command: Command name (without leading slash)

        Returns:
            Help text, or None if command not found
        """
        self._ensure_initialized()
        return self._command_help.get(command.lower())

    def register_command(
        self,
        command: str,
        skill_id: str,
        description: str,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a custom command mapping.

        Args:
            command: Command name (without leading slash)
            skill_id: Skill to invoke
            description: Help text
            aliases: Alternative command names
        """
        self._ensure_initialized()

        command = command.lower()
        self._command_map[command] = skill_id
        self._skill_commands[skill_id] = command
        self._command_help[command] = description

        for alias in aliases or []:
            alias = alias.lower()
            self._command_map[alias] = skill_id
            self._command_help[alias] = f"{description} (alias for /{command})"

        logger.info(f"Registered command /{command} → skill '{skill_id}'")


# Module-level singleton
_command_registry: CommandRegistry | None = None


def get_command_registry() -> CommandRegistry:
    """Get the singleton command registry instance."""
    global _command_registry
    if _command_registry is None:
        _command_registry = CommandRegistry()
    return _command_registry
