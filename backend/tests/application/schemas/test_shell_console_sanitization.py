"""Tests for ConsoleRecord / ShellViewResponse CMD marker sanitization.

Validates that Pydantic ``@field_validator(mode='before')`` automatically
strips ``[CMD_BEGIN]``/``[CMD_END]`` markers at the DTO boundary so they
never reach the frontend.
"""

from app.application.schemas.session import ConsoleRecord, ShellViewResponse


class TestConsoleRecordSanitization:
    """ConsoleRecord should strip markers from ps1 and output fields."""

    def test_ps1_markers_stripped(self) -> None:
        r = ConsoleRecord(
            ps1="\nubuntu@sandbox:~\n[CMD_END]",
            command="uname -a",
            output="plain output",
        )
        assert "[CMD_END]" not in r.ps1
        assert "[CMD_BEGIN]" not in r.ps1
        assert r.ps1 == "ubuntu@sandbox:~ $"

    def test_ps1_without_markers_unchanged(self) -> None:
        r = ConsoleRecord(ps1="ubuntu@sandbox:~ $", command="ls", output="")
        assert r.ps1 == "ubuntu@sandbox:~ $"

    def test_ps1_appends_dollar_if_missing(self) -> None:
        r = ConsoleRecord(ps1="user@host:~", command="ls", output="")
        assert r.ps1.endswith("$")

    def test_ps1_no_double_dollar(self) -> None:
        r = ConsoleRecord(ps1="user@host:~ $", command="ls", output="")
        assert r.ps1 == "user@host:~ $"
        assert not r.ps1.endswith("$ $")

    def test_output_markers_stripped(self) -> None:
        r = ConsoleRecord(
            ps1="\nubuntu@sandbox:~\n[CMD_END]",
            command="uname -a",
            output="[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] uname -a\nLinux sandbox 6.17.0",
        )
        assert "[CMD_BEGIN]" not in r.output
        assert "[CMD_END]" not in r.output
        assert "Linux sandbox 6.17.0" in r.output

    def test_output_header_stripped(self) -> None:
        """The duplicated PS1+command header is removed, leaving only stdout."""
        r = ConsoleRecord(
            ps1="\nubuntu@sandbox:~\n[CMD_END]",
            command="ls -la",
            output="[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] ls -la\nfile1.txt\nfile2.py",
        )
        assert r.output == "file1.txt\nfile2.py"

    def test_output_without_markers_unchanged(self) -> None:
        r = ConsoleRecord(ps1="$ ", command="echo hi", output="hi")
        assert r.output == "hi"

    def test_empty_output_safe(self) -> None:
        r = ConsoleRecord(ps1="$ ", command="true", output="")
        assert r.output == ""

    def test_multi_command_output(self) -> None:
        """Commands with pipes/chains should have their output preserved."""
        r = ConsoleRecord(
            ps1="\nubuntu@sandbox:~\n[CMD_END]",
            command="whoami && hostname",
            output="[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] whoami && hostname\nubuntu\nsandbox",
        )
        assert r.output == "ubuntu\nsandbox"


class TestShellViewResponseSanitization:
    """ShellViewResponse should strip markers from the top-level output."""

    def test_output_markers_stripped(self) -> None:
        resp = ShellViewResponse(
            output="[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] ls\nfile1.txt",
            session_id="test-123",
        )
        assert "[CMD_BEGIN]" not in resp.output
        assert "[CMD_END]" not in resp.output

    def test_console_records_cleaned(self) -> None:
        resp = ShellViewResponse(
            output="clean output",
            session_id="test-123",
            console=[
                {
                    "ps1": "\nubuntu@sandbox:~\n[CMD_END]",
                    "command": "ls",
                    "output": "[CMD_BEGIN]\nubuntu@sandbox:~\n[CMD_END] ls\nfile1.txt",
                }
            ],
        )
        assert resp.console is not None
        assert resp.console[0].ps1 == "ubuntu@sandbox:~ $"
        assert "[CMD" not in resp.console[0].output
        assert "file1.txt" in resp.console[0].output

    def test_none_console_safe(self) -> None:
        resp = ShellViewResponse(output="hello", session_id="x")
        assert resp.console is None

    def test_empty_console_safe(self) -> None:
        resp = ShellViewResponse(output="hello", session_id="x", console=[])
        assert resp.console == []
