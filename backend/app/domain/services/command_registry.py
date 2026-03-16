"""Command Registry for /command invocation.

Maps user-friendly commands to skill invocations or session-state
mutations.  Supports typed arguments with choices and optional
inline-keyboard menus (OpenClaw ``commands-registry.data.ts`` parity).

Custom commands can be registered programmatically via register_command().
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class CommandScope(str, Enum):
    """Where a command is available (OpenClaw scope field)."""

    NATIVE = "native"  # Only registered as a Telegram bot menu command
    TEXT = "text"  # Only matched as /command in message body text
    BOTH = "both"  # Registered in both paths


@dataclass
class CommandArgChoice:
    """A single valid value for a command argument."""

    value: str
    label: str | None = None  # Human-friendly label (defaults to value)

    def display(self) -> str:
        return self.label or self.value


@dataclass
class CommandArg:
    """Typed argument definition for a command."""

    name: str
    description: str = ""
    required: bool = False
    choices: list[CommandArgChoice] | None = None  # None = free-form text


@dataclass
class CommandMapping:
    """Maps a command to a skill invocation or session mutation."""

    command: str  # Command name (without leading slash)
    skill_id: str  # Skill to invoke (or "builtin:<name>" for session commands)
    description: str  # Help text
    aliases: list[str] = field(default_factory=list)
    args: list[CommandArg] = field(default_factory=list)
    scope: CommandScope = CommandScope.BOTH
    args_menu: str | None = None  # "auto" or arg name to display as inline menu
    category: str = "general"  # session | options | status | management | tools


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CommandRegistry:
    """Registry for mapping commands to skill invocations."""

    def __init__(self) -> None:
        self._command_map: dict[str, str] = {}  # command -> skill_id
        self._skill_commands: dict[str, str] = {}  # skill_id -> primary command
        self._command_help: dict[str, str] = {}  # command -> description
        self._commands: dict[str, CommandMapping] = {}  # command -> full mapping
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure registry is initialized (empty by default)."""
        if self._initialized:
            return

        self._initialized = True
        logger.info("✓ CommandRegistry initialized (no default commands)")

    # -----------------------------------------------------------------------
    # Parsing
    # -----------------------------------------------------------------------

    def parse_command(self, message: str) -> tuple[str | None, str]:
        """Parse a message for command syntax.

        Returns:
            Tuple of (skill_id, remaining_message)
            - skill_id: Skill to invoke (None if no command found)
            - remaining_message: Rest of message after command
        """
        self._ensure_initialized()

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

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def get_skill_command(self, skill_id: str) -> str | None:
        """Get the primary command for a skill."""
        self._ensure_initialized()
        return self._skill_commands.get(skill_id)

    def get_available_commands(self) -> list[tuple[str, str, str]]:
        """Get list of available commands with help text.

        Returns:
            List of (command, skill_id, description) tuples
        """
        self._ensure_initialized()

        commands = []
        seen_skills: set[str] = set()

        for command, skill_id in self._command_map.items():
            if skill_id not in seen_skills and command == self._skill_commands.get(skill_id):
                description = self._command_help.get(command, "")
                commands.append((command, skill_id, description))
                seen_skills.add(skill_id)

        return commands

    def get_command_map(self) -> dict[str, str]:
        """Get full mapping of command/alias -> skill_id for slash command detection."""
        self._ensure_initialized()
        return dict(self._command_map)

    def get_command_help(self, command: str) -> str | None:
        """Get help text for a command."""
        self._ensure_initialized()
        return self._command_help.get(command.lower())

    def get_command_definition(self, command: str) -> CommandMapping | None:
        """Get the full command definition including args and scope."""
        self._ensure_initialized()
        return self._commands.get(command.lower())

    def resolve_args_menu(self, command: str) -> list[CommandArgChoice] | None:
        """Resolve the inline argument menu for a command.

        Returns the list of choices if the command has an args_menu
        configuration, or None if no menu should be displayed.
        """
        mapping = self.get_command_definition(command)
        if mapping is None or not mapping.args_menu:
            return None

        if mapping.args_menu == "auto":
            # Use the first arg's choices
            for arg in mapping.args:
                if arg.choices:
                    return arg.choices
            return None

        # Use the named arg's choices
        for arg in mapping.args:
            if arg.name == mapping.args_menu and arg.choices:
                return arg.choices

        return None

    # -----------------------------------------------------------------------
    # Registration
    # -----------------------------------------------------------------------

    def register_command(
        self,
        command: str,
        skill_id: str,
        description: str,
        aliases: list[str] | None = None,
        *,
        args: list[CommandArg] | None = None,
        scope: CommandScope = CommandScope.BOTH,
        args_menu: str | None = None,
        category: str = "general",
    ) -> None:
        """Register a custom command mapping."""
        self._ensure_initialized()

        command = command.lower()
        self._command_map[command] = skill_id
        self._skill_commands[skill_id] = command
        self._command_help[command] = description

        mapping = CommandMapping(
            command=command,
            skill_id=skill_id,
            description=description,
            aliases=list(aliases or []),
            args=list(args or []),
            scope=scope,
            args_menu=args_menu,
            category=category,
        )
        self._commands[command] = mapping

        for alias in aliases or []:
            alias = alias.lower()
            self._command_map[alias] = skill_id
            self._command_help[alias] = f"{description} (alias for /{command})"
            self._commands[alias] = mapping

        logger.info(f"Registered command /{command} → skill '{skill_id}'")


# Module-level singleton
_command_registry: CommandRegistry | None = None


def get_command_registry() -> CommandRegistry:
    """Get the singleton command registry instance."""
    global _command_registry
    if _command_registry is None:
        _command_registry = CommandRegistry()
    return _command_registry
