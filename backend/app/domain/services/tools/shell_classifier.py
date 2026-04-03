"""Shell command classification for intelligent timeout and parallelism decisions.

Classifies shell commands into categories (search, read, write, destructive, etc.)
using shlex tokenization and a lookup table. For piped commands, the most dangerous
component determines the overall classification.
"""

from __future__ import annotations

import logging
import shlex
from enum import StrEnum

logger = logging.getLogger(__name__)


class CommandClassification(StrEnum):
    """Classification of a shell command by its side-effect profile."""

    SEARCH = "search"
    READ = "read"
    LIST = "list"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXECUTE = "execute"
    NETWORK = "network"
    UNKNOWN = "unknown"


# Severity ordering: most dangerous wins in pipes
_SEVERITY: dict[CommandClassification, int] = {
    CommandClassification.READ: 0,
    CommandClassification.LIST: 0,
    CommandClassification.SEARCH: 0,
    CommandClassification.UNKNOWN: 1,
    CommandClassification.NETWORK: 2,
    CommandClassification.EXECUTE: 3,
    CommandClassification.WRITE: 4,
    CommandClassification.DESTRUCTIVE: 5,
}

# Command -> classification lookup table
_COMMAND_TABLE: dict[str, CommandClassification] = {
    # Search
    "grep": CommandClassification.SEARCH,
    "rg": CommandClassification.SEARCH,
    "ag": CommandClassification.SEARCH,
    "ack": CommandClassification.SEARCH,
    "find": CommandClassification.SEARCH,
    "locate": CommandClassification.SEARCH,
    "which": CommandClassification.SEARCH,
    "whereis": CommandClassification.SEARCH,
    "fd": CommandClassification.SEARCH,
    # Read
    "cat": CommandClassification.READ,
    "head": CommandClassification.READ,
    "tail": CommandClassification.READ,
    "less": CommandClassification.READ,
    "more": CommandClassification.READ,
    "wc": CommandClassification.READ,
    "stat": CommandClassification.READ,
    "file": CommandClassification.READ,
    "md5sum": CommandClassification.READ,
    "sha256sum": CommandClassification.READ,
    "diff": CommandClassification.READ,
    "strings": CommandClassification.READ,
    "hexdump": CommandClassification.READ,
    "xxd": CommandClassification.READ,
    "jq": CommandClassification.READ,
    "yq": CommandClassification.READ,
    "awk": CommandClassification.READ,
    "sed": CommandClassification.READ,  # sed without -i is read-only
    "cut": CommandClassification.READ,
    "sort": CommandClassification.READ,
    "uniq": CommandClassification.READ,
    "tr": CommandClassification.READ,
    "tee": CommandClassification.WRITE,  # tee writes to file
    # List
    "ls": CommandClassification.LIST,
    "tree": CommandClassification.LIST,
    "du": CommandClassification.LIST,
    "df": CommandClassification.LIST,
    "pwd": CommandClassification.LIST,
    "whoami": CommandClassification.LIST,
    "id": CommandClassification.LIST,
    "env": CommandClassification.LIST,
    "printenv": CommandClassification.LIST,
    "uname": CommandClassification.LIST,
    "date": CommandClassification.LIST,
    "uptime": CommandClassification.LIST,
    "ps": CommandClassification.LIST,
    "top": CommandClassification.LIST,
    "htop": CommandClassification.LIST,
    "free": CommandClassification.LIST,
    "lsof": CommandClassification.LIST,
    "netstat": CommandClassification.LIST,
    "ss": CommandClassification.LIST,
    # Write
    "cp": CommandClassification.WRITE,
    "mv": CommandClassification.WRITE,
    "mkdir": CommandClassification.WRITE,
    "touch": CommandClassification.WRITE,
    "chmod": CommandClassification.WRITE,
    "chown": CommandClassification.WRITE,
    "ln": CommandClassification.WRITE,
    "tar": CommandClassification.WRITE,
    "zip": CommandClassification.WRITE,
    "unzip": CommandClassification.WRITE,
    "gzip": CommandClassification.WRITE,
    "gunzip": CommandClassification.WRITE,
    # Destructive
    "rm": CommandClassification.DESTRUCTIVE,
    "rmdir": CommandClassification.DESTRUCTIVE,
    "dd": CommandClassification.DESTRUCTIVE,
    "mkfs": CommandClassification.DESTRUCTIVE,
    "shred": CommandClassification.DESTRUCTIVE,
    # Execute
    "python": CommandClassification.EXECUTE,
    "python3": CommandClassification.EXECUTE,
    "node": CommandClassification.EXECUTE,
    "npm": CommandClassification.EXECUTE,
    "npx": CommandClassification.EXECUTE,
    "bun": CommandClassification.EXECUTE,
    "deno": CommandClassification.EXECUTE,
    "pip": CommandClassification.EXECUTE,
    "pip3": CommandClassification.EXECUTE,
    "conda": CommandClassification.EXECUTE,
    "cargo": CommandClassification.EXECUTE,
    "go": CommandClassification.EXECUTE,
    "make": CommandClassification.EXECUTE,
    "cmake": CommandClassification.EXECUTE,
    "gcc": CommandClassification.EXECUTE,
    "g++": CommandClassification.EXECUTE,
    "rustc": CommandClassification.EXECUTE,
    "java": CommandClassification.EXECUTE,
    "javac": CommandClassification.EXECUTE,
    "ruby": CommandClassification.EXECUTE,
    "perl": CommandClassification.EXECUTE,
    "php": CommandClassification.EXECUTE,
    "bash": CommandClassification.EXECUTE,
    "sh": CommandClassification.EXECUTE,
    "zsh": CommandClassification.EXECUTE,
    # Network
    "curl": CommandClassification.NETWORK,
    "wget": CommandClassification.NETWORK,
    "ssh": CommandClassification.NETWORK,
    "scp": CommandClassification.NETWORK,
    "rsync": CommandClassification.NETWORK,
    "ping": CommandClassification.NETWORK,
    "nslookup": CommandClassification.NETWORK,
    "dig": CommandClassification.NETWORK,
    "traceroute": CommandClassification.NETWORK,
    "nc": CommandClassification.NETWORK,
    "ncat": CommandClassification.NETWORK,
    "git": CommandClassification.NETWORK,  # git often needs network
}

# Semantic-neutral commands (ignored in pipe analysis)
_NEUTRAL_COMMANDS = frozenset({"echo", "printf", "true", "false", ":"})


class ShellCommandClassifier:
    """Classifies shell commands by side-effect profile.

    For piped commands (cmd1 | cmd2 | cmd3), returns the classification
    of the most dangerous component.
    """

    def classify(self, command: str) -> CommandClassification:
        """Classify a shell command string.

        Args:
            command: The shell command to classify.

        Returns:
            The classification of the command.
        """
        if not command or not command.strip():
            return CommandClassification.UNKNOWN

        # Split on pipes to analyze each component
        pipe_segments = self._split_pipes(command)

        if not pipe_segments:
            return CommandClassification.UNKNOWN

        # Classify each segment, take the most dangerous
        classifications = []
        for segment in pipe_segments:
            cls = self._classify_single(segment.strip())
            if cls is not None:
                classifications.append(cls)

        if not classifications:
            return CommandClassification.UNKNOWN

        # Return the most severe classification
        return max(classifications, key=lambda c: _SEVERITY.get(c, 1))

    def _split_pipes(self, command: str) -> list[str]:
        """Split command on pipe operators, handling quoted strings."""
        # Simple pipe split — handles most cases correctly
        segments = []
        current = []
        in_single_quote = False
        in_double_quote = False
        i = 0
        chars = command

        while i < len(chars):
            c = chars[i]
            if c == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
                current.append(c)
            elif c == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                current.append(c)
            elif c == "\\" and i + 1 < len(chars) and (in_double_quote or not in_single_quote):
                current.append(c)
                current.append(chars[i + 1])
                i += 1
            elif c == "|" and not in_single_quote and not in_double_quote:
                # Skip || (logical OR) — not a pipe
                if i + 1 < len(chars) and chars[i + 1] == "|":
                    current.append(c)
                    current.append(chars[i + 1])
                    i += 1
                else:
                    segments.append("".join(current))
                    current = []
            else:
                current.append(c)
            i += 1

        if current:
            segments.append("".join(current))
        return segments

    def _classify_single(self, segment: str) -> CommandClassification | None:
        """Classify a single command segment (no pipes)."""
        try:
            tokens = shlex.split(segment)
        except ValueError:
            # Malformed quoting — fall back to simple split
            tokens = segment.split()

        if not tokens:
            return None

        # Skip env vars, sudo, time, etc.
        cmd = self._extract_base_command(tokens)
        if cmd is None:
            return None

        # Skip neutral commands
        if cmd in _NEUTRAL_COMMANDS:
            return None

        # Check for sed -i (in-place edit = write)
        if cmd == "sed" and any(t == "-i" or t.startswith("-i") for t in tokens[1:]):
            return CommandClassification.WRITE

        # Check for git subcommands that are read-only
        if cmd == "git" and len(tokens) > 1:
            return self._classify_git(tokens[1])

        return _COMMAND_TABLE.get(cmd, CommandClassification.UNKNOWN)

    def _extract_base_command(self, tokens: list[str]) -> str | None:
        """Extract the base command name, skipping prefixes like sudo, env, time."""
        skip_prefixes = {"sudo", "env", "time", "nice", "nohup", "strace", "timeout"}
        for token in tokens:
            # Skip env var assignments (FOO=bar)
            if "=" in token and not token.startswith("-"):
                continue
            # Skip command prefixes
            base = token.split("/")[-1]  # Handle /usr/bin/cmd
            if base in skip_prefixes:
                continue
            return base
        return None

    def _classify_git(self, subcommand: str) -> CommandClassification:
        """Classify git subcommands."""
        read_only_git = {
            "status",
            "log",
            "diff",
            "show",
            "branch",
            "tag",
            "blame",
            "shortlog",
            "describe",
            "rev-parse",
            "ls-files",
            "ls-tree",
            "cat-file",
            "reflog",
            "stash",
        }
        network_git = {"clone", "fetch", "pull", "push", "remote"}
        write_git = {"add", "commit", "merge", "rebase", "reset", "checkout", "switch", "restore"}

        if subcommand in read_only_git:
            return CommandClassification.READ
        if subcommand in network_git:
            return CommandClassification.NETWORK
        if subcommand in write_git:
            return CommandClassification.WRITE
        return CommandClassification.EXECUTE
