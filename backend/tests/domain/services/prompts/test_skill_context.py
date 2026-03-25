"""Tests for skill_context: command validation, security allowlists, and dangerous patterns."""

from __future__ import annotations

from app.domain.services.prompts.skill_context import (
    ALLOWED_COMMANDS,
    BLOCKED_SUBCOMMANDS,
    DANGEROUS_PATTERNS,
    _validate_command,
)

# ── ALLOWED_COMMANDS ────────────────────────────────────────────────────────


class TestAllowedCommands:
    def test_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_COMMANDS, frozenset)

    def test_git_is_allowed(self) -> None:
        assert "git" in ALLOWED_COMMANDS

    def test_date_is_allowed(self) -> None:
        assert "date" in ALLOWED_COMMANDS

    def test_echo_is_allowed(self) -> None:
        assert "echo" in ALLOWED_COMMANDS

    def test_python_is_not_allowed(self) -> None:
        assert "python" not in ALLOWED_COMMANDS
        assert "python3" not in ALLOWED_COMMANDS

    def test_node_is_not_allowed(self) -> None:
        assert "node" not in ALLOWED_COMMANDS

    def test_bash_is_not_allowed(self) -> None:
        assert "bash" not in ALLOWED_COMMANDS
        assert "sh" not in ALLOWED_COMMANDS

    def test_rm_is_not_allowed(self) -> None:
        assert "rm" not in ALLOWED_COMMANDS

    def test_curl_is_not_allowed(self) -> None:
        assert "curl" not in ALLOWED_COMMANDS


# ── BLOCKED_SUBCOMMANDS ────────────────────────────────────────────────────


class TestBlockedSubcommands:
    def test_is_frozenset(self) -> None:
        assert isinstance(BLOCKED_SUBCOMMANDS, frozenset)

    def test_push_is_blocked(self) -> None:
        assert "push" in BLOCKED_SUBCOMMANDS

    def test_install_is_blocked(self) -> None:
        assert "install" in BLOCKED_SUBCOMMANDS

    def test_exec_is_blocked(self) -> None:
        assert "exec" in BLOCKED_SUBCOMMANDS

    def test_reset_is_blocked(self) -> None:
        assert "reset" in BLOCKED_SUBCOMMANDS

    def test_dash_c_is_blocked(self) -> None:
        assert "-c" in BLOCKED_SUBCOMMANDS

    def test_run_is_blocked(self) -> None:
        assert "run" in BLOCKED_SUBCOMMANDS


# ── DANGEROUS_PATTERNS ──────────────────────────────────────────────────────


class TestDangerousPatterns:
    def test_is_tuple(self) -> None:
        assert isinstance(DANGEROUS_PATTERNS, tuple)

    def test_semicolon_is_dangerous(self) -> None:
        assert ";" in DANGEROUS_PATTERNS

    def test_pipe_is_dangerous(self) -> None:
        assert "|" in DANGEROUS_PATTERNS

    def test_backtick_is_dangerous(self) -> None:
        assert "`" in DANGEROUS_PATTERNS

    def test_dollar_paren_is_dangerous(self) -> None:
        assert "$(" in DANGEROUS_PATTERNS

    def test_redirect_is_dangerous(self) -> None:
        assert ">" in DANGEROUS_PATTERNS
        assert "<" in DANGEROUS_PATTERNS

    def test_newline_is_dangerous(self) -> None:
        assert "\n" in DANGEROUS_PATTERNS


# ── _validate_command ───────────────────────────────────────────────────────


class TestValidateCommand:
    def test_valid_git_status(self) -> None:
        valid, _err, args = _validate_command("git status")
        assert valid is True
        assert _err == ""
        assert args == ["git", "status"]

    def test_valid_date(self) -> None:
        valid, _err, args = _validate_command("date")
        assert valid is True
        assert args == ["date"]

    def test_valid_echo(self) -> None:
        valid, _err, args = _validate_command("echo hello")
        assert valid is True
        assert args == ["echo", "hello"]

    def test_valid_git_log(self) -> None:
        valid, _err, _args = _validate_command("git log --oneline -5")
        assert valid is True

    def test_blocked_command_python(self) -> None:
        valid, _err, _ = _validate_command("python script.py")
        assert valid is False
        assert "allowlist" in _err.lower()

    def test_blocked_command_rm(self) -> None:
        valid, _err, _ = _validate_command("rm -rf /")
        assert valid is False

    def test_blocked_subcommand_git_push(self) -> None:
        valid, _err, _ = _validate_command("git push origin main")
        assert valid is False
        assert "blocked" in _err.lower()

    def test_blocked_subcommand_pip_install(self) -> None:
        valid, _err, _ = _validate_command("pip install requests")
        assert valid is False
        assert "blocked" in _err.lower()

    def test_blocked_subcommand_npm_install(self) -> None:
        valid, _err, _ = _validate_command("npm install")
        assert valid is False

    def test_dangerous_semicolon(self) -> None:
        valid, _err, _ = _validate_command("echo hello; rm -rf /")
        assert valid is False
        assert "forbidden" in _err.lower()

    def test_dangerous_pipe(self) -> None:
        valid, _err, _ = _validate_command("echo hello | cat")
        assert valid is False

    def test_dangerous_backtick(self) -> None:
        valid, _err, _ = _validate_command("echo `whoami`")
        assert valid is False

    def test_dangerous_dollar_paren(self) -> None:
        valid, _err, _ = _validate_command("echo $(whoami)")
        assert valid is False

    def test_dangerous_redirect(self) -> None:
        valid, _err, _ = _validate_command("echo hello > /etc/passwd")
        assert valid is False

    def test_dangerous_and_chain(self) -> None:
        valid, _err, _ = _validate_command("echo a && rm -rf /")
        assert valid is False

    def test_dangerous_or_chain(self) -> None:
        valid, _err, _ = _validate_command("echo a || rm -rf /")
        assert valid is False

    def test_empty_command(self) -> None:
        valid, _err, _ = _validate_command("")
        # Either fails as empty or due to no args
        assert valid is False

    def test_path_executable_stripped(self) -> None:
        valid, _err, args = _validate_command("/usr/bin/git status")
        assert valid is True
        assert args[0] == "/usr/bin/git"

    def test_git_reset_blocked(self) -> None:
        valid, _err, _ = _validate_command("git reset --hard HEAD")
        assert valid is False

    def test_git_clean_blocked(self) -> None:
        valid, _err, _ = _validate_command("git clean -fd")
        assert valid is False

    def test_valid_which_python(self) -> None:
        valid, _err, args = _validate_command("which python")
        assert valid is True
        assert args == ["which", "python"]

    def test_newline_injection(self) -> None:
        valid, _err, _ = _validate_command("echo hello\nrm -rf /")
        assert valid is False
