"""Tests for SecurityAssessor, SecurityAssessment, and ActionSecurityRisk."""

import pytest

from app.domain.models.tool_permission import PermissionTier
from app.domain.services.agents.security_assessor import (
    ActionSecurityRisk,
    SecurityAssessment,
    SecurityAssessor,
)

# ---------------------------------------------------------------------------
# ActionSecurityRisk enum
# ---------------------------------------------------------------------------


class TestActionSecurityRisk:
    def test_low_value(self):
        assert ActionSecurityRisk.LOW == "low"

    def test_medium_value(self):
        assert ActionSecurityRisk.MEDIUM == "medium"

    def test_high_value(self):
        assert ActionSecurityRisk.HIGH == "high"

    def test_critical_value(self):
        assert ActionSecurityRisk.CRITICAL == "critical"

    def test_member_count(self):
        assert len(ActionSecurityRisk) == 4

    def test_is_str_subclass(self):
        assert isinstance(ActionSecurityRisk.LOW, str)

    def test_all_members_are_strings(self):
        for member in ActionSecurityRisk:
            assert isinstance(member, str)

    def test_lookup_by_value_low(self):
        assert ActionSecurityRisk("low") is ActionSecurityRisk.LOW

    def test_lookup_by_value_critical(self):
        assert ActionSecurityRisk("critical") is ActionSecurityRisk.CRITICAL

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ActionSecurityRisk("unknown")


# ---------------------------------------------------------------------------
# SecurityAssessment dataclass
# ---------------------------------------------------------------------------


class TestSecurityAssessment:
    def test_required_fields_stored(self):
        assessment = SecurityAssessment(
            blocked=False,
            reason="ok",
            risk_level=ActionSecurityRisk.LOW,
        )
        assert assessment.blocked is False
        assert assessment.reason == "ok"
        assert assessment.risk_level is ActionSecurityRisk.LOW

    def test_requires_confirmation_defaults_to_false(self):
        assessment = SecurityAssessment(
            blocked=False,
            reason="ok",
            risk_level=ActionSecurityRisk.LOW,
        )
        assert assessment.requires_confirmation is False

    def test_suggestions_defaults_to_empty_list(self):
        assessment = SecurityAssessment(
            blocked=False,
            reason="ok",
            risk_level=ActionSecurityRisk.LOW,
        )
        assert assessment.suggestions == []

    def test_suggestions_none_becomes_empty_list(self):
        assessment = SecurityAssessment(
            blocked=True,
            reason="blocked",
            risk_level=ActionSecurityRisk.HIGH,
            suggestions=None,
        )
        assert assessment.suggestions == []

    def test_suggestions_not_shared_across_instances(self):
        a = SecurityAssessment(blocked=False, reason="a", risk_level=ActionSecurityRisk.LOW)
        b = SecurityAssessment(blocked=False, reason="b", risk_level=ActionSecurityRisk.LOW)
        a.suggestions.append("hint")
        assert b.suggestions == []

    def test_suggestions_provided_explicitly(self):
        assessment = SecurityAssessment(
            blocked=False,
            reason="ok",
            risk_level=ActionSecurityRisk.LOW,
            suggestions=["use safe path"],
        )
        assert assessment.suggestions == ["use safe path"]

    def test_blocked_true_stores_correctly(self):
        assessment = SecurityAssessment(
            blocked=True,
            reason="denied",
            risk_level=ActionSecurityRisk.CRITICAL,
        )
        assert assessment.blocked is True

    def test_requires_confirmation_true_stores_correctly(self):
        assessment = SecurityAssessment(
            blocked=False,
            reason="needs review",
            risk_level=ActionSecurityRisk.MEDIUM,
            requires_confirmation=True,
        )
        assert assessment.requires_confirmation is True


# ---------------------------------------------------------------------------
# SecurityAssessor class
# ---------------------------------------------------------------------------


class TestSecurityAssessorDefaults:
    def test_default_autonomy_level(self):
        assessor = SecurityAssessor()
        assert assessor.autonomy_level == "autonomous"

    def test_default_allow_credential_access(self):
        assessor = SecurityAssessor()
        assert assessor.allow_credential_access is False

    def test_default_allow_destructive_operations(self):
        assessor = SecurityAssessor()
        assert assessor.allow_destructive_operations is False

    def test_blocked_count_starts_at_zero(self):
        assessor = SecurityAssessor()
        assert assessor._blocked_count == 0

    def test_high_risk_count_starts_at_zero(self):
        assessor = SecurityAssessor()
        assert assessor._high_risk_count == 0


class TestSecurityAssessorInit:
    def test_custom_autonomy_level(self):
        assessor = SecurityAssessor(autonomy_level="human-in-the-loop")
        assert assessor.autonomy_level == "human-in-the-loop"

    def test_allow_credential_access_true(self):
        assessor = SecurityAssessor(allow_credential_access=True)
        assert assessor.allow_credential_access is True

    def test_allow_destructive_operations_true(self):
        assessor = SecurityAssessor(allow_destructive_operations=True)
        assert assessor.allow_destructive_operations is True


class TestAssessAction:
    def test_returns_security_assessment_instance(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("shell_exec", {"cmd": "ls"})
        assert isinstance(result, SecurityAssessment)

    def test_action_not_blocked(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("file_read", {"path": "/tmp/data.txt"})
        assert result.blocked is False

    def test_risk_level_is_low(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("browser_navigate", {"url": "https://example.com"})
        assert result.risk_level is ActionSecurityRisk.LOW

    def test_requires_confirmation_is_false(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("delete_file", {"path": "/tmp/x"})
        assert result.requires_confirmation is False

    def test_reason_is_sandbox_message(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("shell_exec", {})
        assert "sandbox" in result.reason.lower()

    def test_empty_arguments_accepted(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("noop", {})
        assert result.blocked is False

    def test_arbitrary_function_name_accepted(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action("rm_rf_root", {"path": "/"})
        assert result.blocked is False

    def test_multiple_calls_all_return_low_risk(self):
        assessor = SecurityAssessor()
        for fn in ["read_file", "write_file", "exec_cmd", "fetch_url"]:
            result = assessor.assess_action(fn, {"arg": "value"})
            assert result.risk_level is ActionSecurityRisk.LOW

    def test_blocks_when_required_tier_exceeds_active_tier(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action(
            "shell_exec",
            {},
            active_tier=PermissionTier.READ_ONLY,
            required_tier=PermissionTier.DANGER,
        )
        assert result.blocked is True
        assert result.risk_level is ActionSecurityRisk.HIGH
        assert "danger-full-access" in result.reason
        assert "read-only" in result.reason

    def test_allows_when_active_tier_meets_required_tier(self):
        assessor = SecurityAssessor()
        result = assessor.assess_action(
            "file_write",
            {},
            active_tier=PermissionTier.WORKSPACE_WRITE,
            required_tier=PermissionTier.WORKSPACE_WRITE,
        )
        assert result.blocked is False
        assert result.risk_level is ActionSecurityRisk.LOW


class TestGetRiskSummary:
    def test_returns_dict(self):
        assessor = SecurityAssessor()
        summary = assessor.get_risk_summary()
        assert isinstance(summary, dict)

    def test_contains_autonomy_level(self):
        assessor = SecurityAssessor(autonomy_level="semi-autonomous")
        summary = assessor.get_risk_summary()
        assert summary["autonomy_level"] == "semi-autonomous"

    def test_blocked_actions_is_zero_initially(self):
        assessor = SecurityAssessor()
        summary = assessor.get_risk_summary()
        assert summary["blocked_actions"] == 0

    def test_high_risk_actions_is_zero_initially(self):
        assessor = SecurityAssessor()
        summary = assessor.get_risk_summary()
        assert summary["high_risk_actions"] == 0

    def test_summary_keys_present(self):
        assessor = SecurityAssessor()
        summary = assessor.get_risk_summary()
        assert "autonomy_level" in summary
        assert "blocked_actions" in summary
        assert "high_risk_actions" in summary

    def test_summary_unaffected_by_assess_calls(self):
        assessor = SecurityAssessor()
        for _ in range(5):
            assessor.assess_action("shell_exec", {"cmd": "ls"})
        summary = assessor.get_risk_summary()
        # Sandbox allows all — counters stay at 0
        assert summary["blocked_actions"] == 0
        assert summary["high_risk_actions"] == 0
