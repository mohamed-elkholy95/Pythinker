"""State snapshot models for timeline reconstruction."""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SnapshotType(str, Enum):
    """Types of state snapshots."""

    FILE_SYSTEM = "file_system"  # Complete file system state
    FILE_CONTENT = "file_content"  # Single file content
    BROWSER_STATE = "browser_state"  # Browser DOM/screenshot
    TERMINAL_STATE = "terminal_state"  # Terminal buffer state
    EDITOR_STATE = "editor_state"  # Editor state (cursor, selection)
    PLAN_STATE = "plan_state"  # Plan execution state
    FULL_STATE = "full_state"  # Complete session state (periodic checkpoint)


class FileSnapshot(BaseModel):
    """Snapshot of a single file."""

    path: str
    content: str
    size_bytes: int
    modified_at: datetime
    is_binary: bool = False


class FileSystemSnapshot(BaseModel):
    """Snapshot of file system state."""

    files: list[FileSnapshot] = Field(default_factory=list)
    working_directory: str
    total_files: int = 0


class BrowserSnapshot(BaseModel):
    """Snapshot of browser state."""

    url: str
    title: str | None = None
    screenshot: str | None = None  # Base64 encoded
    dom_snapshot: str | None = None  # Compressed DOM
    viewport_width: int | None = None
    viewport_height: int | None = None
    scroll_x: int = 0
    scroll_y: int = 0


class TerminalSnapshot(BaseModel):
    """Snapshot of terminal state."""

    buffer: str  # Terminal output buffer
    working_directory: str
    environment: dict[str, str] | None = None
    cursor_position: int | None = None


class EditorSnapshot(BaseModel):
    """Snapshot of editor state."""

    file_path: str
    content: str
    cursor_line: int = 0
    cursor_column: int = 0
    selection_start: int | None = None
    selection_end: int | None = None
    scroll_top: int = 0


class PlanSnapshot(BaseModel):
    """Snapshot of plan execution state."""

    plan_id: str
    current_step_index: int
    completed_steps: list[str]  # Step IDs
    status: str


class StateSnapshot(BaseModel):
    """
    Point-in-time state snapshot for timeline reconstruction.
    Stored periodically (every N actions) for efficient state reconstruction.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    action_id: str | None = None  # Action that triggered this snapshot
    sequence_number: int  # Position in timeline

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Snapshot type
    snapshot_type: SnapshotType

    # Resource identification
    resource_path: str | None = None  # File path, URL, etc.

    # Snapshot data (one of these will be populated based on type)
    file_system: FileSystemSnapshot | None = None
    file_content: FileSnapshot | None = None
    browser: BrowserSnapshot | None = None
    terminal: TerminalSnapshot | None = None
    editor: EditorSnapshot | None = None
    plan: PlanSnapshot | None = None

    # For full state snapshots, we might have all of these
    full_state: dict[str, Any] | None = None

    # Compression info
    is_compressed: bool = False
    compressed_size_bytes: int | None = None

    @model_validator(mode="after")
    def validate_snapshot_data_matches_type(self) -> "StateSnapshot":
        """Ensure the populated sub-model matches the snapshot_type."""
        type_to_field = {
            SnapshotType.FILE_SYSTEM: "file_system",
            SnapshotType.FILE_CONTENT: "file_content",
            SnapshotType.BROWSER_STATE: "browser",
            SnapshotType.TERMINAL_STATE: "terminal",
            SnapshotType.EDITOR_STATE: "editor",
            SnapshotType.PLAN_STATE: "plan",
            SnapshotType.FULL_STATE: "full_state",
        }
        expected_field = type_to_field.get(self.snapshot_type)
        if expected_field and getattr(self, expected_field) is None:
            raise ValueError(
                f"Snapshot type '{self.snapshot_type.value}' requires "
                f"'{expected_field}' to be populated"
            )
        return self

    @classmethod
    def create_file_snapshot(
        cls, session_id: str, sequence_number: int, file_path: str, content: str, action_id: str | None = None
    ) -> "StateSnapshot":
        """Create a file content snapshot."""
        return cls(
            session_id=session_id,
            action_id=action_id,
            sequence_number=sequence_number,
            snapshot_type=SnapshotType.FILE_CONTENT,
            resource_path=file_path,
            file_content=FileSnapshot(
                path=file_path,
                content=content,
                size_bytes=len(content.encode("utf-8")),
                modified_at=datetime.now(UTC),
            ),
        )

    @classmethod
    def create_browser_snapshot(
        cls,
        session_id: str,
        sequence_number: int,
        url: str,
        screenshot: str | None = None,
        title: str | None = None,
        action_id: str | None = None,
    ) -> "StateSnapshot":
        """Create a browser state snapshot."""
        return cls(
            session_id=session_id,
            action_id=action_id,
            sequence_number=sequence_number,
            snapshot_type=SnapshotType.BROWSER_STATE,
            resource_path=url,
            browser=BrowserSnapshot(
                url=url,
                title=title,
                screenshot=screenshot,
            ),
        )

    @classmethod
    def create_terminal_snapshot(
        cls, session_id: str, sequence_number: int, buffer: str, working_directory: str, action_id: str | None = None
    ) -> "StateSnapshot":
        """Create a terminal state snapshot."""
        return cls(
            session_id=session_id,
            action_id=action_id,
            sequence_number=sequence_number,
            snapshot_type=SnapshotType.TERMINAL_STATE,
            terminal=TerminalSnapshot(
                buffer=buffer,
                working_directory=working_directory,
            ),
        )
