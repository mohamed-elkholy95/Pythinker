"""State snapshot models for timeline reconstruction."""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import uuid


class SnapshotType(str, Enum):
    """Types of state snapshots."""
    FILE_SYSTEM = "file_system"      # Complete file system state
    FILE_CONTENT = "file_content"    # Single file content
    BROWSER_STATE = "browser_state"  # Browser DOM/screenshot
    TERMINAL_STATE = "terminal_state"  # Terminal buffer state
    EDITOR_STATE = "editor_state"    # Editor state (cursor, selection)
    PLAN_STATE = "plan_state"        # Plan execution state
    FULL_STATE = "full_state"        # Complete session state (periodic checkpoint)


class FileSnapshot(BaseModel):
    """Snapshot of a single file."""
    path: str
    content: str
    size_bytes: int
    modified_at: datetime
    is_binary: bool = False


class FileSystemSnapshot(BaseModel):
    """Snapshot of file system state."""
    files: List[FileSnapshot] = []
    working_directory: str
    total_files: int = 0


class BrowserSnapshot(BaseModel):
    """Snapshot of browser state."""
    url: str
    title: Optional[str] = None
    screenshot: Optional[str] = None  # Base64 encoded
    dom_snapshot: Optional[str] = None  # Compressed DOM
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None
    scroll_x: int = 0
    scroll_y: int = 0


class TerminalSnapshot(BaseModel):
    """Snapshot of terminal state."""
    buffer: str  # Terminal output buffer
    working_directory: str
    environment: Optional[Dict[str, str]] = None
    cursor_position: Optional[int] = None


class EditorSnapshot(BaseModel):
    """Snapshot of editor state."""
    file_path: str
    content: str
    cursor_line: int = 0
    cursor_column: int = 0
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    scroll_top: int = 0


class PlanSnapshot(BaseModel):
    """Snapshot of plan execution state."""
    plan_id: str
    current_step_index: int
    completed_steps: List[str]  # Step IDs
    status: str


class StateSnapshot(BaseModel):
    """
    Point-in-time state snapshot for timeline reconstruction.
    Stored periodically (every N actions) for efficient state reconstruction.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    action_id: Optional[str] = None  # Action that triggered this snapshot
    sequence_number: int  # Position in timeline

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)

    # Snapshot type
    snapshot_type: SnapshotType

    # Resource identification
    resource_path: Optional[str] = None  # File path, URL, etc.

    # Snapshot data (one of these will be populated based on type)
    file_system: Optional[FileSystemSnapshot] = None
    file_content: Optional[FileSnapshot] = None
    browser: Optional[BrowserSnapshot] = None
    terminal: Optional[TerminalSnapshot] = None
    editor: Optional[EditorSnapshot] = None
    plan: Optional[PlanSnapshot] = None

    # For full state snapshots, we might have all of these
    full_state: Optional[Dict[str, Any]] = None

    # Compression info
    is_compressed: bool = False
    compressed_size_bytes: Optional[int] = None

    @classmethod
    def create_file_snapshot(
        cls,
        session_id: str,
        sequence_number: int,
        file_path: str,
        content: str,
        action_id: Optional[str] = None
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
                size_bytes=len(content.encode('utf-8')),
                modified_at=datetime.now(),
            )
        )

    @classmethod
    def create_browser_snapshot(
        cls,
        session_id: str,
        sequence_number: int,
        url: str,
        screenshot: Optional[str] = None,
        title: Optional[str] = None,
        action_id: Optional[str] = None
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
            )
        )

    @classmethod
    def create_terminal_snapshot(
        cls,
        session_id: str,
        sequence_number: int,
        buffer: str,
        working_directory: str,
        action_id: Optional[str] = None
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
            )
        )
