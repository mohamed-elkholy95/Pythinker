"""Tests for timeline models (app.domain.models.timeline).

Covers ActionType, ActionStatus, FileChange, BrowserAction,
TerminalCommand, ActionMetadata, and TimelineAction lifecycle.
"""

from datetime import UTC, datetime

from app.domain.models.timeline import (
    ActionMetadata,
    ActionStatus,
    ActionType,
    BrowserAction,
    FileChange,
    TerminalCommand,
    TimelineAction,
)

# ── Enums ────────────────────────────────────────────────────────────


class TestActionType:
    """Tests for ActionType enum."""

    def test_file_operations(self) -> None:
        assert ActionType.FILE_CREATE == "file_create"
        assert ActionType.FILE_EDIT == "file_edit"
        assert ActionType.FILE_DELETE == "file_delete"
        assert ActionType.FILE_READ == "file_read"
        assert ActionType.FILE_MOVE == "file_move"

    def test_browser_operations(self) -> None:
        assert ActionType.BROWSER_NAVIGATE == "browser_navigate"
        assert ActionType.BROWSER_INTERACT == "browser_interact"

    def test_cognitive_actions(self) -> None:
        assert ActionType.THINKING == "thinking"
        assert ActionType.PLANNING == "planning"
        assert ActionType.VERIFICATION == "verification"
        assert ActionType.REFLECTION == "reflection"

    def test_all_unique(self) -> None:
        values = [a.value for a in ActionType]
        assert len(values) == len(set(values))


class TestActionStatus:
    """Tests for ActionStatus enum."""

    def test_values(self) -> None:
        assert ActionStatus.PENDING == "pending"
        assert ActionStatus.EXECUTING == "executing"
        assert ActionStatus.COMPLETED == "completed"
        assert ActionStatus.FAILED == "failed"


# ── Sub-models ───────────────────────────────────────────────────────


class TestFileChange:
    """Tests for FileChange model."""

    def test_creation(self) -> None:
        change = FileChange(path="/app/main.py", operation="edit", diff="@@ -1 +1 @@")
        assert change.path == "/app/main.py"
        assert change.operation == "edit"
        assert change.diff == "@@ -1 +1 @@"

    def test_defaults(self) -> None:
        change = FileChange(path="/test.py", operation="create")
        assert change.content_before is None
        assert change.content_after is None
        assert change.diff is None


class TestBrowserAction:
    """Tests for BrowserAction model."""

    def test_creation(self) -> None:
        action = BrowserAction(
            action_type="click",
            target="#submit-btn",
            value=None,
        )
        assert action.action_type == "click"
        assert action.target == "#submit-btn"


class TestTerminalCommand:
    """Tests for TerminalCommand model."""

    def test_creation(self) -> None:
        cmd = TerminalCommand(
            command="ls -la",
            working_directory="/home/user",
            exit_code=0,
            stdout="file1.txt\nfile2.txt",
        )
        assert cmd.command == "ls -la"
        assert cmd.exit_code == 0


class TestActionMetadata:
    """Tests for ActionMetadata model."""

    def test_defaults(self) -> None:
        meta = ActionMetadata()
        assert meta.file_changes is None
        assert meta.browser_actions is None
        assert meta.terminal_commands is None
        assert meta.reasoning is None
        assert meta.error_message is None

    def test_with_data(self) -> None:
        meta = ActionMetadata(
            file_changes=[FileChange(path="/a.py", operation="create")],
            reasoning="Need to create file for task",
        )
        assert len(meta.file_changes) == 1
        assert meta.reasoning is not None


# ── TimelineAction ───────────────────────────────────────────────────


class TestTimelineAction:
    """Tests for TimelineAction lifecycle."""

    def _make_action(self) -> TimelineAction:
        return TimelineAction(
            session_id="sess-1",
            sequence_number=1,
            action_type=ActionType.FILE_CREATE,
        )

    def test_creation(self) -> None:
        action = self._make_action()
        assert action.session_id == "sess-1"
        assert action.sequence_number == 1
        assert action.action_type == ActionType.FILE_CREATE
        assert action.status == ActionStatus.PENDING
        assert action.id is not None
        assert action.timestamp is not None

    def test_mark_completed(self) -> None:
        action = self._make_action()
        action.mark_completed(result="File created")
        assert action.status == ActionStatus.COMPLETED
        assert action.function_result == "File created"
        assert action.completed_at is not None
        assert action.duration_ms is not None
        assert action.duration_ms >= 0

    def test_mark_failed(self) -> None:
        action = self._make_action()
        action.mark_failed("Permission denied")
        assert action.status == ActionStatus.FAILED
        assert action.metadata.error_message == "Permission denied"
        assert action.completed_at is not None
        assert action.duration_ms is not None

    def test_tool_fields(self) -> None:
        action = TimelineAction(
            session_id="sess-1",
            sequence_number=2,
            action_type=ActionType.SEARCH,
            tool_name="web_search",
            tool_call_id="tc-1",
            function_name="search",
            function_args={"query": "test"},
        )
        assert action.tool_name == "web_search"
        assert action.function_args == {"query": "test"}

    def test_duration_calculation(self) -> None:
        action = self._make_action()
        # Manually set started_at to a known time
        action.started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        action.mark_completed()
        assert action.duration_ms is not None
        assert action.duration_ms > 0  # Should be a very large number since started_at is far in past
