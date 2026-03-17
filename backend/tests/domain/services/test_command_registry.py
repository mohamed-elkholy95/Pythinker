"""Tests for CommandRegistry — command-to-skill mapping and resolution.

Covers parse_command, get_skill_command, get_available_commands,
get_command_help, register_command, and lazy initialization.
"""

import pytest

from app.domain.services.command_registry import CommandMapping, CommandRegistry


@pytest.fixture
def registry() -> CommandRegistry:
    """Fresh CommandRegistry instance for each test."""
    return CommandRegistry()


@pytest.fixture
def populated_registry() -> CommandRegistry:
    """Registry with some test commands pre-registered."""
    reg = CommandRegistry()
    reg.register_command("test", "test-skill", "Test command", aliases=["t", "tst"])
    reg.register_command("custom", "custom-skill", "Custom command", aliases=["c"])
    return reg


# ---------------------------------------------------------------------------
# 1. parse_command - Empty Registry
# ---------------------------------------------------------------------------


class TestParseCommandEmpty:
    """Tests for CommandRegistry.parse_command with empty registry."""

    def test_unknown_command_empty_registry(self, registry: CommandRegistry) -> None:
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

    def test_slash_only(self, registry: CommandRegistry) -> None:
        """A lone slash is not a valid command."""
        skill_id, remaining = registry.parse_command("/")
        assert skill_id is None
        assert remaining == "/"

    def test_empty_message(self, registry: CommandRegistry) -> None:
        """Empty string returns None and the original message."""
        skill_id, remaining = registry.parse_command("")
        assert skill_id is None
        assert remaining == ""

    def test_slash_in_middle_of_text(self, registry: CommandRegistry) -> None:
        """Slash in the middle of text is not treated as a command."""
        message = "please run /test for me"
        skill_id, remaining = registry.parse_command(message)
        assert skill_id is None
        assert remaining == message


# ---------------------------------------------------------------------------
# 2. parse_command - With Registered Commands
# ---------------------------------------------------------------------------


class TestParseCommandPopulated:
    """Tests for CommandRegistry.parse_command with registered commands."""

    def test_primary_command_with_text(self, populated_registry: CommandRegistry) -> None:
        """Primary command followed by text returns skill_id and remainder."""
        skill_id, remaining = populated_registry.parse_command("/test hello world")
        assert skill_id == "test-skill"
        assert remaining == "hello world"

    def test_alias_command_with_text(self, populated_registry: CommandRegistry) -> None:
        """Alias resolves to the same skill_id as the primary command."""
        skill_id, remaining = populated_registry.parse_command("/t something cool")
        assert skill_id == "test-skill"
        assert remaining == "something cool"

    def test_command_only_no_remaining(self, populated_registry: CommandRegistry) -> None:
        """Command with no trailing text returns empty remaining string."""
        skill_id, remaining = populated_registry.parse_command("/test")
        assert skill_id == "test-skill"
        assert remaining == ""

    def test_leading_whitespace_stripped(self, populated_registry: CommandRegistry) -> None:
        """Leading/trailing whitespace around the message is handled."""
        skill_id, remaining = populated_registry.parse_command("  /test  hello  ")
        assert skill_id == "test-skill"
        assert remaining == "hello"

    def test_multiline_message(self, populated_registry: CommandRegistry) -> None:
        """Command with multiline remaining text preserves all lines."""
        message = "/test line one\nline two\nline three"
        skill_id, remaining = populated_registry.parse_command(message)
        assert skill_id == "test-skill"
        assert "line one" in remaining
        assert "line two" in remaining
        assert "line three" in remaining

    def test_case_insensitive_uppercase(self, populated_registry: CommandRegistry) -> None:
        """Commands are matched case-insensitively (all uppercase)."""
        skill_id, remaining = populated_registry.parse_command("/TEST loud message")
        assert skill_id == "test-skill"
        assert remaining == "loud message"

    def test_case_insensitive_mixed(self, populated_registry: CommandRegistry) -> None:
        """Commands are matched case-insensitively (mixed case)."""
        skill_id, remaining = populated_registry.parse_command("/TeSt mixed")
        assert skill_id == "test-skill"
        assert remaining == "mixed"

    def test_case_insensitive_alias(self, populated_registry: CommandRegistry) -> None:
        """Aliases are also matched case-insensitively."""
        skill_id, remaining = populated_registry.parse_command("/T caps alias")
        assert skill_id == "test-skill"
        assert remaining == "caps alias"

    def test_remaining_text_stripped(self, populated_registry: CommandRegistry) -> None:
        """Remaining text after command has leading/trailing whitespace stripped."""
        skill_id, remaining = populated_registry.parse_command("/test   lots of spaces   ")
        assert skill_id == "test-skill"
        assert remaining == "lots of spaces"


# ---------------------------------------------------------------------------
# 3. get_skill_command
# ---------------------------------------------------------------------------


class TestGetSkillCommand:
    """Tests for CommandRegistry.get_skill_command."""

    def test_known_skill_returns_primary_command(self, populated_registry: CommandRegistry) -> None:
        """Known skill_id returns its primary command name."""
        command = populated_registry.get_skill_command("test-skill")
        assert command == "test"

    def test_another_known_skill(self, populated_registry: CommandRegistry) -> None:
        """Another known skill returns its primary command."""
        command = populated_registry.get_skill_command("custom-skill")
        assert command == "custom"

    def test_unknown_skill_returns_none(self, populated_registry: CommandRegistry) -> None:
        """Unknown skill_id returns None."""
        command = populated_registry.get_skill_command("nonexistent-skill")
        assert command is None

    def test_empty_registry_returns_none(self, registry: CommandRegistry) -> None:
        """Empty registry returns None for any skill_id."""
        command = registry.get_skill_command("any-skill")
        assert command is None


# ---------------------------------------------------------------------------
# 4. get_available_commands
# ---------------------------------------------------------------------------


class TestGetAvailableCommands:
    """Tests for CommandRegistry.get_available_commands."""

    def test_empty_registry_returns_empty_list(self, registry: CommandRegistry) -> None:
        """Empty registry returns an empty list."""
        commands = registry.get_available_commands()
        assert isinstance(commands, list)
        assert len(commands) == 0

    def test_returns_list_of_tuples(self, populated_registry: CommandRegistry) -> None:
        """Returns a list of 3-tuples."""
        commands = populated_registry.get_available_commands()
        assert isinstance(commands, list)
        assert len(commands) == 2  # test and custom
        for entry in commands:
            assert isinstance(entry, tuple)
            assert len(entry) == 3

    def test_tuple_structure(self, populated_registry: CommandRegistry) -> None:
        """Each tuple contains (command_str, skill_id_str, description_str)."""
        commands = populated_registry.get_available_commands()
        for command, skill_id, description in commands:
            assert isinstance(command, str)
            assert isinstance(skill_id, str)
            assert isinstance(description, str)
            assert len(command) > 0
            assert len(skill_id) > 0
            assert len(description) > 0

    def test_no_duplicate_skills(self, populated_registry: CommandRegistry) -> None:
        """Each skill_id appears at most once (aliases are excluded)."""
        commands = populated_registry.get_available_commands()
        skill_ids = [skill_id for _, skill_id, _ in commands]
        assert len(skill_ids) == len(set(skill_ids)), "Duplicate skill_ids found"

    def test_only_primary_commands(self, populated_registry: CommandRegistry) -> None:
        """Only primary commands are returned, not aliases."""
        commands = populated_registry.get_available_commands()
        command_names = {cmd for cmd, _, _ in commands}
        # "t" and "c" are aliases, should not appear
        assert "t" not in command_names
        assert "c" not in command_names
        # "test" and "custom" are primary, should appear
        assert "test" in command_names
        assert "custom" in command_names


# ---------------------------------------------------------------------------
# 5. get_command_map
# ---------------------------------------------------------------------------


class TestGetCommandMap:
    """Tests for CommandRegistry.get_command_map."""

    def test_empty_registry_returns_empty_dict(self, registry: CommandRegistry) -> None:
        """Empty registry returns an empty dict."""
        cmd_map = registry.get_command_map()
        assert isinstance(cmd_map, dict)
        assert len(cmd_map) == 0

    def test_returns_dict(self, populated_registry: CommandRegistry) -> None:
        """Returns a dict mapping command/alias -> skill_id."""
        cmd_map = populated_registry.get_command_map()
        assert isinstance(cmd_map, dict)
        assert len(cmd_map) > 0

    def test_primary_commands_included(self, populated_registry: CommandRegistry) -> None:
        """Primary commands resolve to skill_id."""
        cmd_map = populated_registry.get_command_map()
        assert cmd_map.get("test") == "test-skill"
        assert cmd_map.get("custom") == "custom-skill"

    def test_aliases_included(self, populated_registry: CommandRegistry) -> None:
        """Aliases also resolve to skill_id."""
        cmd_map = populated_registry.get_command_map()
        assert cmd_map.get("t") == "test-skill"
        assert cmd_map.get("tst") == "test-skill"
        assert cmd_map.get("c") == "custom-skill"

    def test_count_includes_aliases(self, populated_registry: CommandRegistry) -> None:
        """Map has more entries than primary commands (includes aliases)."""
        cmd_map = populated_registry.get_command_map()
        commands = populated_registry.get_available_commands()
        # 2 primaries + 3 aliases = 5 total
        assert len(cmd_map) == 5
        assert len(commands) == 2


# ---------------------------------------------------------------------------
# 6. get_command_help
# ---------------------------------------------------------------------------


class TestGetCommandHelp:
    """Tests for CommandRegistry.get_command_help."""

    def test_primary_command_help(self, populated_registry: CommandRegistry) -> None:
        """Primary command returns its description."""
        help_text = populated_registry.get_command_help("test")
        assert help_text == "Test command"

    def test_alias_help_contains_alias_for(self, populated_registry: CommandRegistry) -> None:
        """Alias help text mentions 'alias for /primary_command'."""
        help_text = populated_registry.get_command_help("t")
        assert help_text is not None
        assert "alias for /test" in help_text

    def test_another_alias_help(self, populated_registry: CommandRegistry) -> None:
        """Another alias also contains the 'alias for' marker."""
        help_text = populated_registry.get_command_help("c")
        assert help_text is not None
        assert "alias for /custom" in help_text

    def test_unknown_command_returns_none(self, populated_registry: CommandRegistry) -> None:
        """Unknown command returns None."""
        help_text = populated_registry.get_command_help("nonexistent")
        assert help_text is None

    def test_empty_registry_returns_none(self, registry: CommandRegistry) -> None:
        """Empty registry returns None for any command."""
        help_text = registry.get_command_help("test")
        assert help_text is None

    def test_case_insensitive_lookup(self, populated_registry: CommandRegistry) -> None:
        """Help lookup is case-insensitive."""
        help_text = populated_registry.get_command_help("TEST")
        assert help_text == "Test command"

    def test_case_insensitive_alias_lookup(self, populated_registry: CommandRegistry) -> None:
        """Alias help lookup is also case-insensitive."""
        help_text = populated_registry.get_command_help("T")
        assert help_text is not None
        assert "alias for /test" in help_text


# ---------------------------------------------------------------------------
# 7. register_command
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

    def test_register_overwrites_existing(self, populated_registry: CommandRegistry) -> None:
        """Registering a command that already exists overwrites it."""
        populated_registry.register_command("test", "new-test-skill", "New version")
        skill_id, _ = populated_registry.parse_command("/test hello")
        assert skill_id == "new-test-skill"

    def test_register_appears_in_available_commands(self, registry: CommandRegistry) -> None:
        """Registered command appears in get_available_commands list."""
        registry.register_command("visible", "visible-skill", "Visible command")
        commands = registry.get_available_commands()
        command_names = [cmd for cmd, _, _ in commands]
        assert "visible" in command_names


# ---------------------------------------------------------------------------
# 8. Lazy initialization
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
        reg.parse_command("/test hello")
        assert reg._initialized is True

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
                method("test-skill")
            elif method_name == "get_available_commands":
                method()
            elif method_name == "get_command_help":
                method("test")
            elif method_name == "register_command":
                method("x", "x-skill", "x desc")

            assert reg._initialized is True, f"{method_name} did not trigger initialization"


# ---------------------------------------------------------------------------
# 9. CommandMapping dataclass
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

    def test_command_mapping_with_empty_aliases(self) -> None:
        """CommandMapping can be created with empty aliases list."""
        mapping = CommandMapping(
            command="solo",
            skill_id="solo-skill",
            description="Solo command",
            aliases=[],
        )
        assert mapping.command == "solo"
        assert mapping.aliases == []
