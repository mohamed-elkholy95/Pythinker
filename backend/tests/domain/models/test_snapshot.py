"""Tests for app.domain.models.snapshot — state snapshot models.

Covers: SnapshotType, FileSnapshot, FileSystemSnapshot, BrowserSnapshot,
TerminalSnapshot, EditorSnapshot, PlanSnapshot, StateSnapshot validators
and factory methods.
"""

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


# ---------------------------------------------------------------------------
# SnapshotType enum
# ---------------------------------------------------------------------------
class TestSnapshotType:
    def test_all_types(self):
        expected = {
            "file_system",
            "file_content",
            "browser_state",
            "terminal_state",
            "editor_state",
            "plan_state",
            "full_state",
        }
        actual = {t.value for t in SnapshotType}
        assert actual == expected


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------
class TestFileSnapshot:
    def test_creation(self):
        fs = FileSnapshot(
            path="/app/main.py",
            content="print('hello')",
            size_bytes=15,
            modified_at=datetime.now(UTC),
        )
        assert fs.path == "/app/main.py"
        assert fs.is_binary is False

    def test_binary_file(self):
        fs = FileSnapshot(
            path="/app/image.png",
            content="<binary>",
            size_bytes=1024,
            modified_at=datetime.now(UTC),
            is_binary=True,
        )
        assert fs.is_binary is True


class TestFileSystemSnapshot:
    def test_empty(self):
        fss = FileSystemSnapshot(working_directory="/app")
        assert fss.files == []
        assert fss.total_files == 0

    def test_with_files(self):
        f = FileSnapshot(path="/a.py", content="x", size_bytes=1, modified_at=datetime.now(UTC))
        fss = FileSystemSnapshot(files=[f], working_directory="/app", total_files=1)
        assert len(fss.files) == 1


class TestBrowserSnapshot:
    def test_minimal(self):
        bs = BrowserSnapshot(url="https://example.com")
        assert bs.title is None
        assert bs.screenshot is None
        assert bs.scroll_x == 0

    def test_full(self):
        bs = BrowserSnapshot(
            url="https://example.com",
            title="Example",
            viewport_width=1920,
            viewport_height=1080,
            scroll_y=500,
        )
        assert bs.title == "Example"
        assert bs.scroll_y == 500


class TestTerminalSnapshot:
    def test_creation(self):
        ts = TerminalSnapshot(buffer="$ ls\nfile.txt", working_directory="/home")
        assert "ls" in ts.buffer
        assert ts.environment is None


class TestEditorSnapshot:
    def test_defaults(self):
        es = EditorSnapshot(file_path="/app/main.py", content="code")
        assert es.cursor_line == 0
        assert es.cursor_column == 0
        assert es.scroll_top == 0
        assert es.selection_start is None


class TestPlanSnapshot:
    def test_creation(self):
        ps = PlanSnapshot(
            plan_id="plan-1",
            current_step_index=2,
            completed_steps=["s1", "s2"],
            status="executing",
        )
        assert ps.current_step_index == 2
        assert len(ps.completed_steps) == 2


# ---------------------------------------------------------------------------
# StateSnapshot — validators
# ---------------------------------------------------------------------------
class TestStateSnapshotValidator:
    def test_file_content_requires_file_content_field(self):
        with pytest.raises(ValidationError, match="file_content"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.FILE_CONTENT,
                # file_content not provided
            )

    def test_browser_state_requires_browser_field(self):
        with pytest.raises(ValidationError, match="browser"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.BROWSER_STATE,
            )

    def test_terminal_state_requires_terminal_field(self):
        with pytest.raises(ValidationError, match="terminal"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.TERMINAL_STATE,
            )

    def test_plan_state_requires_plan_field(self):
        with pytest.raises(ValidationError, match="plan"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.PLAN_STATE,
            )

    def test_full_state_requires_full_state_field(self):
        with pytest.raises(ValidationError, match="full_state"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.FULL_STATE,
            )

    def test_file_system_requires_file_system_field(self):
        with pytest.raises(ValidationError, match="file_system"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.FILE_SYSTEM,
            )

    def test_editor_state_requires_editor_field(self):
        with pytest.raises(ValidationError, match="editor"):
            StateSnapshot(
                session_id="s1",
                sequence_number=1,
                snapshot_type=SnapshotType.EDITOR_STATE,
            )

    def test_valid_file_content_snapshot(self):
        snap = StateSnapshot(
            session_id="s1",
            sequence_number=1,
            snapshot_type=SnapshotType.FILE_CONTENT,
            file_content=FileSnapshot(
                path="/a.py",
                content="code",
                size_bytes=4,
                modified_at=datetime.now(UTC),
            ),
        )
        assert snap.file_content is not None

    def test_valid_browser_snapshot(self):
        snap = StateSnapshot(
            session_id="s1",
            sequence_number=1,
            snapshot_type=SnapshotType.BROWSER_STATE,
            browser=BrowserSnapshot(url="https://example.com"),
        )
        assert snap.browser is not None

    def test_valid_full_state(self):
        snap = StateSnapshot(
            session_id="s1",
            sequence_number=1,
            snapshot_type=SnapshotType.FULL_STATE,
            full_state={"key": "value"},
        )
        assert snap.full_state == {"key": "value"}


# ---------------------------------------------------------------------------
# StateSnapshot — factory methods
# ---------------------------------------------------------------------------
class TestStateSnapshotFactories:
    def test_create_file_snapshot(self):
        snap = StateSnapshot.create_file_snapshot(
            session_id="s1",
            sequence_number=1,
            file_path="/app/main.py",
            content="print('hello')",
        )
        assert snap.snapshot_type == SnapshotType.FILE_CONTENT
        assert snap.file_content is not None
        assert snap.file_content.path == "/app/main.py"
        assert snap.file_content.size_bytes == len(b"print('hello')")
        assert snap.resource_path == "/app/main.py"

    def test_create_file_snapshot_with_action_id(self):
        snap = StateSnapshot.create_file_snapshot(
            session_id="s1",
            sequence_number=1,
            file_path="/a.py",
            content="x",
            action_id="act-1",
        )
        assert snap.action_id == "act-1"

    def test_create_browser_snapshot(self):
        snap = StateSnapshot.create_browser_snapshot(
            session_id="s1",
            sequence_number=2,
            url="https://example.com",
            title="Example",
        )
        assert snap.snapshot_type == SnapshotType.BROWSER_STATE
        assert snap.browser is not None
        assert snap.browser.url == "https://example.com"
        assert snap.browser.title == "Example"
        assert snap.resource_path == "https://example.com"

    def test_create_browser_snapshot_with_screenshot(self):
        snap = StateSnapshot.create_browser_snapshot(
            session_id="s1",
            sequence_number=1,
            url="https://example.com",
            screenshot="base64data",
        )
        assert snap.browser.screenshot == "base64data"

    def test_create_terminal_snapshot(self):
        snap = StateSnapshot.create_terminal_snapshot(
            session_id="s1",
            sequence_number=3,
            buffer="$ ls\nfile.txt",
            working_directory="/home/user",
        )
        assert snap.snapshot_type == SnapshotType.TERMINAL_STATE
        assert snap.terminal is not None
        assert snap.terminal.buffer == "$ ls\nfile.txt"
        assert snap.terminal.working_directory == "/home/user"

    def test_snapshot_gets_uuid(self):
        snap = StateSnapshot.create_file_snapshot(
            session_id="s1",
            sequence_number=1,
            file_path="/a.py",
            content="x",
        )
        assert snap.id is not None
        assert len(snap.id) > 0

    def test_defaults(self):
        snap = StateSnapshot.create_file_snapshot(
            session_id="s1",
            sequence_number=1,
            file_path="/a.py",
            content="x",
        )
        assert snap.is_compressed is False
        assert snap.compressed_size_bytes is None
