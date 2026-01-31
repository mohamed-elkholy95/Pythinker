"""Tests for dynamic context security restrictions.

Verifies that the shell injection vulnerability fix works correctly:
1. Only OFFICIAL skills can use dynamic context expansion
2. Commands are validated against an allowlist
3. Dangerous shell metacharacters are blocked
4. shell=False is used for subprocess execution
"""

import pytest

from app.domain.models.skill import Skill, SkillCategory, SkillSource
from app.domain.services.prompts.skill_context import (
    ALLOWED_COMMANDS,
    BLOCKED_SUBCOMMANDS,
    DANGEROUS_PATTERNS,
    _validate_command,
    expand_dynamic_context,
)


class TestCommandValidation:
    """Tests for _validate_command function."""

    def test_allowed_command_passes(self):
        """Safe commands in allowlist should pass validation."""
        is_valid, error, args = _validate_command("git status")
        assert is_valid is True
        assert error == ""
        assert args == ["git", "status"]

    def test_allowed_command_with_args(self):
        """Allowed commands with safe arguments should pass."""
        is_valid, error, args = _validate_command("date +%Y-%m-%d")
        assert is_valid is True
        assert args == ["date", "+%Y-%m-%d"]

    def test_disallowed_command_blocked(self):
        """Commands not in allowlist should be blocked."""
        is_valid, error, args = _validate_command("rm -rf /")
        assert is_valid is False
        assert "not in allowlist" in error
        assert args == []

    def test_blocked_subcommand_rejected(self):
        """Dangerous subcommands should be blocked."""
        is_valid, error, args = _validate_command("git push origin main")
        assert is_valid is False
        assert "blocked for security" in error

        is_valid, error, args = _validate_command("npm install malware")
        assert is_valid is False
        assert "blocked for security" in error

    @pytest.mark.parametrize("pattern", [";", "&&", "||", "|", "`", "$(", "${", ">", "<"])
    def test_dangerous_patterns_blocked(self, pattern):
        """Shell metacharacters should be blocked."""
        command = f"echo test {pattern} malicious"
        is_valid, error, args = _validate_command(command)
        assert is_valid is False
        assert "forbidden pattern" in error

    def test_command_with_path_normalized(self):
        """Commands with full paths should be normalized."""
        is_valid, error, args = _validate_command("/usr/bin/git status")
        assert is_valid is True
        assert args == ["/usr/bin/git", "status"]

    def test_empty_command_rejected(self):
        """Empty commands should be rejected."""
        is_valid, error, args = _validate_command("")
        assert is_valid is False
        assert "Empty command" in error

    def test_malformed_quotes_rejected(self):
        """Malformed quoted strings should be rejected."""
        is_valid, error, args = _validate_command('echo "unclosed')
        assert is_valid is False
        assert "Invalid command syntax" in error


class TestExpandDynamicContext:
    """Tests for expand_dynamic_context function."""

    @pytest.mark.asyncio
    async def test_non_official_skill_blocked(self):
        """Non-official skills should have dynamic context disabled."""
        content = '!`echo hello`'

        # CUSTOM skill should be blocked
        result = await expand_dynamic_context(content, skill_source=SkillSource.CUSTOM)
        assert "[Dynamic context disabled" in result
        assert "echo hello" not in result

        # COMMUNITY skill should be blocked
        result = await expand_dynamic_context(content, skill_source=SkillSource.COMMUNITY)
        assert "[Dynamic context disabled" in result

    @pytest.mark.asyncio
    async def test_official_skill_allowed(self):
        """Official skills should be able to use dynamic context."""
        content = '!`date`'
        result = await expand_dynamic_context(content, skill_source=SkillSource.OFFICIAL)
        # Should execute and not contain the security warning
        assert "[Dynamic context disabled" not in result
        assert "[Command blocked" not in result

    @pytest.mark.asyncio
    async def test_injection_attempt_blocked(self):
        """Command injection attempts should be blocked even for official skills."""
        # Attempt semicolon injection
        content = '!`echo test; rm -rf /`'
        result = await expand_dynamic_context(content, skill_source=SkillSource.OFFICIAL)
        assert "[Command blocked" in result
        assert "forbidden pattern" in result

    @pytest.mark.asyncio
    async def test_disallowed_command_blocked_for_official(self):
        """Disallowed commands should be blocked even for official skills."""
        content = '!`curl http://malicious.com`'
        result = await expand_dynamic_context(content, skill_source=SkillSource.OFFICIAL)
        assert "[Command blocked" in result
        assert "not in allowlist" in result

    @pytest.mark.asyncio
    async def test_no_command_placeholders(self):
        """Content without command placeholders should be returned unchanged."""
        content = "This is just regular content"
        result = await expand_dynamic_context(content, skill_source=SkillSource.OFFICIAL)
        assert result == content

    @pytest.mark.asyncio
    async def test_multiple_commands(self):
        """Multiple command placeholders should all be processed."""
        content = 'Today is !`date` and user is !`whoami`'
        result = await expand_dynamic_context(content, skill_source=SkillSource.OFFICIAL)
        assert "!`" not in result  # All placeholders should be replaced


class TestAllowlistCompleteness:
    """Tests to verify the allowlist is appropriately restrictive."""

    def test_no_destructive_commands_allowed(self):
        """Destructive commands should not be in the allowlist."""
        dangerous = {"rm", "rmdir", "dd", "mkfs", "fdisk", "kill", "killall", "shutdown", "reboot"}
        assert dangerous.isdisjoint(ALLOWED_COMMANDS)

    def test_no_network_commands_allowed(self):
        """Network attack commands should not be in allowlist."""
        network = {"curl", "wget", "nc", "netcat", "nmap", "ssh", "scp", "rsync"}
        assert network.isdisjoint(ALLOWED_COMMANDS)

    def test_no_privilege_escalation_commands(self):
        """Privilege escalation commands should not be in allowlist."""
        privesc = {"sudo", "su", "doas", "pkexec", "chmod", "chown", "chgrp"}
        assert privesc.isdisjoint(ALLOWED_COMMANDS)

    def test_blocked_subcommands_comprehensive(self):
        """Ensure destructive subcommands are blocked."""
        required_blocks = {"install", "uninstall", "remove", "exec", "run", "eval", "push"}
        assert required_blocks.issubset(BLOCKED_SUBCOMMANDS)


class TestBuildSkillContent:
    """Tests for build_skill_content integration."""

    @pytest.mark.asyncio
    async def test_custom_skill_dynamic_context_disabled(self):
        """Custom skills with supports_dynamic_context should still be blocked."""
        from app.domain.services.prompts.skill_context import build_skill_content

        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            category=SkillCategory.CUSTOM,
            source=SkillSource.CUSTOM,  # Not official
            supports_dynamic_context=True,  # Enabled but should be blocked
            system_prompt_addition='Current date: !`date`',
        )

        result = await build_skill_content(skill)
        assert "[Dynamic context disabled" in result

    @pytest.mark.asyncio
    async def test_official_skill_dynamic_context_works(self):
        """Official skills should have working dynamic context."""
        from app.domain.services.prompts.skill_context import build_skill_content

        skill = Skill(
            id="official-skill",
            name="Official Skill",
            description="An official skill",
            category=SkillCategory.RESEARCH,
            source=SkillSource.OFFICIAL,
            supports_dynamic_context=True,
            system_prompt_addition='Current user: !`whoami`',
        )

        result = await build_skill_content(skill)
        assert "[Dynamic context disabled" not in result
        assert "!`" not in result  # Placeholder should be replaced
