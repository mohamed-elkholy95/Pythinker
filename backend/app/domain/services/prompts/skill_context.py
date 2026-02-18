"""Skill Context Builder for System Prompt Injection.

This module provides functions to build skill-based context additions
that are injected into agent system prompts when skills are enabled.

Implements Claude's skills architecture patterns:
- Dynamic context injection (!command syntax)
- Tool restrictions based on skill configuration
- Argument substitution ($ARGUMENTS, $1, $2, etc.)

CRITICAL: This is Phase 3 of the Custom Skills implementation.
Without this injection, skill system_prompt_additions are NOT used by agents.

SECURITY: Dynamic context execution is restricted to OFFICIAL skills only
and uses a command allowlist to prevent arbitrary code execution.
"""

import asyncio
import html
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.skill import Skill, SkillSource

logger = logging.getLogger(__name__)

# Optional skills-ref integration for standard <available_skills> XML generation
try:
    from skills_ref.prompt import to_prompt as _agentskills_to_prompt

    _AGENTSKILLS_PROMPT_AVAILABLE = True
except ImportError:
    _AGENTSKILLS_PROMPT_AVAILABLE = False


# Allowlist of safe commands for dynamic context expansion
# Only these executables can be invoked via !command syntax
ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        # Version/info commands (read-only, safe)
        "date",
        "whoami",
        "hostname",
        "uname",
        "pwd",
        "echo",
        # Git commands (read-only operations)
        "git",
        # Package managers (version/list only — validated by BLOCKED_SUBCOMMANDS)
        "npm",
        "pip",
        "pip3",
        # System info
        "which",
        # NOTE: python, python3, node intentionally excluded — they accept
        # arbitrary script file paths as arguments (e.g. `python /tmp/evil.py`),
        # which bypasses the BLOCKED_SUBCOMMANDS check. Use `python --version`
        # needs can be covered by `which python` or system info commands instead.
    }
)

# Subcommands that are explicitly blocked even for allowed commands
BLOCKED_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        # Destructive git operations
        "push",
        "reset",
        "clean",
        "checkout",
        # Package modification
        "install",
        "uninstall",
        "remove",
        "update",
        "upgrade",
        # Execution
        "exec",
        "run",
        "eval",
        # Arbitrary code execution flag
        "-c",
    }
)

# Shell metacharacters that indicate injection attempts
DANGEROUS_PATTERNS: tuple[str, ...] = (
    ";",
    "&&",
    "||",
    "|",
    "`",
    "$(",
    "${",
    ">",
    "<",
    ">>",
    "<<",
    "\n",
    "\r",
)


def _validate_command(command: str) -> tuple[bool, str, list[str]]:
    """Validate and parse a command for safe execution.

    Args:
        command: The raw command string

    Returns:
        Tuple of (is_valid, error_message, parsed_args)
    """
    # Check for dangerous shell metacharacters
    for pattern in DANGEROUS_PATTERNS:
        if pattern in command:
            return False, f"Command contains forbidden pattern: {pattern!r}", []

    # Parse the command safely
    try:
        args = shlex.split(command)
    except ValueError as e:
        return False, f"Invalid command syntax: {e}", []

    if not args:
        return False, "Empty command", []

    # Get the base executable (handle paths like /usr/bin/git)
    executable = args[0].split("/")[-1]

    # Check if executable is in allowlist
    if executable not in ALLOWED_COMMANDS:
        return False, f"Command '{executable}' is not in allowlist", []

    # Check for blocked subcommands
    if len(args) > 1:
        subcommand = args[1].lower()
        if subcommand in BLOCKED_SUBCOMMANDS:
            return False, f"Subcommand '{subcommand}' is blocked for security", []

    return True, "", args


async def expand_dynamic_context(content: str, skill_source: "SkillSource | None" = None) -> str:
    """Expand !command syntax by running shell commands.

    This is Claude's pattern for injecting dynamic data into skills.
    Commands are run and their output replaces the placeholder.

    SECURITY: Only OFFICIAL skills can use dynamic context expansion.
    Commands must be in the allowlist and pass validation.

    Supported syntax:
    - !`command` - backtick syntax
    - !"command" - quote syntax

    Args:
        content: Skill content with potential !command placeholders
        skill_source: Source of the skill (OFFICIAL, COMMUNITY, CUSTOM)

    Returns:
        Content with commands expanded
    """
    from app.domain.models.skill import SkillSource

    # SECURITY: Only allow dynamic context for OFFICIAL skills
    if skill_source is not None and skill_source != SkillSource.OFFICIAL:
        logger.warning(f"Dynamic context expansion blocked for non-official skill (source={skill_source})")
        # Return content with placeholders replaced by security notice
        pattern = r'!\`([^`]+)\`|!"([^"]+)"'
        return re.sub(
            pattern,
            "[Dynamic context disabled for non-official skills]",
            content,
        )

    # Pattern: !`command` or !"command"
    pattern = r'!\`([^`]+)\`|!"([^"]+)"'

    matches = list(re.finditer(pattern, content))
    if not matches:
        return content

    # Run commands and collect results
    for match in reversed(matches):  # Reverse to preserve positions
        command = match.group(1) or match.group(2)

        # Validate command before execution
        is_valid, error_msg, parsed_args = _validate_command(command)
        if not is_valid:
            logger.warning(f"Blocked dynamic context command: {command!r} - {error_msg}")
            output = f"[Command blocked: {error_msg}]"
        else:
            try:
                # Run command with timeout using shell=False for security
                result = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
                        None,
                        lambda args=parsed_args: subprocess.run(  # noqa: S603, ASYNC221 - Validated command execution in executor for skill dynamic context
                            args,
                            shell=False,  # SECURITY: Never use shell=True
                            capture_output=True,
                            text=True,
                            timeout=30,
                            # Prevent environment variable injection
                            env={},
                        ),
                    ),
                    timeout=35,
                )

                output = (
                    result.stdout.strip() if result.returncode == 0 else f"[Command failed: {result.stderr.strip()}]"
                )
            except (TimeoutError, subprocess.TimeoutExpired):
                output = "[Command timed out]"
            except FileNotFoundError:
                output = f"[Command not found: {parsed_args[0]}]"
            except Exception as e:
                logger.exception(f"Error executing dynamic context command: {command}")
                output = f"[Command error: {e!s}]"

        # Replace the command with its output
        content = content[: match.start()] + output + content[match.end() :]

    return content


def substitute_arguments(content: str, arguments: str = "") -> str:
    """Substitute argument placeholders in skill content.

    Claude-style argument substitution:
    - $ARGUMENTS - all arguments as a single string
    - $1, $2, etc. - positional arguments

    Args:
        content: Skill content with potential argument placeholders
        arguments: Arguments string (like "arg1 arg2 arg3")

    Returns:
        Content with arguments substituted
    """
    # Handle $ARGUMENTS substitution
    if "$ARGUMENTS" in content:
        content = content.replace("$ARGUMENTS", arguments or "")
    elif arguments:
        # Append arguments if not explicitly handled
        content += f"\n\nARGUMENTS: {arguments}"

    # Handle positional arguments ($1, $2, etc.)
    if arguments:
        parts = arguments.split()
        for i, part in enumerate(parts, 1):
            content = content.replace(f"${i}", part)

    return content


async def build_skill_content(skill: "Skill", arguments: str = "") -> str:
    """Build the complete skill content with all expansions.

    Args:
        skill: The skill to build content for
        arguments: Optional arguments for the skill

    Returns:
        Fully expanded skill content
    """
    content = skill.system_prompt_addition or ""

    if not content:
        return f"Skill '{skill.name}' is active but has no specific instructions."

    # Apply argument substitution
    content = substitute_arguments(content, arguments)

    # Apply dynamic context expansion if enabled
    # SECURITY: Pass skill source for access control
    if skill.supports_dynamic_context:
        content = await expand_dynamic_context(content, skill_source=skill.source)

    return content


def build_skill_context(skills: list["Skill"]) -> str:
    """Build system prompt section from enabled skills.

    Takes a list of enabled skills and assembles their system_prompt_additions
    into a formatted prompt section that guides agent behavior.

    Args:
        skills: List of Skill objects with system_prompt_addition fields

    Returns:
        Formatted string to append to system prompt, or empty string if no additions
    """
    if not skills:
        return ""

    prompt_additions = []
    for skill in skills:
        # Use provided prompt if available; otherwise, generate a minimal activation notice
        if skill.system_prompt_addition and skill.system_prompt_addition.strip():
            content = skill.system_prompt_addition.strip()
        else:
            # Minimal default to make activation visible and guide tool usage
            tools_list = (
                ", ".join([*(skill.required_tools or []), *(skill.optional_tools or [])]) or "see skill configuration"
            )
            content = f"## {skill.name} Skill Active\nUse tools from this skill when applicable: {tools_list}"
        # Add skill name as a header for clarity
        addition = f"### {skill.name} Skill\n{content}"
        prompt_additions.append(addition)

    if not prompt_additions:
        return ""

    # Wrap in XML-style tags for clear boundaries with strong directive
    return (
        '\n\n<enabled_skills priority="HIGH">\n'
        "⚠️ MANDATORY: The following skills are ACTIVE for this session. "
        "You MUST follow their instructions exactly. Skill instructions OVERRIDE default behavior. "
        "If a skill specifies an output format (e.g., Excel file), you MUST produce that format.\n\n"
        + "\n\n".join(prompt_additions)
        + "\n</enabled_skills>\n"
    )


async def build_skill_context_from_ids(
    skill_ids: list[str],
    expand_dynamic: bool = True,
) -> str:
    """Build skill context from a list of skill IDs.

    Fetches skills from the database and builds the context.
    This is the main entry point for integrating skill prompts.

    Args:
        skill_ids: List of skill IDs to fetch and build context from
        expand_dynamic: Whether to expand dynamic !command syntax

    Returns:
        Formatted skill context string, or empty string if none
    """
    if not skill_ids:
        return ""

    try:
        from app.application.services.skill_service import get_skill_service

        skill_service = get_skill_service()
        skills = await skill_service.get_skills_by_ids(skill_ids)

        if not skills:
            logger.debug(f"No skills found for IDs: {skill_ids}")
            return ""

        # Build context with dynamic expansion if needed
        if expand_dynamic:
            context = await build_skill_context_async(skills)
        else:
            context = build_skill_context(skills)

        if context:
            logger.debug(f"Built skill context for {len(skills)} skills ({len(context)} chars)")
        return context

    except Exception as e:
        logger.warning(f"Failed to build skill context: {e}")
        return ""


async def build_skill_context_async(skills: list["Skill"]) -> str:
    """Build skill context with async dynamic content expansion.

    Args:
        skills: List of skills to build context from

    Returns:
        Formatted skill context string with dynamic content expanded
    """
    if not skills:
        return ""

    prompt_additions = []
    for skill in skills:
        if skill.system_prompt_addition and skill.system_prompt_addition.strip():
            # Build skill content with expansions
            content = await build_skill_content(skill)
            addition = f"### {skill.name} Skill\n{content}"
            prompt_additions.append(addition)

    if not prompt_additions:
        return ""

    return (
        '\n\n<enabled_skills priority="HIGH">\n'
        "⚠️ MANDATORY: The following skills are ACTIVE for this session. "
        "You MUST follow their instructions exactly. Skill instructions OVERRIDE default behavior. "
        "If a skill specifies an output format (e.g., Excel file), you MUST produce that format.\n\n"
        + "\n\n".join(prompt_additions)
        + "\n</enabled_skills>\n"
    )


def build_available_skills_xml(skill_dirs: list[Path]) -> str:
    """Generate the standard AgentSkills <available_skills> XML block.

    Uses the official skills-ref library (Anthropic open standard) to emit
    the ``<available_skills>`` XML format that Claude models natively
    recognise from training.  Falls back to a lightweight custom
    implementation when skills-ref is not installed.

    This function covers skill **discovery** — i.e. telling the agent which
    skills it *can* invoke.  It is separate from ``build_skill_context()``,
    which covers skill **activation** — i.e. injecting instructions from
    skills that are *already* enabled.

    Usage (in system prompt assembly)::

        skill_dirs = [Path("skills/web-research"), Path("skills/pdf")]
        xml = build_available_skills_xml(skill_dirs)
        system_prompt = base_prompt + xml

    Args:
        skill_dirs: List of paths to individual skill directories.
                    Each directory must contain a ``SKILL.md`` file.

    Returns:
        ``<available_skills>…</available_skills>`` XML string, or empty
        string if no valid skill directories are provided.
    """
    valid_dirs = [d for d in skill_dirs if d.is_dir() and (d / "SKILL.md").exists()]
    if not valid_dirs:
        return ""

    # --- Primary: AgentSkills standard (skills-ref library) ---
    if _AGENTSKILLS_PROMPT_AVAILABLE:
        try:
            return _agentskills_to_prompt(valid_dirs)
        except Exception as e:
            logger.debug(f"skills-ref to_prompt failed ({e}), using fallback")

    # --- Fallback: lightweight custom XML builder ---
    entries: list[str] = []
    for skill_dir in valid_dirs:
        skill_md = skill_dir / "SKILL.md"
        try:
            content = skill_md.read_text(encoding="utf-8")
            # Extract name and description from frontmatter (simple regex, no deps)
            name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
            desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
            skill_name = html.escape(name_match.group(1).strip()) if name_match else skill_dir.name
            skill_desc = html.escape(desc_match.group(1).strip()) if desc_match else ""
            location = html.escape(str(skill_md.resolve()))
            entries.append(
                f"<skill>\n"
                f"<name>{skill_name}</name>\n"
                f"<description>{skill_desc}</description>\n"
                f"<location>{location}</location>\n"
                f"</skill>"
            )
        except Exception as e:
            logger.warning(f"Failed to build XML entry for skill {skill_dir.name}: {e}")

    if not entries:
        return ""

    return "<available_skills>\n" + "\n".join(entries) + "\n</available_skills>"


async def build_available_skills_xml_from_registry() -> str:
    """Build <available_skills> XML for all filesystem-discovered skills.

    Queries the SkillLoader for skills that exist on disk (official + seeded)
    and generates the standard AgentSkills discovery XML.  Intended for
    injection into the base system prompt so the agent knows what skills
    it can request to load.

    Returns:
        ``<available_skills>`` XML string, or empty string if unavailable.
    """
    try:
        from app.domain.services.skill_registry import get_skill_registry

        registry = await get_skill_registry()
        skills = await registry.get_available_skills()

        # Map skills back to their directory paths for skills-ref compatibility
        skills_base_dir = Path(__file__).parent.parent.parent.parent.parent.parent / "skills"
        if not skills_base_dir.exists():
            # Try relative to the working directory
            import os

            skills_base_dir = Path(os.getcwd()) / "skills"

        skill_dirs: list[Path] = []
        for skill in skills:
            candidate = skills_base_dir / skill.id
            if candidate.is_dir() and (candidate / "SKILL.md").exists():
                skill_dirs.append(candidate)

        if not skill_dirs:
            logger.debug("No filesystem skill directories found for <available_skills> XML")
            return ""

        return build_available_skills_xml(skill_dirs)

    except Exception as e:
        logger.debug(f"build_available_skills_xml_from_registry: {e}")
        return ""


def get_skill_tools(skills: list["Skill"]) -> set[str]:
    """Get all tool names required by a list of skills.

    Args:
        skills: List of Skill objects

    Returns:
        Set of tool names
    """
    tools: set[str] = set()
    for skill in skills:
        tools.update(skill.required_tools)
        tools.update(skill.optional_tools)
    return tools


async def get_skill_tools_from_ids(skill_ids: list[str]) -> set[str]:
    """Get all tool names required by skills with the given IDs.

    Args:
        skill_ids: List of skill IDs

    Returns:
        Set of tool names
    """
    if not skill_ids:
        return set()

    try:
        from app.application.services.skill_service import get_skill_service

        skill_service = get_skill_service()
        return await skill_service.get_tools_for_skill_ids(skill_ids)

    except Exception as e:
        logger.warning(f"Failed to get skill tools: {e}")
        return set()


def format_skill_prompt_section(
    skill_name: str,
    prompt_addition: str,
    category: str | None = None,
) -> str:
    """Format a single skill's prompt addition for injection.

    Args:
        skill_name: Name of the skill
        prompt_addition: The system_prompt_addition content
        category: Optional skill category

    Returns:
        Formatted prompt section
    """
    header = f"### {skill_name}"
    if category:
        header += f" ({category})"

    return f"{header}\n{prompt_addition.strip()}"


def get_allowed_tools_from_skills(skills: list["Skill"]) -> set[str] | None:
    """Get the allowed tools based on skill configurations.

    If any skill has allowed_tools set, return the intersection of all.
    If no skills have restrictions, return None (all tools allowed).

    If the intersection would be empty (conflicting restrictions), falls back
    to the union of all allowed tools with a warning logged.

    This implements Claude's tool restriction pattern where skills
    can limit which tools the agent can use.

    Args:
        skills: List of skills to check

    Returns:
        Set of allowed tool names, or None if no restrictions
    """
    restrictions: list[set[str]] = []
    skill_names: list[str] = []

    for skill in skills:
        if skill.allowed_tools:
            restrictions.append(set(skill.allowed_tools))
            skill_names.append(skill.name)

    if not restrictions:
        return None

    # Return intersection of all restrictions
    if len(restrictions) == 1:
        return restrictions[0]

    result = restrictions[0]
    for restriction in restrictions[1:]:
        result = result.intersection(restriction)

    # Handle empty intersection (conflicting tool restrictions)
    if not result:
        logger.warning(
            f"Empty tool intersection from skills: {skill_names}. "
            f"Skills have conflicting allowed_tools. Falling back to union of all allowed tools."
        )
        # Fall back to union instead of empty set to avoid completely blocking the agent
        result = set()
        for restriction in restrictions:
            result = result.union(restriction)

        if not result:
            # Even union is empty - this means skills had empty allowed_tools lists
            logger.error(f"Skills {skill_names} have empty allowed_tools. Returning None to allow all tools.")
            return None

    return result


async def get_allowed_tools_from_skill_ids(skill_ids: list[str]) -> set[str] | None:
    """Get allowed tools from a list of skill IDs.

    Args:
        skill_ids: List of skill IDs

    Returns:
        Set of allowed tool names, or None if no restrictions
    """
    if not skill_ids:
        return None

    try:
        from app.application.services.skill_service import get_skill_service

        skill_service = get_skill_service()
        skills = await skill_service.get_skills_by_ids(skill_ids)

        if not skills:
            return None

        return get_allowed_tools_from_skills(skills)

    except Exception as e:
        logger.warning(f"Failed to get skill tool restrictions: {e}")
        return None


def get_combined_tools_from_skills(skills: list["Skill"]) -> set[str]:
    """Get all tools (required + optional) from a list of skills.

    Args:
        skills: List of skills

    Returns:
        Set of all tool names needed by the skills
    """
    tools: set[str] = set()
    for skill in skills:
        tools.update(skill.required_tools)
        tools.update(skill.optional_tools)
    return tools
