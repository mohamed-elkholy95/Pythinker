"""Tests for CommandRegistry — command-to-skill mapping and resolution.

Covers parse_command, get_skill_command, get_available_commands,
get_command_help, register_command, and lazy initialization.
"""

import pytest

from app.domain.services.command_registry import (
    SUPERPOWERS_COMMANDS,
    CommandMapping,
    CommandRegistry,
)


@pytest.fixture
def registry() -> CommandRegistry:
    """Fresh CommandRegistry instance for each test."""
    return CommandRegistry()


# ---------------------------------------------------------------------------
# 1. parse_command
# ---------------------------------------------------------------------------


class TestParseCommand:
    """Tests for CommandRegistry.parse_command."""

    def test_primary_command_with_text(self, registry: CommandRegistry) -> None:
        """Primary command followed by text returns skill_id and remainder."""
        skill_id, remaining = registry.parse_command("/brainstorm hello world")
        assert skill_id == "brainstorming"
        assert remaining == "hello world"

    def test_alias_command_with_text(self, registry: CommandRegistry) -> None:
        """Alias resolves to the same skill_id as the primary command."""
        skill_id, remaining = registry.parse_command("/design something cool")
        assert skill_id == "brainstorming"
        assert remaining == "something cool"

    def test_another_alias(self, registry: CommandRegistry) -> None:
        """Second alias for the same command also resolves correctly."""
        skill_id, remaining = registry.parse_command("/plan-design my feature")
        assert skill_id == "brainstorming"
        assert remaining == "my feature"

    def test_unknown_command(self, registry: CommandRegistry) -> None:
        """Unknown /command returns None and the original message."""
        skill_id, remaining = registry.parse_command("/foobar do stuff")
        assert skill_id is None
        assert remaining == "/foobar do stuff"

    def test_no_command_plain_text(self, registry: CommandRegistry) -> None:
        """Plain text without a leading slash returns None and original message."""
        message = "hello there"
        skill_id, remaining = registry.parse_command(message)
        assert skill_id is None
        assert remaining == message

    def test_leading_whitespace_stripped(self, registry: CommandRegistry) -> None:
        """Leading/trailing whitespace around the message is handled."""
        skill_id, remaining = registry.parse_command("  /brainstorm  hello  ")
        assert skill_id == "brainstorming"
        assert remaining == "hello"

    def test_multiline_message(self, registry: CommandRegistry) -> None:
        """Command with multiline remaining text preserves all lines."""
        message = "/tdd line one\nline two\nline three"
        skill_id, remaining = registry.parse_command(message)
        assert skill_id == "test-driven-development"
        assert "line one" in remaining
        assert "line two" in remaining
        assert "line three" in remaining

    def test_command_only_no_remaining(self, registry: CommandRegistry) -> None:
        """Command with no trailing text returns empty remaining string."""
        skill_id, remaining = registry.parse_command("/debug")
        assert skill_id == "systematic-debugging"
        assert remaining == ""

    def test_case_insensitive_uppercase(self, registry: CommandRegistry) -> None:
        """Commands are matched case-insensitively (all uppercase)."""
        skill_id, remaining = registry.parse_command("/BRAINSTORM loud message")
        assert skill_id == "brainstorming"
        assert remaining == "loud message"

    def test_case_insensitive_mixed(self, registry: CommandRegistry) -> None:
        """Commands are matched case-insensitively (mixed case)."""
        skill_id, remaining = registry.parse_command("/BrAiNsToRm mixed")
        assert skill_id == "brainstorming"
        assert remaining == "mixed"

    def test_case_insensitive_alias(self, registry: CommandRegistry) -> None:
        """Aliases are also matched case-insensitively."""
        skill_id, remaining = registry.parse_command("/DESIGN caps alias")
        assert skill_id == "brainstorming"
        assert remaining == "caps alias"

    def test_slash_in_middle_of_text(self, registry: CommandRegistry) -> None:
        """Slash in the middle of text is not treated as a command."""
        message = "please run /brainstorm for me"
        skill_id, remaining = registry.parse_command(message)
        assert skill_id is None
        assert remaining == message

    def test_empty_message(self, registry: CommandRegistry) -> None:
        """Empty string returns None and the original message."""
        skill_id, remaining = registry.parse_command("")
        assert skill_id is None
        assert remaining == ""

    def test_slash_only(self, registry: CommandRegistry) -> None:
        """A lone slash is not a valid command."""
        skill_id, remaining = registry.parse_command("/")
        assert skill_id is None
        assert remaining == "/"

    def test_all_primary_commands_parseable(self, registry: CommandRegistry) -> None:
        """Every primary command in SUPERPOWERS_COMMANDS is parseable."""
        for mapping in SUPERPOWERS_COMMANDS:
            skill_id, _ = registry.parse_command(f"/{mapping.command} test")
            assert skill_id == mapping.skill_id, (
                f"/{mapping.command} should resolve to '{mapping.skill_id}', got '{skill_id}'"
            )

    def test_all_aliases_parseable(self, registry: CommandRegistry) -> None:
        """Every alias in SUPERPOWERS_COMMANDS resolves to the correct skill."""
        for mapping in SUPERPOWERS_COMMANDS:
            for alias in mapping.aliases:
                skill_id, _ = registry.parse_command(f"/{alias} test")
                assert skill_id == mapping.skill_id, (
                    f"/{alias} should resolve to '{mapping.skill_id}', got '{skill_id}'"
                )

    def test_write_plan_command(self, registry: CommandRegistry) -> None:
        """Hyphenated command like /write-plan works correctly."""
        skill_id, remaining = registry.parse_command("/write-plan build auth module")
        assert skill_id == "writing-plans"
        assert remaining == "build auth module"

    def test_execute_plan_alias(self, registry: CommandRegistry) -> None:
        """Alias /exec-plan resolves to executing-plans."""
        skill_id, _ = registry.parse_command("/exec-plan")
        assert skill_id == "executing-plans"

    def test_remaining_text_stripped(self, registry: CommandRegistry) -> None:
        """Remaining text after command has leading/trailing whitespace stripped."""
        skill_id, remaining = registry.parse_command("/tdd   lots of spaces   ")
        assert skill_id == "test-driven-development"
        assert remaining == "lots of spaces"


# ---------------------------------------------------------------------------
# 2. get_skill_command
# ---------------------------------------------------------------------------


class TestGetSkillCommand:
    """Tests for CommandRegistry.get_skill_command."""

    def test_known_skill_returns_primary_command(self, registry: CommandRegistry) -> None:
        """Known skill_id returns its primary command name."""
        command = registry.get_skill_command("brainstorming")
        assert command == "brainstorm"

    def test_another_known_skill(self, registry: CommandRegistry) -> None:
        """Another known skill returns its primary command."""
        command = registry.get_skill_command("test-driven-development")
        assert command == "tdd"

    def test_unknown_skill_returns_none(self, registry: CommandRegistry) -> None:
        """Unknown skill_id returns None."""
        command = registry.get_skill_command("nonexistent-skill")
        assert command is None

    def test_all_skills_have_reverse_mapping(self, registry: CommandRegistry) -> None:
        """Every skill in SUPERPOWERS_COMMANDS has a reverse mapping."""
        for mapping in SUPERPOWERS_COMMANDS:
            command = registry.get_skill_command(mapping.skill_id)
            assert command == mapping.command, (
                f"Skill '{mapping.skill_id}' should map back to '{mapping.command}', got '{command}'"
            )


# ---------------------------------------------------------------------------
# 3. get_available_commands
# ---------------------------------------------------------------------------


class TestGetAvailableCommands:
    """Tests for CommandRegistry.get_available_commands."""

    def test_returns_list_of_tuples(self, registry: CommandRegistry) -> None:
        """Returns a list of 3-tuples."""
        commands = registry.get_available_commands()
        assert isinstance(commands, list)
        assert len(commands) > 0
        for entry in commands:
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_tuple_structure(self, registry: CommandRegistry) -> None:
        """Each tuple contains (command_str, skill_id_str, description_str)."""
        commands = registry.get_available_commands()
        for command, skill_id, description in commands:
            assert isinstance(command, str)
            assert isinstance(skill_id, str)
            assert isinstance(description, str)
            assert len(command) > 0
            assert len(skill_id) > 0
            assert len(description) > 0

    def test_no_duplicate_skills(self, registry: CommandRegistry) -> None:
        """Each skill_id appears at most once (aliases are excluded)."""
        commands = registry.get_available_commands()
        skill_ids = [skill_id for _, skill_id, _ in commands]
        assert len(skill_ids) == len(set(skill_ids)), "Duplicate skill_ids found"

    def test_count_matches_superpowers(self, registry: CommandRegistry) -> None:
        """Number of commands matches number of SUPERPOWERS_COMMANDS entries."""
        commands = registry.get_available_commands()
        assert len(commands) == len(SUPERPOWERS_COMMANDS)

    def test_contains_brainstorm(self, registry: CommandRegistry) -> None:
        """The brainstorm command is in the list."""
        commands = registry.get_available_commands()
        command_names = [cmd for cmd, _, _ in commands]
        assert "brainstorm" in command_names

    def test_only_primary_commands(self, registry: CommandRegistry) -> None:
        """Only primary commands are returned, not aliases."""
        commands = registry.get_available_commands()
        command_names = {cmd for cmd, _, _ in commands}
        # "design" is an alias, should not appear
        assert "design" not in command_names
        # "brainstorm" is primary, should appear
        assert "brainstorm" in command_names


# ---------------------------------------------------------------------------
# 4. get_command_help
# ---------------------------------------------------------------------------


class TestGetCommandHelp:
    """Tests for CommandRegistry.get_command_help."""

    def test_primary_command_help(self, registry: CommandRegistry) -> None:
        """Primary command returns its description."""
        help_text = registry.get_command_help("brainstorm")
        assert help_text is not None
        assert "design" in help_text.lower() or "refinement" in help_text.lower()

    def test_alias_help_contains_alias_for(self, registry: CommandRegistry) -> None:
        """Alias help text mentions 'alias for /primary_command'."""
        help_text = registry.get_command_help("design")
        assert help_text is not None
        assert "alias for /brainstorm" in help_text

    def test_another_alias_help(self, registry: CommandRegistry) -> None:
        """Another alias also contains the 'alias for' marker."""
        help_text = registry.get_command_help("test-first")
        assert help_text is not None
        assert "alias for /tdd" in help_text

    def test_unknown_command_returns_none(self, registry: CommandRegistry) -> None:
        """Unknown command returns None."""
        help_text = registry.get_command_help("nonexistent")
        assert help_text is None

    def test_case_insensitive_lookup(self, registry: CommandRegistry) -> None:
        """Help lookup is case-insensitive."""
        help_text = registry.get_command_help("BRAINSTORM")
        assert help_text is not None

    def test_case_insensitive_alias_lookup(self, registry: CommandRegistry) -> None:
        """Alias help lookup is also case-insensitive."""
        help_text = registry.get_command_help("DESIGN")
        assert help_text is not None
        assert "alias for /brainstorm" in help_text


# ---------------------------------------------------------------------------
# 5. register_command
# ---------------------------------------------------------------------------


class TestRegisterCommand:
    """Tests for CommandRegistry.register_command."""

    def test_register_new_command(self, registry: CommandRegistry) -> None:
        """Newly registered command is resolvable via parse_command."""
        registry.register_command("mycommand", "my-skill", "Does my thing")
        skill_id, remaining = registry.parse_command("/mycommand do it")
        assert skill_id == "my-skill"
        assert remaining == "do it"

    def test_register_with_aliases(self, registry: CommandRegistry) -> None:
        """Registered aliases resolve to the same skill."""
        registry.register_command("custom", "custom-skill", "Custom desc", aliases=["c", "cust"])
        skill_id_primary, _ = registry.parse_command("/custom test")
        skill_id_alias1, _ = registry.parse_command("/c test")
        skill_id_alias2, _ = registry.parse_command("/cust test")
        assert skill_id_primary == "custom-skill"
        assert skill_id_alias1 == "custom-skill"
        assert skill_id_alias2 == "custom-skill"

    def test_register_command_appears_in_skill_lookup(self, registry: CommandRegistry) -> None:
        """Registered command appears in get_skill_command reverse lookup."""
        registry.register_command("newcmd", "new-skill-id", "New description")
        command = registry.get_skill_command("new-skill-id")
        assert command == "newcmd"

    def test_register_command_help(self, registry: CommandRegistry) -> None:
        """Registered command help text is returned correctly."""
        registry.register_command("helpcmd", "help-skill", "Help description text")
        help_text = registry.get_command_help("helpcmd")
        assert help_text == "Help description text"

    def test_register_alias_help(self, registry: CommandRegistry) -> None:
        """Registered alias help text includes 'alias for' marker."""
        registry.register_command("primary", "primary-skill", "Primary desc", aliases=["alt"])
        help_text = registry.get_command_help("alt")
        assert help_text is not None
        assert "alias for /primary" in help_text

    def test_register_without_aliases(self, registry: CommandRegistry) -> None:
        """Registering a command with no aliases works (aliases=None)."""
        registry.register_command("solo", "solo-skill", "Solo desc")
        skill_id, _ = registry.parse_command("/solo go")
        assert skill_id == "solo-skill"

    def test_register_command_case_normalized(self, registry: CommandRegistry) -> None:
        """Registered commands are lowercased so uppercase input works."""
        registry.register_command("MyCMD", "myskill", "My desc")
        skill_id, _ = registry.parse_command("/mycmd test")
        assert skill_id == "myskill"
        # Also verify uppercase input resolves
        skill_id2, _ = registry.parse_command("/MYCMD test")
        assert skill_id2 == "myskill"

    def test_register_overwrites_existing(self, registry: CommandRegistry) -> None:
        """Registering a command that already exists overwrites it."""
        registry.register_command("brainstorm", "custom-brainstorm", "Custom version")
        skill_id, _ = registry.parse_command("/brainstorm test")
        assert skill_id == "custom-brainstorm"


# ---------------------------------------------------------------------------
# 6. Lazy initialization
# ---------------------------------------------------------------------------


class TestLazyInitialization:
    """Tests for lazy initialization behavior."""

    def test_not_initialized_on_construction(self) -> None:
        """Registry is not initialized upon construction."""
        reg = CommandRegistry()
        assert reg._initialized is False
        assert len(reg._command_map) == 0

    def test_initialized_after_first_call(self) -> None:
        """Registry is initialized after the first method call."""
        reg = CommandRegistry()
        reg.parse_command("/brainstorm test")
        assert reg._initialized is True
        assert len(reg._command_map) > 0

    def test_ensure_initialized_idempotent(self) -> None:
        """Calling _ensure_initialized multiple times is safe and idempotent."""
        reg = CommandRegistry()
        reg._ensure_initialized()
        size_after_first = len(reg._command_map)
        reg._ensure_initialized()
        size_after_second = len(reg._command_map)
        assert size_after_first == size_after_second

    def test_all_methods_trigger_initialization(self) -> None:
        """Every public method triggers lazy initialization."""
        for method_name in [
            "parse_command",
            "get_skill_command",
            "get_available_commands",
            "get_command_help",
            "register_command",
        ]:
            reg = CommandRegistry()
            assert reg._initialized is False

            method = getattr(reg, method_name)
            if method_name == "parse_command":
                method("/test")
            elif method_name == "get_skill_command":
                method("brainstorming")
            elif method_name == "get_available_commands":
                method()
            elif method_name == "get_command_help":
                method("brainstorm")
            elif method_name == "register_command":
                method("x", "x-skill", "x desc")

            assert reg._initialized is True, f"{method_name} did not trigger initialization"

    def test_command_map_populated_with_aliases(self) -> None:
        """After initialization, command_map contains both primaries and aliases."""
        reg = CommandRegistry()
        reg._ensure_initialized()

        # Count expected entries
        expected_count = 0
        for mapping in SUPERPOWERS_COMMANDS:
            expected_count += 1  # primary
            expected_count += len(mapping.aliases)

        assert len(reg._command_map) == expected_count


# ---------------------------------------------------------------------------
# 7. CommandMapping dataclass
# ---------------------------------------------------------------------------


class TestCommandMapping:
    """Tests for the CommandMapping dataclass itself."""

    def test_create_command_mapping(self) -> None:
        """CommandMapping can be created with all fields."""
        mapping = CommandMapping(
            command="test",
            skill_id="test-skill",
            description="Test description",
            aliases=["t", "tst"],
        )
        assert mapping.command == "test"
        assert mapping.skill_id == "test-skill"
        assert mapping.description == "Test description"
        assert mapping.aliases == ["t", "tst"]

    def test_superpowers_commands_not_empty(self) -> None:
        """SUPERPOWERS_COMMANDS is a non-empty list."""
        assert len(SUPERPOWERS_COMMANDS) > 0

    def test_all_superpowers_have_required_fields(self) -> None:
        """Every SUPERPOWERS_COMMANDS entry has non-empty required fields."""
        for mapping in SUPERPOWERS_COMMANDS:
            assert mapping.command, f"Empty command in {mapping}"
            assert mapping.skill_id, f"Empty skill_id in {mapping}"
            assert mapping.description, f"Empty description in {mapping}"
            assert isinstance(mapping.aliases, list), f"aliases is not a list in {mapping}"

    def test_no_duplicate_primary_commands(self) -> None:
        """No duplicate primary command names in SUPERPOWERS_COMMANDS."""
        commands = [m.command for m in SUPERPOWERS_COMMANDS]
        assert len(commands) == len(set(commands)), "Duplicate primary commands found"

    def test_no_duplicate_skill_ids(self) -> None:
        """No duplicate skill_ids in SUPERPOWERS_COMMANDS."""
        skill_ids = [m.skill_id for m in SUPERPOWERS_COMMANDS]
        assert len(skill_ids) == len(set(skill_ids)), "Duplicate skill_ids found"

    def test_no_alias_shadows_primary(self) -> None:
        """No alias is the same as any primary command name."""
        primaries = {m.command for m in SUPERPOWERS_COMMANDS}
        for mapping in SUPERPOWERS_COMMANDS:
            for alias in mapping.aliases:
                assert alias not in primaries, f"Alias '{alias}' shadows primary command"
