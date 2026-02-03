"""Command Registry for Superpowers-style /command invocation.

Maps user-friendly commands like `/brainstorm`, `/write-plan`, `/tdd`
to skill invocations.

Example:
    /brainstorm → invokes "brainstorming" skill
    /write-plan → invokes "writing-plans" skill
    /tdd → invokes "test-driven-development" skill
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


# Built-in Superpowers command mappings
SUPERPOWERS_COMMANDS: list[CommandMapping] = [
    # Design & Planning
    CommandMapping(
        command="brainstorm",
        skill_id="brainstorming",
        description="Interactive design refinement - explore ideas before implementation",
        aliases=["design", "plan-design"],
    ),
    CommandMapping(
        command="write-plan",
        skill_id="writing-plans",
        description="Create detailed implementation plan with bite-sized tasks",
        aliases=["plan", "create-plan"],
    ),
    CommandMapping(
        command="execute-plan",
        skill_id="executing-plans",
        description="Execute implementation plan in batches with checkpoints",
        aliases=["exec-plan", "run-plan"],
    ),
    # Development
    CommandMapping(
        command="tdd",
        skill_id="test-driven-development",
        description="Test-Driven Development - RED-GREEN-REFACTOR cycle",
        aliases=["test-first"],
    ),
    CommandMapping(
        command="debug",
        skill_id="systematic-debugging",
        description="Systematic debugging - 4-phase root cause process",
        aliases=["fix-bug", "troubleshoot"],
    ),
    CommandMapping(
        command="subagent",
        skill_id="subagent-driven-development",
        description="Dispatch fresh subagent per task with two-stage review",
        aliases=["subagent-dev"],
    ),
    CommandMapping(
        command="parallel",
        skill_id="dispatching-parallel-agents",
        description="Concurrent subagent workflows for parallel execution",
        aliases=["parallel-agents"],
    ),
    # Git Workflow
    CommandMapping(
        command="worktree",
        skill_id="using-git-worktrees",
        description="Create isolated workspace on new branch",
        aliases=["git-worktree", "new-worktree"],
    ),
    CommandMapping(
        command="finish-branch",
        skill_id="finishing-a-development-branch",
        description="Verify tests, present merge/PR options, clean up",
        aliases=["complete-branch", "merge-branch"],
    ),
    # Code Review
    CommandMapping(
        command="request-review",
        skill_id="requesting-code-review",
        description="Review code against plan, report issues by severity",
        aliases=["code-review", "review"],
    ),
    CommandMapping(
        command="receive-review",
        skill_id="receiving-code-review",
        description="Respond to code review feedback systematically",
        aliases=["handle-feedback"],
    ),
    # Verification
    CommandMapping(
        command="verify",
        skill_id="verification-before-completion",
        description="Ensure fix/feature actually works before marking complete",
        aliases=["check", "validate"],
    ),
    # Meta
    CommandMapping(
        command="superpowers",
        skill_id="using-superpowers",
        description="Introduction to the Superpowers skills system",
        aliases=["help-skills", "skills-help"],
    ),
    CommandMapping(
        command="write-skill",
        skill_id="writing-skills",
        description="Create new skills following best practices",
        aliases=["create-skill", "new-skill"],
    ),
]


class CommandRegistry:
    """Registry for mapping commands to skill invocations."""

    def __init__(self) -> None:
        self._command_map: dict[str, str] = {}  # command -> skill_id
        self._skill_commands: dict[str, str] = {}  # skill_id -> primary command
        self._command_help: dict[str, str] = {}  # command -> description
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure registry is initialized with Superpowers commands."""
        if self._initialized:
            return

        for mapping in SUPERPOWERS_COMMANDS:
            # Register primary command
            self._command_map[mapping.command] = mapping.skill_id
            self._skill_commands[mapping.skill_id] = mapping.command
            self._command_help[mapping.command] = mapping.description

            # Register aliases
            for alias in mapping.aliases:
                self._command_map[alias] = mapping.skill_id
                self._command_help[alias] = f"{mapping.description} (alias for /{mapping.command})"

        self._initialized = True
        logger.info(
            f"✓ CommandRegistry initialized with {len(SUPERPOWERS_COMMANDS)} commands "
            f"({len(self._command_map)} total including aliases)"
        )

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

        for mapping in SUPERPOWERS_COMMANDS:
            if mapping.skill_id not in seen_skills:
                commands.append((mapping.command, mapping.skill_id, mapping.description))
                seen_skills.add(mapping.skill_id)

        return commands

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
