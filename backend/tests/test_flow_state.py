"""
Tests for the flow state module.
"""

from app.domain.models.flow_state import FlowStateSnapshot, FlowStatus


class TestFlowStatus:
    """Tests for FlowStatus enum"""

    def test_all_statuses_exist(self):
        """Verify all expected statuses exist"""
        expected = ["IDLE", "PLANNING", "EXECUTING", "UPDATING", "SUMMARIZING", "COMPLETED", "ERROR", "PAUSED"]
        for status in expected:
            assert hasattr(FlowStatus, status)


class TestFlowStateSnapshot:
    """Tests for FlowStateSnapshot model"""

    def test_initialization(self):
        """Test basic initialization"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456"
        )
        assert snapshot.agent_id == "agent-123"
        assert snapshot.session_id == "session-456"
        assert snapshot.status == FlowStatus.IDLE

    def test_update(self):
        """Test update method creates new snapshot"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456"
        )

        updated = snapshot.update(status=FlowStatus.PLANNING)

        # Original should be unchanged
        assert snapshot.status == FlowStatus.IDLE
        # New snapshot should have updated status
        assert updated.status == FlowStatus.PLANNING
        assert updated.agent_id == "agent-123"

    def test_mark_step_completed(self):
        """Test marking a step as completed"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            current_step_id="step-1"
        )

        updated = snapshot.mark_step_completed("step-1")

        assert "step-1" in updated.completed_steps
        assert updated.current_step_id is None

    def test_mark_step_completed_no_duplicate(self):
        """Test marking same step twice doesn't duplicate"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            completed_steps=["step-1"]
        )

        updated = snapshot.mark_step_completed("step-1")

        assert updated.completed_steps.count("step-1") == 1

    def test_enter_error_state(self):
        """Test entering error state"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.EXECUTING
        )

        updated = snapshot.enter_error_state("Something failed", "TOOL_ERROR")

        assert updated.status == FlowStatus.ERROR
        assert updated.previous_status == FlowStatus.EXECUTING
        assert updated.error_message == "Something failed"
        assert updated.error_type == "TOOL_ERROR"

    def test_recover_from_error(self):
        """Test recovering from error state"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.ERROR,
            previous_status=FlowStatus.EXECUTING,
            error_message="Failed",
            recovery_attempts=0
        )

        updated = snapshot.recover_from_error()

        assert updated.status == FlowStatus.EXECUTING
        assert updated.previous_status == FlowStatus.ERROR
        assert updated.recovery_attempts == 1
        assert updated.error_message is None

    def test_recover_from_error_no_previous(self):
        """Test recovering with no previous status defaults to IDLE"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.ERROR,
            previous_status=None
        )

        updated = snapshot.recover_from_error()

        assert updated.status == FlowStatus.IDLE

    def test_recover_from_non_error(self):
        """Test recovery from non-error state returns unchanged"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.EXECUTING
        )

        updated = snapshot.recover_from_error()

        assert updated is snapshot  # Same object returned

    def test_can_recover_true(self):
        """Test can_recover returns true when within attempts"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.ERROR,
            recovery_attempts=1
        )

        assert snapshot.can_recover(max_attempts=3) is True

    def test_can_recover_false_at_limit(self):
        """Test can_recover returns false at attempt limit"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.ERROR,
            recovery_attempts=3
        )

        assert snapshot.can_recover(max_attempts=3) is False

    def test_can_recover_false_not_error(self):
        """Test can_recover returns false when not in error state"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.EXECUTING
        )

        assert snapshot.can_recover() is False

    def test_increment_iteration(self):
        """Test incrementing iteration count"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            iteration_count=5
        )

        updated = snapshot.increment_iteration()

        assert updated.iteration_count == 6

    def test_is_complete(self):
        """Test is_complete check"""
        incomplete = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.EXECUTING
        )
        complete = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.COMPLETED
        )

        assert incomplete.is_complete() is False
        assert complete.is_complete() is True

    def test_is_error(self):
        """Test is_error check"""
        normal = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.EXECUTING
        )
        error = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            status=FlowStatus.ERROR
        )

        assert normal.is_error() is False
        assert error.is_error() is True

    def test_metadata(self):
        """Test metadata field"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456",
            metadata={"custom_key": "custom_value"}
        )

        assert snapshot.metadata["custom_key"] == "custom_value"

    def test_timestamps_set(self):
        """Test that timestamps are automatically set"""
        snapshot = FlowStateSnapshot(
            agent_id="agent-123",
            session_id="session-456"
        )

        assert snapshot.created_at is not None
        assert snapshot.updated_at is not None
        assert snapshot.last_activity_at is not None
