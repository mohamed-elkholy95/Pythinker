"""Tests for ShellCommandClassifier and TimeoutPolicy."""

from __future__ import annotations

from app.domain.services.tools.shell_classifier import CommandClassification, ShellCommandClassifier
from app.domain.services.tools.timeout_policy import TimeoutPolicy


class TestShellCommandClassifier:
    def setup_method(self):
        self.clf = ShellCommandClassifier()

    # ── Basic classification ──────────────────────────────────────────

    def test_search_commands(self):
        for cmd in ["grep foo bar.txt", "rg pattern src/", "find . -name '*.py'", "fd .py"]:
            assert self.clf.classify(cmd) == CommandClassification.SEARCH, cmd

    def test_read_commands(self):
        for cmd in ["cat file.txt", "head -n 10 log.txt", "tail -f log.txt", "wc -l file.txt", "jq . data.json"]:
            assert self.clf.classify(cmd) == CommandClassification.READ, cmd

    def test_list_commands(self):
        for cmd in ["ls -la", "tree src/", "du -sh .", "df -h", "ps aux", "printenv"]:
            assert self.clf.classify(cmd) == CommandClassification.LIST, cmd

    def test_write_commands(self):
        for cmd in ["cp src dst", "mv old new", "mkdir -p dir", "touch file", "chmod 755 file"]:
            assert self.clf.classify(cmd) == CommandClassification.WRITE, cmd

    def test_destructive_commands(self):
        for cmd in ["rm -rf /tmp/dir", "rmdir empty_dir", "shred secret.txt"]:
            assert self.clf.classify(cmd) == CommandClassification.DESTRUCTIVE, cmd

    def test_execute_commands(self):
        for cmd in ["python3 script.py", "node app.js", "npm install", "pip install requests", "make build"]:
            assert self.clf.classify(cmd) == CommandClassification.EXECUTE, cmd

    def test_network_commands(self):
        for cmd in ["curl https://example.com", "wget https://example.com/file", "ping 8.8.8.8"]:
            assert self.clf.classify(cmd) == CommandClassification.NETWORK, cmd

    def test_unknown_command(self):
        assert self.clf.classify("some_totally_unknown_binary --flag") == CommandClassification.UNKNOWN

    # ── Edge cases ────────────────────────────────────────────────────

    def test_empty_command(self):
        assert self.clf.classify("") == CommandClassification.UNKNOWN

    def test_whitespace_only(self):
        assert self.clf.classify("   ") == CommandClassification.UNKNOWN

    def test_neutral_commands_skipped(self):
        # echo alone should not produce a segment classification
        result = self.clf.classify("echo hello")
        assert result == CommandClassification.UNKNOWN

    def test_sed_without_i_flag_is_read(self):
        assert self.clf.classify("sed 's/foo/bar/' file.txt") == CommandClassification.READ

    def test_sed_with_i_flag_is_write(self):
        assert self.clf.classify("sed -i 's/foo/bar/' file.txt") == CommandClassification.WRITE

    def test_tee_is_write(self):
        assert self.clf.classify("echo foo | tee output.txt") == CommandClassification.WRITE

    # ── Pipe analysis — most dangerous wins ──────────────────────────

    def test_pipe_search_into_read(self):
        # grep | head → SEARCH (max of SEARCH=0 and READ=0 → first wins, both same)
        result = self.clf.classify("grep foo bar.txt | head -5")
        assert result in {CommandClassification.SEARCH, CommandClassification.READ}

    def test_pipe_read_into_destructive(self):
        result = self.clf.classify("cat file.txt | rm -rf /")
        assert result == CommandClassification.DESTRUCTIVE

    def test_pipe_with_neutral_command(self):
        result = self.clf.classify("echo hello | grep hello")
        assert result == CommandClassification.SEARCH

    def test_logical_or_not_treated_as_pipe(self):
        # || should not split into two segments
        result = self.clf.classify("ls nonexistent || echo fallback")
        assert result == CommandClassification.LIST

    # ── Git subcommand classification ─────────────────────────────────

    def test_git_status_is_read(self):
        assert self.clf.classify("git status") == CommandClassification.READ

    def test_git_log_is_read(self):
        assert self.clf.classify("git log --oneline") == CommandClassification.READ

    def test_git_push_is_network(self):
        assert self.clf.classify("git push origin main") == CommandClassification.NETWORK

    def test_git_clone_is_network(self):
        assert self.clf.classify("git clone https://github.com/foo/bar") == CommandClassification.NETWORK

    def test_git_commit_is_write(self):
        assert self.clf.classify("git commit -m 'msg'") == CommandClassification.WRITE

    def test_git_add_is_write(self):
        assert self.clf.classify("git add .") == CommandClassification.WRITE

    def test_git_unknown_subcommand_is_execute(self):
        assert self.clf.classify("git bisect start") == CommandClassification.EXECUTE

    # ── Prefix skipping (sudo, env vars) ─────────────────────────────

    def test_sudo_prefix_stripped(self):
        assert self.clf.classify("sudo rm -rf /tmp/test") == CommandClassification.DESTRUCTIVE

    def test_env_var_assignment_stripped(self):
        assert self.clf.classify("PYTHONPATH=/src python3 script.py") == CommandClassification.EXECUTE

    def test_absolute_path_command(self):
        assert self.clf.classify("/usr/bin/grep foo bar") == CommandClassification.SEARCH

    # ── Quoted strings ────────────────────────────────────────────────

    def test_single_quoted_pipe_not_split(self):
        result = self.clf.classify("echo 'a | b'")
        # The quoted | should not be treated as a pipe separator
        assert result == CommandClassification.UNKNOWN  # echo is neutral, result from echo only

    def test_double_quoted_pipe_not_split(self):
        result = self.clf.classify('grep "a | b" file.txt')
        assert result == CommandClassification.SEARCH


class TestTimeoutPolicy:
    def setup_method(self):
        self.policy = TimeoutPolicy()

    def test_search_tier(self):
        tier = self.policy.get_tier(CommandClassification.SEARCH)
        assert tier.soft_seconds == 30
        assert tier.hard_seconds == 60

    def test_read_tier(self):
        tier = self.policy.get_tier(CommandClassification.READ)
        assert tier.soft_seconds == 30
        assert tier.hard_seconds == 60

    def test_list_tier(self):
        tier = self.policy.get_tier(CommandClassification.LIST)
        assert tier.soft_seconds == 30
        assert tier.hard_seconds == 60

    def test_write_tier(self):
        tier = self.policy.get_tier(CommandClassification.WRITE)
        assert tier.soft_seconds == 60
        assert tier.hard_seconds == 120

    def test_execute_tier(self):
        tier = self.policy.get_tier(CommandClassification.EXECUTE)
        assert tier.soft_seconds == 60
        assert tier.hard_seconds == 120

    def test_network_tier(self):
        tier = self.policy.get_tier(CommandClassification.NETWORK)
        assert tier.soft_seconds == 90
        assert tier.hard_seconds == 300

    def test_destructive_tier(self):
        tier = self.policy.get_tier(CommandClassification.DESTRUCTIVE)
        assert tier.soft_seconds == 60
        assert tier.hard_seconds == 120

    def test_unknown_tier(self):
        tier = self.policy.get_tier(CommandClassification.UNKNOWN)
        assert tier.soft_seconds == 60
        assert tier.hard_seconds == 120

    def test_all_classifications_covered(self):
        """Every CommandClassification must have a tier entry."""
        for classification in CommandClassification:
            tier = self.policy.get_tier(classification)
            assert tier.hard_seconds > tier.soft_seconds, f"{classification}: hard must exceed soft"
