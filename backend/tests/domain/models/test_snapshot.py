"""Tests for state snapshot domain models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.models.snapshot import (
    BrowserSnapshot,
    EditorSnapshot,
    FileSnapshot,
    FileSystemSnapshot,
    PlanSnapshot,
    SnapshotType,
    StateSnapshot,
    TerminalSnapshot,
)


class TestSnapshotType:
    def test_all_values(self) -> None:
        expected = {
            "file_system",
            "file_content",
            "browser_state",
            "terminal_state",
            "editor_state",
            "plan_state",
            "full_state",
        }
        assert {s.value for s in SnapshotType} == expected

    def test_count(self) -> None:
        assert len(SnapshotType) == 7

    def test_is_str_enum(self) -> None:
        assert isinstance(SnapshotType.FILE_SYSTEM, str)


class TestFileSnapshot:
    def test_required_fields(self) -> None:
        now = datetime.now(UTC)
        snap = FileSnapshot(
            path="/app/main.py", content="print('hi')", size_bytes=10, modified_at=now
        )
        assert snap.path == "/app/main.py"
        assert snap.is_binary is False

    def test_binary_flag(self) -> None:
        snap = FileSnapshot(
            path="/data/img.png",
            content="",
            size_bytes=1024,
            modified_at=datetime.now(UTC),
            is_binary=True,
        )
        assert snap.is_binary is True


class TestFileSystemSnapshot:
    def test_defaults(self) -> None:
        snap = FileSystemSnapshot(working_directory="/app")
        assert snap.files == []
        assert snap.total_files == 0


class TestBrowserSnapshot:
    def test_required_url(self) -> None:
        snap = BrowserSnapshot(url="https://example.com")
        assert snap.url == "https://example.com"
        assert snap.title is None
        assert snap.scroll_x == 0
        assert snap.scroll_y == 0


class TestTerminalSnapshot:
    def test_required_fields(self) -> None:
        snap = TerminalSnapshot(buffer="$ ls\nfile.py", working_directory="/home")
        assert snap.buffer == "$ ls\nfile.py"
        assert snap.environment is None


class TestEditorSnapshot:
    def test_defaults(self) -> None:
        snap = EditorSnapshot(file_path="/app/main.py", content="code")
        assert snap.cursor_line == 0
        assert snap.cursor_column == 0
        assert snap.scroll_top == 0


class TestPlanSnapshot:
    def test_required_fields(self) -> None:
        snap = PlanSnapshot(
            plan_id="p1",
            current_step_index=2,
            completed_steps=["s1", "s2"],
            status="executing",
        )
        assert snap.current_step_index == 2
        assert len(snap.completed_steps) == 2


class TestStateSnapshot:
    def test_file_content_snapshot_valid(self) -> None:
        snap = StateSnapshot(
            session_id="sess-1",
            sequence_number=1,
            snapshot_type=SnapshotType.FILE_CONTENT,
            file_content=FileSnapshot(
                path="/f.py",
                content="x=1",
                size_bytes=3,
                modified_at=datetime.now(UTC),
            ),
        )
        assert snap.snapshot_type == SnapshotType.FILE_CONTENT

    def test_missing_submodel_raises(self) -> None:
        with pytest.raises(ValidationError, match="file_content"):
            StateSnapshot(
                session_id="sess-1",
                sequence_number=1,
                snapshot_type=SnapshotType.FILE_CONTENT,
            )

    def test_browser_snapshot_missing_raises(self) -> None:
        with pytest.raises(ValidationError, match="browser"):
            StateSnapshot(
                session_id="sess-1",
                sequence_number=1,
                snapshot_type=SnapshotType.BROWSER_STATE,
            )

    def test_auto_generated_id(self) -> None:
        snap = StateSnapshot(
            session_id="s1",
            sequence_number=0,
            snapshot_type=SnapshotType.FULL_STATE,
            full_state={"key": "value"},
        )
        assert snap.id  # UUID string
        assert len(snap.id) > 10

    def test_create_file_snapshot_factory(self) -> None:
        snap = StateSnapshot.create_file_snapshot(
            session_id="sess-1",
            sequence_number=5,
            file_path="/app/main.py",
            content="print('hello')",
        )
        assert snap.snapshot_type == SnapshotType.FILE_CONTENT
        assert snap.resource_path == "/app/main.py"
        assert snap.file_content is not None
        assert snap.file_content.content == "print('hello')"

    def test_create_browser_snapshot_factory(self) -> None:
        snap = StateSnapshot.create_browser_snapshot(
            session_id="sess-2",
            sequence_number=3,
            url="https://example.com",
            title="Example",
        )
        assert snap.snapshot_type == SnapshotType.BROWSER_STATE
        assert snap.browser is not None
        assert snap.browser.url == "https://example.com"
        assert snap.browser.title == "Example"

    def test_create_terminal_snapshot_factory(self) -> None:
        snap = StateSnapshot.create_terminal_snapshot(
            session_id="sess-3",
            sequence_number=1,
            buffer="$ whoami\nroot",
            working_directory="/root",
        )
        assert snap.snapshot_type == SnapshotType.TERMINAL_STATE
        assert snap.terminal is not None
        assert snap.terminal.buffer == "$ whoami\nroot"

    def test_compression_defaults(self) -> None:
        snap = StateSnapshot(
            session_id="s1",
            sequence_number=0,
            snapshot_type=SnapshotType.FULL_STATE,
            full_state={},
        )
        assert snap.is_compressed is False
        assert snap.compressed_size_bytes is None

    def test_terminal_missing_raises(self) -> None:
        with pytest.raises(ValidationError, match="terminal"):
            StateSnapshot(
                session_id="s1",
                sequence_number=0,
                snapshot_type=SnapshotType.TERMINAL_STATE,
            )
