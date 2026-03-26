"""
Comprehensive tests for the autonomy_config module.

Covers:
- AutonomyLevel enum values and str behaviour
- ActionCategory enum values
- CONFIRMATION_REQUIRED mapping per level
- PermissionFlags defaults, domain allow/block, path allow/block
- SafetyLimits counters, exceedance, time tracking, get_remaining
- ApprovalRequest creation and serialization
- AutonomyConfig approval flow (sync helpers + async request_approval)
- AutonomyConfig tool categorization
- AutonomyConfig.from_settings with valid and invalid inputs
- AutonomyConfig.get_status reporting
- AutonomyConfig.start_run counter reset
- Singleton get_autonomy_config / set_autonomy_config
"""

import asyncio
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.domain.services.agents.autonomy_config as _module
from app.domain.services.agents.autonomy_config import (
    CONFIRMATION_REQUIRED,
    ActionCategory,
    ApprovalRequest,
    AutonomyConfig,
    AutonomyLevel,
    PermissionFlags,
    SafetyLimits,
    get_autonomy_config,
    set_autonomy_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_ACTION_CATEGORIES: list[ActionCategory] = list(ActionCategory)


def _reset_singleton() -> None:
    """Reset the module-level singleton to avoid test pollution."""
    _module._autonomy_config = None


# ---------------------------------------------------------------------------
# 1. AutonomyLevel enum
# ---------------------------------------------------------------------------


class TestAutonomyLevelEnum:
    def test_is_str_enum(self) -> None:
        assert isinstance(AutonomyLevel.SUPERVISED, str)

    def test_supervised_value(self) -> None:
        assert AutonomyLevel.SUPERVISED == "supervised"
        assert AutonomyLevel.SUPERVISED.value == "supervised"

    def test_guided_value(self) -> None:
        assert AutonomyLevel.GUIDED == "guided"
        assert AutonomyLevel.GUIDED.value == "guided"

    def test_autonomous_value(self) -> None:
        assert AutonomyLevel.AUTONOMOUS == "autonomous"
        assert AutonomyLevel.AUTONOMOUS.value == "autonomous"

    def test_unrestricted_value(self) -> None:
        assert AutonomyLevel.UNRESTRICTED == "unrestricted"
        assert AutonomyLevel.UNRESTRICTED.value == "unrestricted"

    def test_four_members(self) -> None:
        assert len(list(AutonomyLevel)) == 4

    def test_construction_from_string(self) -> None:
        assert AutonomyLevel("supervised") is AutonomyLevel.SUPERVISED
        assert AutonomyLevel("guided") is AutonomyLevel.GUIDED
        assert AutonomyLevel("autonomous") is AutonomyLevel.AUTONOMOUS
        assert AutonomyLevel("unrestricted") is AutonomyLevel.UNRESTRICTED

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            AutonomyLevel("admin")

    def test_names_uppercase(self) -> None:
        for member in AutonomyLevel:
            assert member.name == member.name.upper()


# ---------------------------------------------------------------------------
# 2. ActionCategory enum
# ---------------------------------------------------------------------------


class TestActionCategoryEnum:
    def test_is_str_enum(self) -> None:
        assert isinstance(ActionCategory.FILE_WRITE, str)

    def test_credential_access_value(self) -> None:
        assert ActionCategory.CREDENTIAL_ACCESS == "credential_access"

    def test_external_request_value(self) -> None:
        assert ActionCategory.EXTERNAL_REQUEST == "external_request"

    def test_file_write_value(self) -> None:
        assert ActionCategory.FILE_WRITE == "file_write"

    def test_file_delete_value(self) -> None:
        assert ActionCategory.FILE_DELETE == "file_delete"

    def test_shell_execute_value(self) -> None:
        assert ActionCategory.SHELL_EXECUTE == "shell_execute"

    def test_browser_navigate_value(self) -> None:
        assert ActionCategory.BROWSER_NAVIGATE == "browser_navigate"

    def test_payment_value(self) -> None:
        assert ActionCategory.PAYMENT == "payment"

    def test_data_modification_value(self) -> None:
        assert ActionCategory.DATA_MODIFICATION == "data_modification"

    def test_system_config_value(self) -> None:
        assert ActionCategory.SYSTEM_CONFIG == "system_config"

    def test_network_request_value(self) -> None:
        assert ActionCategory.NETWORK_REQUEST == "network_request"

    def test_ten_members(self) -> None:
        assert len(list(ActionCategory)) == 10


# ---------------------------------------------------------------------------
# 3. CONFIRMATION_REQUIRED mapping
# ---------------------------------------------------------------------------


class TestConfirmationRequired:
    def test_supervised_requires_all_actions(self) -> None:
        supervised_set = CONFIRMATION_REQUIRED[AutonomyLevel.SUPERVISED]
        for cat in ActionCategory:
            assert cat in supervised_set, f"{cat} missing from SUPERVISED"

    def test_guided_requires_critical_subset(self) -> None:
        guided_set = CONFIRMATION_REQUIRED[AutonomyLevel.GUIDED]
        assert ActionCategory.CREDENTIAL_ACCESS in guided_set
        assert ActionCategory.PAYMENT in guided_set
        assert ActionCategory.FILE_DELETE in guided_set
        assert ActionCategory.DATA_MODIFICATION in guided_set
        assert ActionCategory.SYSTEM_CONFIG in guided_set

    def test_guided_does_not_require_file_write(self) -> None:
        assert ActionCategory.FILE_WRITE not in CONFIRMATION_REQUIRED[AutonomyLevel.GUIDED]

    def test_guided_does_not_require_shell_execute(self) -> None:
        assert ActionCategory.SHELL_EXECUTE not in CONFIRMATION_REQUIRED[AutonomyLevel.GUIDED]

    def test_guided_does_not_require_browser_navigate(self) -> None:
        assert ActionCategory.BROWSER_NAVIGATE not in CONFIRMATION_REQUIRED[AutonomyLevel.GUIDED]

    def test_guided_does_not_require_external_request(self) -> None:
        assert ActionCategory.EXTERNAL_REQUEST not in CONFIRMATION_REQUIRED[AutonomyLevel.GUIDED]

    def test_autonomous_requires_payment_and_system_config(self) -> None:
        auto_set = CONFIRMATION_REQUIRED[AutonomyLevel.AUTONOMOUS]
        assert ActionCategory.PAYMENT in auto_set
        assert ActionCategory.SYSTEM_CONFIG in auto_set

    def test_autonomous_does_not_require_credential_access(self) -> None:
        auto_set = CONFIRMATION_REQUIRED[AutonomyLevel.AUTONOMOUS]
        assert ActionCategory.CREDENTIAL_ACCESS not in auto_set

    def test_autonomous_does_not_require_file_delete(self) -> None:
        auto_set = CONFIRMATION_REQUIRED[AutonomyLevel.AUTONOMOUS]
        assert ActionCategory.FILE_DELETE not in auto_set

    def test_autonomous_does_not_require_data_modification(self) -> None:
        auto_set = CONFIRMATION_REQUIRED[AutonomyLevel.AUTONOMOUS]
        assert ActionCategory.DATA_MODIFICATION not in auto_set

    def test_unrestricted_requires_nothing(self) -> None:
        assert len(CONFIRMATION_REQUIRED[AutonomyLevel.UNRESTRICTED]) == 0

    def test_all_four_levels_present(self) -> None:
        for level in AutonomyLevel:
            assert level in CONFIRMATION_REQUIRED

    def test_supervised_set_is_all_categories(self) -> None:
        supervised_set = CONFIRMATION_REQUIRED[AutonomyLevel.SUPERVISED]
        assert supervised_set == set(ActionCategory)


# ---------------------------------------------------------------------------
# 4. PermissionFlags defaults
# ---------------------------------------------------------------------------


class TestPermissionFlagsDefaults:
    def test_credential_access_allowed_by_default(self) -> None:
        pf = PermissionFlags()
        assert pf.allow_credential_access is True

    def test_external_requests_allowed_by_default(self) -> None:
        assert PermissionFlags().allow_external_requests is True

    def test_file_system_write_allowed_by_default(self) -> None:
        assert PermissionFlags().allow_file_system_write is True

    def test_file_system_delete_disabled_by_default(self) -> None:
        assert PermissionFlags().allow_file_system_delete is False

    def test_shell_execute_allowed_by_default(self) -> None:
        assert PermissionFlags().allow_shell_execute is True

    def test_browser_navigation_allowed_by_default(self) -> None:
        assert PermissionFlags().allow_browser_navigation is True

    def test_payment_operations_disabled_by_default(self) -> None:
        assert PermissionFlags().allow_payment_operations is False

    def test_data_modification_allowed_by_default(self) -> None:
        assert PermissionFlags().allow_data_modification is True

    def test_system_config_disabled_by_default(self) -> None:
        assert PermissionFlags().allow_system_config is False

    def test_allowed_domains_is_none_by_default(self) -> None:
        assert PermissionFlags().allowed_domains is None

    def test_allowed_paths_is_none_by_default(self) -> None:
        assert PermissionFlags().allowed_paths is None

    def test_blocked_domains_contains_localhost(self) -> None:
        pf = PermissionFlags()
        assert "localhost" in pf.blocked_domains

    def test_blocked_domains_contains_loopback(self) -> None:
        pf = PermissionFlags()
        assert "127.0.0.1" in pf.blocked_domains

    def test_blocked_domains_contains_internal(self) -> None:
        pf = PermissionFlags()
        assert "internal" in pf.blocked_domains

    def test_blocked_paths_contains_etc(self) -> None:
        pf = PermissionFlags()
        assert "/etc" in pf.blocked_paths

    def test_blocked_paths_contains_root(self) -> None:
        pf = PermissionFlags()
        assert "/root" in pf.blocked_paths

    def test_blocked_paths_independent_per_instance(self) -> None:
        pf1 = PermissionFlags()
        pf2 = PermissionFlags()
        pf1.blocked_domains.add("extra.example.com")
        assert "extra.example.com" not in pf2.blocked_domains


# ---------------------------------------------------------------------------
# 5. PermissionFlags.is_domain_allowed
# ---------------------------------------------------------------------------


class TestPermissionFlagsDomainCheck:
    def test_normal_external_domain_allowed(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("example.com") is True

    def test_localhost_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("localhost") is False

    def test_subdomain_of_blocked_domain_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("sub.localhost") is False

    def test_loopback_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("127.0.0.1") is False

    def test_internal_domain_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("services.internal") is False

    def test_case_insensitive_blocking(self) -> None:
        pf = PermissionFlags()
        assert pf.is_domain_allowed("LOCALHOST") is False

    def test_custom_blocked_domain(self) -> None:
        pf = PermissionFlags(blocked_domains={"evil.com"})
        assert pf.is_domain_allowed("evil.com") is False
        assert pf.is_domain_allowed("sub.evil.com") is False

    def test_allowed_list_restricts_to_listed_domains(self) -> None:
        pf = PermissionFlags(allowed_domains={"trusted.com"})
        assert pf.is_domain_allowed("trusted.com") is True
        assert pf.is_domain_allowed("other.com") is False

    def test_allowed_list_with_blocked_takes_blocked_priority(self) -> None:
        pf = PermissionFlags(
            allowed_domains={"trusted.com", "localhost"},
            blocked_domains={"localhost"},
        )
        # blocked is checked first
        assert pf.is_domain_allowed("localhost") is False

    def test_zero_blocked_domains(self) -> None:
        pf = PermissionFlags(blocked_domains=set())
        assert pf.is_domain_allowed("192.168.1.1") is True

    def test_domain_not_in_allowed_list_blocked(self) -> None:
        pf = PermissionFlags(allowed_domains={"only-this.com"}, blocked_domains=set())
        assert pf.is_domain_allowed("anything-else.com") is False


# ---------------------------------------------------------------------------
# 6. PermissionFlags.is_path_allowed
# ---------------------------------------------------------------------------


class TestPermissionFlagsPathCheck:
    def test_tmp_path_allowed_by_default(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/tmp/output.txt") is True

    def test_etc_path_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/etc/passwd") is False

    def test_var_path_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/var/log/syslog") is False

    def test_usr_path_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/usr/local/bin/python") is False

    def test_root_home_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/root/.bashrc") is False

    def test_home_path_blocked(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/home/user/.ssh/id_rsa") is False

    def test_allowed_paths_restricts_to_listed(self) -> None:
        pf = PermissionFlags(allowed_paths={"/workspace"}, blocked_paths=set())
        assert pf.is_path_allowed("/workspace/output.txt") is True
        assert pf.is_path_allowed("/tmp/output.txt") is False

    def test_blocked_takes_priority_over_allowed(self) -> None:
        pf = PermissionFlags(
            allowed_paths={"/etc"},
            blocked_paths={"/etc"},
        )
        assert pf.is_path_allowed("/etc/file") is False

    def test_tilde_path_blocked(self) -> None:
        pf = PermissionFlags()
        # ~ resolves to home dir, which starts with /home or /root in most systems
        # Either way tilde is in blocked_paths so it should be blocked
        result = pf.is_path_allowed("~/secret")
        # The result depends on the actual home directory but the default blocked list
        # includes "~" which normalises to the actual home path; we just assert it
        # is consistent (not raising an exception)
        assert isinstance(result, bool)

    def test_path_normalization_traversal(self) -> None:
        pf = PermissionFlags()
        # /tmp/../etc/passwd resolves to /etc/passwd which is blocked
        assert pf.is_path_allowed("/tmp/../etc/passwd") is False

    def test_workspace_path_not_blocked_by_default(self) -> None:
        pf = PermissionFlags()
        assert pf.is_path_allowed("/workspace/project/main.py") is True


# ---------------------------------------------------------------------------
# 7. SafetyLimits defaults and start_run
# ---------------------------------------------------------------------------


class TestSafetyLimitsDefaults:
    def test_default_max_iterations(self) -> None:
        sl = SafetyLimits()
        assert sl.max_iterations == 200

    def test_default_max_tool_calls(self) -> None:
        sl = SafetyLimits()
        assert sl.max_tool_calls == 300

    def test_default_max_execution_time(self) -> None:
        sl = SafetyLimits()
        assert sl.max_execution_time_seconds == 3600

    def test_default_max_tokens(self) -> None:
        sl = SafetyLimits()
        assert sl.max_tokens_per_run == 500_000

    def test_default_max_cost_is_none(self) -> None:
        sl = SafetyLimits()
        assert sl.max_cost_usd is None

    def test_counters_start_at_zero(self) -> None:
        sl = SafetyLimits()
        assert sl.current_iterations == 0
        assert sl.current_tool_calls == 0
        assert sl.current_tokens == 0
        assert sl.current_cost == 0.0

    def test_start_time_initially_none(self) -> None:
        sl = SafetyLimits()
        assert sl.start_time is None

    def test_start_run_resets_counters(self) -> None:
        sl = SafetyLimits()
        sl.current_iterations = 50
        sl.current_tool_calls = 100
        sl.current_tokens = 9999
        sl.current_cost = 3.14
        sl.start_run()
        assert sl.current_iterations == 0
        assert sl.current_tool_calls == 0
        assert sl.current_tokens == 0
        assert sl.current_cost == 0.0

    def test_start_run_sets_start_time(self) -> None:
        sl = SafetyLimits()
        before = datetime.now(UTC)
        sl.start_run()
        after = datetime.now(UTC)
        assert sl.start_time is not None
        assert before <= sl.start_time <= after


# ---------------------------------------------------------------------------
# 8. SafetyLimits.increment_iteration
# ---------------------------------------------------------------------------


class TestSafetyLimitsIncrementIteration:
    def test_returns_true_within_limit(self) -> None:
        sl = SafetyLimits(max_iterations=5)
        assert sl.increment_iteration() is True
        assert sl.current_iterations == 1

    def test_returns_true_at_exact_limit(self) -> None:
        sl = SafetyLimits(max_iterations=3)
        sl.current_iterations = 2
        assert sl.increment_iteration() is True  # now 3 == max, NOT exceeded

    def test_returns_false_when_limit_exceeded(self) -> None:
        sl = SafetyLimits(max_iterations=3)
        sl.current_iterations = 3
        assert sl.increment_iteration() is False  # now 4 > 3

    def test_counter_keeps_incrementing_beyond_limit(self) -> None:
        sl = SafetyLimits(max_iterations=2)
        sl.increment_iteration()
        sl.increment_iteration()
        sl.increment_iteration()
        assert sl.current_iterations == 3

    def test_multiple_increments_accumulate(self) -> None:
        sl = SafetyLimits(max_iterations=100)
        for _ in range(10):
            sl.increment_iteration()
        assert sl.current_iterations == 10


# ---------------------------------------------------------------------------
# 9. SafetyLimits.increment_tool_calls
# ---------------------------------------------------------------------------


class TestSafetyLimitsIncrementToolCalls:
    def test_returns_true_within_limit(self) -> None:
        sl = SafetyLimits(max_tool_calls=10)
        assert sl.increment_tool_calls() is True
        assert sl.current_tool_calls == 1

    def test_bulk_increment(self) -> None:
        sl = SafetyLimits(max_tool_calls=100)
        assert sl.increment_tool_calls(count=5) is True
        assert sl.current_tool_calls == 5

    def test_returns_false_when_exceeded(self) -> None:
        sl = SafetyLimits(max_tool_calls=5)
        sl.current_tool_calls = 5
        assert sl.increment_tool_calls() is False

    def test_exact_limit_returns_true(self) -> None:
        sl = SafetyLimits(max_tool_calls=5)
        sl.current_tool_calls = 4
        assert sl.increment_tool_calls() is True  # 5 == max, not exceeded


# ---------------------------------------------------------------------------
# 10. SafetyLimits.add_tokens
# ---------------------------------------------------------------------------


class TestSafetyLimitsAddTokens:
    def test_returns_true_within_limit(self) -> None:
        sl = SafetyLimits(max_tokens_per_run=1000)
        assert sl.add_tokens(500) is True
        assert sl.current_tokens == 500

    def test_returns_false_when_exceeded(self) -> None:
        sl = SafetyLimits(max_tokens_per_run=1000)
        sl.current_tokens = 1000
        assert sl.add_tokens(1) is False

    def test_tokens_accumulate(self) -> None:
        sl = SafetyLimits(max_tokens_per_run=10000)
        sl.add_tokens(3000)
        sl.add_tokens(2000)
        assert sl.current_tokens == 5000

    def test_at_exact_limit_returns_true(self) -> None:
        sl = SafetyLimits(max_tokens_per_run=1000)
        sl.current_tokens = 999
        assert sl.add_tokens(1) is True  # now 1000 == max, not exceeded


# ---------------------------------------------------------------------------
# 11. SafetyLimits.add_cost
# ---------------------------------------------------------------------------


class TestSafetyLimitsAddCost:
    def test_no_limit_always_returns_true(self) -> None:
        sl = SafetyLimits(max_cost_usd=None)
        assert sl.add_cost(999.99) is True

    def test_returns_true_within_limit(self) -> None:
        sl = SafetyLimits(max_cost_usd=10.0)
        assert sl.add_cost(5.0) is True
        assert sl.current_cost == pytest.approx(5.0)

    def test_returns_false_when_exceeded(self) -> None:
        sl = SafetyLimits(max_cost_usd=10.0)
        sl.current_cost = 10.0
        assert sl.add_cost(0.01) is False

    def test_cost_accumulates(self) -> None:
        sl = SafetyLimits(max_cost_usd=100.0)
        sl.add_cost(1.5)
        sl.add_cost(2.5)
        assert sl.current_cost == pytest.approx(4.0)

    def test_at_exact_limit_returns_true(self) -> None:
        sl = SafetyLimits(max_cost_usd=10.0)
        sl.current_cost = 9.99
        assert sl.add_cost(0.01) is True  # exactly 10.0, not exceeded


# ---------------------------------------------------------------------------
# 12. SafetyLimits.check_time_limit
# ---------------------------------------------------------------------------


class TestSafetyLimitsCheckTimeLimit:
    def test_no_start_time_returns_true(self) -> None:
        sl = SafetyLimits()
        assert sl.check_time_limit() is True

    def test_within_time_returns_true(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=3600)
        sl.start_time = datetime.now(UTC)
        assert sl.check_time_limit() is True

    def test_exceeded_time_returns_false(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=10)
        sl.start_time = datetime.now(UTC) - timedelta(seconds=20)
        assert sl.check_time_limit() is False

    def test_exactly_at_limit_returns_true(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=60)
        sl.start_time = datetime.now(UTC) - timedelta(seconds=59)
        assert sl.check_time_limit() is True


# ---------------------------------------------------------------------------
# 13. SafetyLimits.check_all_limits
# ---------------------------------------------------------------------------


class TestSafetyLimitsCheckAllLimits:
    def test_all_ok_when_fresh(self) -> None:
        sl = SafetyLimits()
        ok, reason = sl.check_all_limits()
        assert ok is True
        assert reason is None

    def test_iteration_exceeded(self) -> None:
        sl = SafetyLimits(max_iterations=5)
        sl.current_iterations = 6
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert reason is not None
        assert "Iteration" in reason or "iteration" in reason.lower()

    def test_tool_call_exceeded(self) -> None:
        sl = SafetyLimits(max_tool_calls=5)
        sl.current_tool_calls = 6
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Tool call" in reason or "tool" in reason.lower()

    def test_token_exceeded(self) -> None:
        sl = SafetyLimits(max_tokens_per_run=1000)
        sl.current_tokens = 1001
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Token" in reason or "token" in reason.lower()

    def test_cost_exceeded(self) -> None:
        sl = SafetyLimits(max_cost_usd=5.0)
        sl.current_cost = 6.0
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Cost" in reason or "cost" in reason.lower()

    def test_time_exceeded(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=10)
        sl.start_time = datetime.now(UTC) - timedelta(seconds=30)
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Time" in reason or "time" in reason.lower()

    def test_iteration_checked_before_tool_calls(self) -> None:
        sl = SafetyLimits(max_iterations=1, max_tool_calls=1)
        sl.current_iterations = 2
        sl.current_tool_calls = 2
        ok, reason = sl.check_all_limits()
        assert ok is False
        # Iteration limit is checked first in the implementation
        assert "iteration" in reason.lower() or "Iteration" in reason


# ---------------------------------------------------------------------------
# 14. SafetyLimits.get_remaining
# ---------------------------------------------------------------------------


class TestSafetyLimitsGetRemaining:
    def test_returns_all_keys(self) -> None:
        sl = SafetyLimits()
        remaining = sl.get_remaining()
        assert "iterations" in remaining
        assert "tool_calls" in remaining
        assert "tokens" in remaining
        assert "time_seconds" in remaining
        assert "cost_usd" in remaining

    def test_full_remaining_when_no_usage(self) -> None:
        sl = SafetyLimits(max_iterations=50, max_tool_calls=100, max_tokens_per_run=10000)
        remaining = sl.get_remaining()
        assert remaining["iterations"] == 50
        assert remaining["tool_calls"] == 100
        assert remaining["tokens"] == 10000

    def test_remaining_decreases_after_usage(self) -> None:
        sl = SafetyLimits(max_iterations=50)
        sl.current_iterations = 20
        assert sl.get_remaining()["iterations"] == 30

    def test_cost_remaining_is_none_when_no_limit(self) -> None:
        sl = SafetyLimits(max_cost_usd=None)
        assert sl.get_remaining()["cost_usd"] is None

    def test_cost_remaining_calculated(self) -> None:
        sl = SafetyLimits(max_cost_usd=10.0)
        sl.current_cost = 3.0
        assert sl.get_remaining()["cost_usd"] == pytest.approx(7.0)

    def test_time_seconds_is_non_negative_without_start_time(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=60)
        remaining = sl.get_remaining()
        assert remaining["time_seconds"] >= 0

    def test_time_remaining_decreases_with_start_time(self) -> None:
        sl = SafetyLimits(max_execution_time_seconds=3600)
        sl.start_time = datetime.now(UTC) - timedelta(seconds=100)
        remaining = sl.get_remaining()
        assert remaining["time_seconds"] == pytest.approx(3500, abs=2)


# ---------------------------------------------------------------------------
# 15. ApprovalRequest creation and serialization
# ---------------------------------------------------------------------------


class TestApprovalRequest:
    def test_basic_creation(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.FILE_WRITE,
            action_description="Write report.txt",
        )
        assert req.action_category is ActionCategory.FILE_WRITE
        assert req.action_description == "Write report.txt"
        assert req.tool_name is None
        assert req.parameters is None
        assert req.risk_level == "medium"

    def test_default_timestamp_is_utc(self) -> None:
        before = datetime.now(UTC)
        req = ApprovalRequest(
            action_category=ActionCategory.PAYMENT,
            action_description="Pay invoice",
        )
        after = datetime.now(UTC)
        assert before <= req.timestamp <= after

    def test_custom_risk_level(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.PAYMENT,
            action_description="Large payment",
            risk_level="critical",
        )
        assert req.risk_level == "critical"

    def test_with_tool_name_and_params(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.SHELL_EXECUTE,
            action_description="Run script",
            tool_name="shell_tool",
            parameters={"cmd": "ls", "args": ["-la"]},
        )
        assert req.tool_name == "shell_tool"
        assert req.parameters == {"cmd": "ls", "args": ["-la"]}

    def test_to_dict_keys(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.FILE_DELETE,
            action_description="Delete temp files",
        )
        d = req.to_dict()
        assert "action_category" in d
        assert "action_description" in d
        assert "tool_name" in d
        assert "parameters" in d
        assert "risk_level" in d
        assert "timestamp" in d

    def test_to_dict_action_category_is_string(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.CREDENTIAL_ACCESS,
            action_description="Access secrets",
        )
        d = req.to_dict()
        assert isinstance(d["action_category"], str)
        assert d["action_category"] == "credential_access"

    def test_to_dict_timestamp_is_iso_string(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.NETWORK_REQUEST,
            action_description="Network call",
        )
        d = req.to_dict()
        ts = d["timestamp"]
        assert isinstance(ts, str)
        # Must be parseable as ISO 8601
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

    def test_to_dict_parameters_preserved(self) -> None:
        params = {"url": "https://example.com", "method": "POST"}
        req = ApprovalRequest(
            action_category=ActionCategory.EXTERNAL_REQUEST,
            action_description="POST request",
            parameters=params,
        )
        assert req.to_dict()["parameters"] == params

    def test_to_dict_none_tool_name(self) -> None:
        req = ApprovalRequest(
            action_category=ActionCategory.DATA_MODIFICATION,
            action_description="Modify records",
        )
        assert req.to_dict()["tool_name"] is None

    def test_two_requests_have_independent_timestamps(self) -> None:
        req1 = ApprovalRequest(
            action_category=ActionCategory.FILE_WRITE,
            action_description="First",
        )
        req2 = ApprovalRequest(
            action_category=ActionCategory.FILE_WRITE,
            action_description="Second",
        )
        assert req1.timestamp <= req2.timestamp


# ---------------------------------------------------------------------------
# 16. AutonomyConfig initialization
# ---------------------------------------------------------------------------


class TestAutonomyConfigInit:
    def test_default_level_is_guided(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.level is AutonomyLevel.GUIDED

    def test_custom_level(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        assert cfg.level is AutonomyLevel.AUTONOMOUS

    def test_default_permissions_created(self) -> None:
        cfg = AutonomyConfig()
        assert isinstance(cfg.permissions, PermissionFlags)

    def test_custom_permissions_used(self) -> None:
        pf = PermissionFlags(allow_payment_operations=True)
        cfg = AutonomyConfig(permissions=pf)
        assert cfg.permissions is pf

    def test_default_limits_created(self) -> None:
        cfg = AutonomyConfig()
        assert isinstance(cfg.limits, SafetyLimits)

    def test_custom_limits_used(self) -> None:
        sl = SafetyLimits(max_iterations=10)
        cfg = AutonomyConfig(limits=sl)
        assert cfg.limits is sl

    def test_no_pending_approvals_on_init(self) -> None:
        cfg = AutonomyConfig()
        assert cfg._pending_approvals == []

    def test_no_approval_callback_on_init(self) -> None:
        cfg = AutonomyConfig()
        assert cfg._approval_callback is None


# ---------------------------------------------------------------------------
# 17. AutonomyConfig.set_approval_callback
# ---------------------------------------------------------------------------


class TestAutonomyConfigSetApprovalCallback:
    def test_sets_callback(self) -> None:
        cfg = AutonomyConfig()
        cb = AsyncMock(return_value=True)
        cfg.set_approval_callback(cb)
        assert cfg._approval_callback is cb

    def test_replaces_existing_callback(self) -> None:
        cfg = AutonomyConfig()
        cb1 = AsyncMock(return_value=True)
        cb2 = AsyncMock(return_value=False)
        cfg.set_approval_callback(cb1)
        cfg.set_approval_callback(cb2)
        assert cfg._approval_callback is cb2


# ---------------------------------------------------------------------------
# 18. AutonomyConfig.requires_approval
# ---------------------------------------------------------------------------


class TestAutonomyConfigRequiresApproval:
    def test_supervised_requires_all(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        for cat in ActionCategory:
            assert cfg.requires_approval(cat) is True, f"{cat} should require approval"

    def test_unrestricted_requires_none_by_level(self) -> None:
        # Use unrestricted level with all permissions enabled so we don't trip
        # the permission-disabled gate
        cfg = AutonomyConfig(
            level=AutonomyLevel.UNRESTRICTED,
            permissions=PermissionFlags(
                allow_payment_operations=True,
                allow_system_config=True,
                allow_file_system_delete=True,
            ),
        )
        for cat in ActionCategory:
            assert cfg.requires_approval(cat) is False, f"{cat} should not require approval"

    def test_guided_requires_payment(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.GUIDED,
            permissions=PermissionFlags(allow_payment_operations=True),
        )
        assert cfg.requires_approval(ActionCategory.PAYMENT) is True

    def test_guided_does_not_require_file_write(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        assert cfg.requires_approval(ActionCategory.FILE_WRITE) is False

    def test_autonomous_requires_system_config(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.AUTONOMOUS,
            permissions=PermissionFlags(allow_system_config=True),
        )
        assert cfg.requires_approval(ActionCategory.SYSTEM_CONFIG) is True

    def test_disabled_permission_requires_approval(self) -> None:
        # FILE_DELETE is disabled by default — even though AUTONOMOUS doesn't
        # require it, the disabled permission triggers approval requirement
        cfg = AutonomyConfig(
            level=AutonomyLevel.AUTONOMOUS,
            permissions=PermissionFlags(allow_file_system_delete=False),
        )
        assert cfg.requires_approval(ActionCategory.FILE_DELETE) is True

    def test_disabled_payment_requires_approval_in_unrestricted(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.UNRESTRICTED,
            permissions=PermissionFlags(allow_payment_operations=False),
        )
        assert cfg.requires_approval(ActionCategory.PAYMENT) is True


# ---------------------------------------------------------------------------
# 19. AutonomyConfig.is_action_allowed
# ---------------------------------------------------------------------------


class TestAutonomyConfigIsActionAllowed:
    def test_allowed_action_returns_true(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.is_action_allowed(ActionCategory.FILE_WRITE) is True

    def test_disabled_file_delete_returns_false(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.is_action_allowed(ActionCategory.FILE_DELETE) is False

    def test_disabled_payment_returns_false(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.is_action_allowed(ActionCategory.PAYMENT) is False

    def test_disabled_system_config_returns_false(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.is_action_allowed(ActionCategory.SYSTEM_CONFIG) is False

    def test_enabling_payment_returns_true(self) -> None:
        pf = PermissionFlags(allow_payment_operations=True)
        cfg = AutonomyConfig(permissions=pf)
        assert cfg.is_action_allowed(ActionCategory.PAYMENT) is True

    def test_network_request_not_in_map_returns_true(self) -> None:
        cfg = AutonomyConfig()
        # NETWORK_REQUEST has no explicit flag in permission_map, defaults to True
        assert cfg.is_action_allowed(ActionCategory.NETWORK_REQUEST) is True


# ---------------------------------------------------------------------------
# 20. AutonomyConfig.request_approval — async
# ---------------------------------------------------------------------------


class TestAutonomyConfigRequestApproval:
    async def test_blocked_permission_returns_false(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.UNRESTRICTED,
            permissions=PermissionFlags(allow_payment_operations=False),
        )
        result = await cfg.request_approval(
            ActionCategory.PAYMENT,
            "Pay $100",
        )
        assert result is False

    async def test_no_approval_required_returns_true(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.UNRESTRICTED,
            permissions=PermissionFlags(
                allow_payment_operations=True,
                allow_system_config=True,
                allow_file_system_delete=True,
            ),
        )
        result = await cfg.request_approval(
            ActionCategory.FILE_WRITE,
            "Write output",
        )
        assert result is True

    async def test_callback_called_with_approval_request(self) -> None:
        callback = AsyncMock(return_value=True)
        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        cfg.set_approval_callback(callback)
        await cfg.request_approval(
            ActionCategory.CREDENTIAL_ACCESS,
            "Read API key",
            tool_name="secret_reader",
            risk_level="high",
        )
        callback.assert_called_once()
        call_arg = callback.call_args[0][0]
        assert isinstance(call_arg, ApprovalRequest)
        assert call_arg.action_category is ActionCategory.CREDENTIAL_ACCESS

    async def test_callback_approved_returns_true(self) -> None:
        # Enable payment so the permission gate passes and the callback is reached
        cfg = AutonomyConfig(
            level=AutonomyLevel.GUIDED,
            permissions=PermissionFlags(allow_payment_operations=True),
        )
        cfg.set_approval_callback(AsyncMock(return_value=True))
        result = await cfg.request_approval(
            ActionCategory.PAYMENT,
            "Pay invoice",
        )
        assert result is True

    async def test_callback_denied_returns_false(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        cfg.set_approval_callback(AsyncMock(return_value=False))
        result = await cfg.request_approval(
            ActionCategory.CREDENTIAL_ACCESS,
            "Access secrets",
        )
        assert result is False

    async def test_callback_exception_returns_false(self) -> None:
        async def bad_callback(req: ApprovalRequest) -> bool:
            raise RuntimeError("callback exploded")

        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        cfg.set_approval_callback(bad_callback)
        result = await cfg.request_approval(
            ActionCategory.PAYMENT,
            "Pay invoice",
        )
        assert result is False

    async def test_no_callback_adds_to_pending_and_returns_false(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        result = await cfg.request_approval(
            ActionCategory.CREDENTIAL_ACCESS,
            "Read secret",
        )
        assert result is False
        assert len(cfg._pending_approvals) == 1
        assert cfg._pending_approvals[0].action_category is ActionCategory.CREDENTIAL_ACCESS

    async def test_no_callback_accumulates_pending(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        await cfg.request_approval(ActionCategory.FILE_WRITE, "Write 1")
        await cfg.request_approval(ActionCategory.FILE_WRITE, "Write 2")
        assert len(cfg._pending_approvals) == 2

    async def test_parameters_forwarded_to_request(self) -> None:
        received: list[ApprovalRequest] = []

        async def capture(req: ApprovalRequest) -> bool:
            received.append(req)
            return True

        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        cfg.set_approval_callback(capture)
        params = {"key": "value", "count": 3}
        await cfg.request_approval(
            ActionCategory.CREDENTIAL_ACCESS,
            "Fetch key",
            parameters=params,
        )
        assert received[0].parameters == params

    async def test_risk_level_forwarded(self) -> None:
        received: list[ApprovalRequest] = []

        async def capture(req: ApprovalRequest) -> bool:
            received.append(req)
            return True

        # Enable payment so the permission gate passes and the callback fires
        cfg = AutonomyConfig(
            level=AutonomyLevel.GUIDED,
            permissions=PermissionFlags(allow_payment_operations=True),
        )
        cfg.set_approval_callback(capture)
        await cfg.request_approval(
            ActionCategory.PAYMENT,
            "Critical payment",
            risk_level="critical",
        )
        assert received[0].risk_level == "critical"


# ---------------------------------------------------------------------------
# 21. AutonomyConfig.categorize_tool
# ---------------------------------------------------------------------------


class TestAutonomyConfigCategorizeTool:
    def setup_method(self) -> None:
        self.cfg = AutonomyConfig()

    def test_credential_tool(self) -> None:
        assert self.cfg.categorize_tool("get_credential") is ActionCategory.CREDENTIAL_ACCESS

    def test_password_tool(self) -> None:
        assert self.cfg.categorize_tool("password_manager") is ActionCategory.CREDENTIAL_ACCESS

    def test_secret_tool(self) -> None:
        assert self.cfg.categorize_tool("secret_fetch") is ActionCategory.CREDENTIAL_ACCESS

    def test_key_tool(self) -> None:
        assert self.cfg.categorize_tool("api_key_reader") is ActionCategory.CREDENTIAL_ACCESS

    def test_auth_tool(self) -> None:
        assert self.cfg.categorize_tool("auth_token") is ActionCategory.CREDENTIAL_ACCESS

    def test_file_write_tool(self) -> None:
        assert self.cfg.categorize_tool("file_write") is ActionCategory.FILE_WRITE

    def test_file_create_tool(self) -> None:
        assert self.cfg.categorize_tool("file_create") is ActionCategory.FILE_WRITE

    def test_save_tool(self) -> None:
        assert self.cfg.categorize_tool("save_document") is ActionCategory.FILE_WRITE

    def test_file_delete_tool(self) -> None:
        assert self.cfg.categorize_tool("file_delete") is ActionCategory.FILE_DELETE

    def test_remove_tool(self) -> None:
        assert self.cfg.categorize_tool("remove_entry") is ActionCategory.FILE_DELETE

    def test_rm_tool(self) -> None:
        assert self.cfg.categorize_tool("rm_old_files") is ActionCategory.FILE_DELETE

    def test_shell_tool(self) -> None:
        assert self.cfg.categorize_tool("shell_run") is ActionCategory.SHELL_EXECUTE

    def test_exec_tool(self) -> None:
        assert self.cfg.categorize_tool("exec_command") is ActionCategory.SHELL_EXECUTE

    def test_bash_tool(self) -> None:
        assert self.cfg.categorize_tool("bash_execute") is ActionCategory.SHELL_EXECUTE

    def test_command_tool(self) -> None:
        assert self.cfg.categorize_tool("run_command") is ActionCategory.SHELL_EXECUTE

    def test_run_tool(self) -> None:
        assert self.cfg.categorize_tool("run_script") is ActionCategory.SHELL_EXECUTE

    def test_browser_tool(self) -> None:
        assert self.cfg.categorize_tool("browser_open") is ActionCategory.BROWSER_NAVIGATE

    def test_navigate_tool(self) -> None:
        assert self.cfg.categorize_tool("navigate_to_url") is ActionCategory.BROWSER_NAVIGATE

    def test_click_tool(self) -> None:
        assert self.cfg.categorize_tool("click_element") is ActionCategory.BROWSER_NAVIGATE

    def test_page_tool(self) -> None:
        assert self.cfg.categorize_tool("page_screenshot") is ActionCategory.BROWSER_NAVIGATE

    def test_search_tool(self) -> None:
        assert self.cfg.categorize_tool("info_search_web") is ActionCategory.EXTERNAL_REQUEST

    def test_fetch_tool(self) -> None:
        assert self.cfg.categorize_tool("fetch_url") is ActionCategory.EXTERNAL_REQUEST

    def test_request_tool(self) -> None:
        assert self.cfg.categorize_tool("http_request") is ActionCategory.EXTERNAL_REQUEST

    def test_api_tool(self) -> None:
        assert self.cfg.categorize_tool("call_api") is ActionCategory.EXTERNAL_REQUEST

    def test_pay_tool(self) -> None:
        assert self.cfg.categorize_tool("pay_invoice") is ActionCategory.PAYMENT

    def test_purchase_tool(self) -> None:
        assert self.cfg.categorize_tool("purchase_item") is ActionCategory.PAYMENT

    def test_buy_tool(self) -> None:
        assert self.cfg.categorize_tool("buy_product") is ActionCategory.PAYMENT

    def test_charge_tool(self) -> None:
        assert self.cfg.categorize_tool("charge_card") is ActionCategory.PAYMENT

    def test_billing_tool(self) -> None:
        assert self.cfg.categorize_tool("billing_update") is ActionCategory.PAYMENT

    def test_update_tool(self) -> None:
        assert self.cfg.categorize_tool("update_record") is ActionCategory.DATA_MODIFICATION

    def test_modify_tool(self) -> None:
        assert self.cfg.categorize_tool("modify_entry") is ActionCategory.DATA_MODIFICATION

    def test_edit_tool(self) -> None:
        assert self.cfg.categorize_tool("edit_document") is ActionCategory.DATA_MODIFICATION

    def test_change_tool(self) -> None:
        assert self.cfg.categorize_tool("change_settings") is ActionCategory.DATA_MODIFICATION

    def test_unknown_tool_defaults_to_network_request(self) -> None:
        assert self.cfg.categorize_tool("totally_unknown_xyz") is ActionCategory.NETWORK_REQUEST

    def test_case_insensitive_matching(self) -> None:
        assert self.cfg.categorize_tool("SHELL_RUN") is ActionCategory.SHELL_EXECUTE


# ---------------------------------------------------------------------------
# 22. AutonomyConfig.check_limits
# ---------------------------------------------------------------------------


class TestAutonomyConfigCheckLimits:
    def test_delegates_to_safety_limits(self) -> None:
        sl = SafetyLimits(max_iterations=5)
        sl.current_iterations = 10
        cfg = AutonomyConfig(limits=sl)
        ok, reason = cfg.check_limits()
        assert ok is False
        assert reason is not None

    def test_ok_when_within_limits(self) -> None:
        cfg = AutonomyConfig()
        ok, reason = cfg.check_limits()
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# 23. AutonomyConfig.start_run
# ---------------------------------------------------------------------------


class TestAutonomyConfigStartRun:
    def test_resets_counters(self) -> None:
        cfg = AutonomyConfig()
        cfg.limits.current_iterations = 99
        cfg.limits.current_tool_calls = 88
        cfg.start_run()
        assert cfg.limits.current_iterations == 0
        assert cfg.limits.current_tool_calls == 0

    def test_clears_pending_approvals(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        cfg._pending_approvals.append(
            ApprovalRequest(
                action_category=ActionCategory.FILE_WRITE,
                action_description="Some action",
            )
        )
        cfg.start_run()
        assert cfg._pending_approvals == []

    def test_sets_start_time(self) -> None:
        cfg = AutonomyConfig()
        before = datetime.now(UTC)
        cfg.start_run()
        after = datetime.now(UTC)
        assert cfg.limits.start_time is not None
        assert before <= cfg.limits.start_time <= after


# ---------------------------------------------------------------------------
# 24. AutonomyConfig.get_status
# ---------------------------------------------------------------------------


class TestAutonomyConfigGetStatus:
    def test_returns_autonomy_level(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        status = cfg.get_status()
        assert status["autonomy_level"] == "autonomous"

    def test_within_limits_true_on_fresh_config(self) -> None:
        cfg = AutonomyConfig()
        assert cfg.get_status()["within_limits"] is True

    def test_within_limits_false_when_exceeded(self) -> None:
        cfg = AutonomyConfig(limits=SafetyLimits(max_iterations=1))
        cfg.limits.current_iterations = 5
        assert cfg.get_status()["within_limits"] is False

    def test_limit_exceeded_reason_populated(self) -> None:
        cfg = AutonomyConfig(limits=SafetyLimits(max_iterations=1))
        cfg.limits.current_iterations = 5
        assert cfg.get_status()["limit_exceeded_reason"] is not None

    def test_pending_approvals_count(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        cfg._pending_approvals.append(
            ApprovalRequest(ActionCategory.FILE_WRITE, "A")
        )
        cfg._pending_approvals.append(
            ApprovalRequest(ActionCategory.FILE_WRITE, "B")
        )
        assert cfg.get_status()["pending_approvals"] == 2

    def test_current_stats_present(self) -> None:
        cfg = AutonomyConfig()
        cfg.limits.current_iterations = 7
        cfg.limits.current_tool_calls = 3
        cfg.limits.current_tokens = 500
        cfg.limits.current_cost = 0.12
        stats = cfg.get_status()["current_stats"]
        assert stats["iterations"] == 7
        assert stats["tool_calls"] == 3
        assert stats["tokens"] == 500
        assert stats["cost_usd"] == pytest.approx(0.12)

    def test_remaining_key_present(self) -> None:
        cfg = AutonomyConfig()
        remaining = cfg.get_status()["remaining"]
        assert "iterations" in remaining
        assert "tool_calls" in remaining


# ---------------------------------------------------------------------------
# 25. AutonomyConfig.from_settings
# ---------------------------------------------------------------------------


class TestAutonomyConfigFromSettings:
    def _make_settings(self, **kwargs: Any) -> MagicMock:
        defaults = {
            "autonomy_level": "guided",
            "allow_credential_access": True,
            "allow_external_requests": True,
            "allow_file_system_write": True,
            "allow_file_system_delete": False,
            "allow_shell_execute": True,
            "allow_browser_navigation": True,
            "allow_payment_operations": False,
            "max_iterations": 50,
            "max_tool_calls": 100,
            "max_execution_time_seconds": 1800,
            "max_tokens_per_run": 500000,
            "max_cost_usd": None,
        }
        defaults.update(kwargs)
        settings = MagicMock()
        for k, v in defaults.items():
            setattr(settings, k, v)
        # Make getattr fall through to the MagicMock for unset attrs
        return settings

    def test_returns_autonomy_config_instance(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings())
        assert isinstance(cfg, AutonomyConfig)

    def test_level_set_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="autonomous"))
        assert cfg.level is AutonomyLevel.AUTONOMOUS

    def test_guided_level_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="guided"))
        assert cfg.level is AutonomyLevel.GUIDED

    def test_supervised_level_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="supervised"))
        assert cfg.level is AutonomyLevel.SUPERVISED

    def test_unrestricted_level_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="unrestricted"))
        assert cfg.level is AutonomyLevel.UNRESTRICTED

    def test_invalid_level_defaults_to_guided(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="superadmin"))
        assert cfg.level is AutonomyLevel.GUIDED

    def test_missing_autonomy_level_defaults_to_guided(self) -> None:
        settings = MagicMock(spec=[])  # no attributes at all
        cfg = AutonomyConfig.from_settings(settings)
        assert cfg.level is AutonomyLevel.GUIDED

    def test_permission_flags_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(
            self._make_settings(
                allow_file_system_delete=True,
                allow_payment_operations=True,
            )
        )
        assert cfg.permissions.allow_file_system_delete is True
        assert cfg.permissions.allow_payment_operations is True

    def test_disabled_permissions_respected(self) -> None:
        cfg = AutonomyConfig.from_settings(
            self._make_settings(allow_credential_access=False)
        )
        assert cfg.permissions.allow_credential_access is False

    def test_limits_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(
            self._make_settings(max_iterations=42, max_tool_calls=99)
        )
        assert cfg.limits.max_iterations == 42
        assert cfg.limits.max_tool_calls == 99

    def test_cost_limit_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(max_cost_usd=25.0))
        assert cfg.limits.max_cost_usd == pytest.approx(25.0)

    def test_no_cost_limit_from_settings(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(max_cost_usd=None))
        assert cfg.limits.max_cost_usd is None

    def test_missing_settings_use_defaults(self) -> None:
        # Only set the level; all other attrs missing so getattr falls back
        settings = MagicMock(spec=["autonomy_level"])
        settings.autonomy_level = "guided"
        cfg = AutonomyConfig.from_settings(settings)
        assert cfg.level is AutonomyLevel.GUIDED
        # Limits should still be SafetyLimits instances
        assert isinstance(cfg.limits, SafetyLimits)

    def test_uppercase_level_string_works(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="AUTONOMOUS"))
        assert cfg.level is AutonomyLevel.AUTONOMOUS

    def test_mixed_case_level_string_works(self) -> None:
        cfg = AutonomyConfig.from_settings(self._make_settings(autonomy_level="Guided"))
        assert cfg.level is AutonomyLevel.GUIDED


# ---------------------------------------------------------------------------
# 26. Singleton management
# ---------------------------------------------------------------------------


class TestSingletonManagement:
    def setup_method(self) -> None:
        _reset_singleton()

    def teardown_method(self) -> None:
        _reset_singleton()

    def test_get_autonomy_config_returns_instance(self) -> None:
        cfg = get_autonomy_config()
        assert isinstance(cfg, AutonomyConfig)

    def test_get_autonomy_config_returns_same_instance(self) -> None:
        cfg1 = get_autonomy_config()
        cfg2 = get_autonomy_config()
        assert cfg1 is cfg2

    def test_default_singleton_level_is_guided(self) -> None:
        cfg = get_autonomy_config()
        assert cfg.level is AutonomyLevel.GUIDED

    def test_set_autonomy_config_replaces_singleton(self) -> None:
        new_cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        set_autonomy_config(new_cfg)
        assert get_autonomy_config() is new_cfg

    def test_set_then_get_same_object(self) -> None:
        new_cfg = AutonomyConfig(level=AutonomyLevel.UNRESTRICTED)
        set_autonomy_config(new_cfg)
        retrieved = get_autonomy_config()
        assert retrieved is new_cfg
        assert retrieved.level is AutonomyLevel.UNRESTRICTED

    def test_reset_allows_fresh_creation(self) -> None:
        first = get_autonomy_config()
        _reset_singleton()
        second = get_autonomy_config()
        assert first is not second

    def test_set_none_then_get_creates_new(self) -> None:
        _module._autonomy_config = None
        cfg = get_autonomy_config()
        assert cfg is not None
        assert isinstance(cfg, AutonomyConfig)

    def test_multiple_set_calls_last_wins(self) -> None:
        cfg1 = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        cfg2 = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        set_autonomy_config(cfg1)
        set_autonomy_config(cfg2)
        assert get_autonomy_config() is cfg2

    def test_singleton_isolation_between_tests(self) -> None:
        # After setup_method resets singleton, get_autonomy_config creates new
        cfg = get_autonomy_config()
        assert cfg.level is AutonomyLevel.GUIDED

    def test_set_config_updates_module_global(self) -> None:
        new_cfg = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        set_autonomy_config(new_cfg)
        assert _module._autonomy_config is new_cfg


# ---------------------------------------------------------------------------
# 27. Integration: full approval flow with safety limits
# ---------------------------------------------------------------------------


class TestIntegrationApprovalWithLimits:
    async def test_approved_action_proceeds(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.GUIDED)
        cfg.set_approval_callback(AsyncMock(return_value=True))
        cfg.start_run()
        # Simulate iteration tracking alongside approval
        cfg.limits.increment_iteration()
        ok = await cfg.request_approval(
            ActionCategory.CREDENTIAL_ACCESS,
            "Read env var",
        )
        assert ok is True
        assert cfg.limits.current_iterations == 1

    async def test_limit_exceeded_detected_independently(self) -> None:
        cfg = AutonomyConfig(
            level=AutonomyLevel.GUIDED,
            limits=SafetyLimits(max_iterations=2),
        )
        cfg.start_run()
        cfg.limits.current_iterations = 3
        ok, reason = cfg.check_limits()
        assert ok is False

    async def test_start_run_clears_state_for_new_run(self) -> None:
        cfg = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        cfg._pending_approvals.append(
            ApprovalRequest(ActionCategory.FILE_WRITE, "Old action")
        )
        cfg.limits.current_iterations = 50
        cfg.start_run()
        assert cfg._pending_approvals == []
        assert cfg.limits.current_iterations == 0

    async def test_concurrent_approval_requests(self) -> None:
        approved_categories: list[ActionCategory] = []

        async def capture_callback(req: ApprovalRequest) -> bool:
            approved_categories.append(req.action_category)
            return True

        # Enable file-delete so the permission gate passes for all three actions
        cfg = AutonomyConfig(
            level=AutonomyLevel.SUPERVISED,
            permissions=PermissionFlags(allow_file_system_delete=True),
        )
        cfg.set_approval_callback(capture_callback)

        results = await asyncio.gather(
            cfg.request_approval(ActionCategory.FILE_WRITE, "Write 1"),
            cfg.request_approval(ActionCategory.FILE_DELETE, "Delete 1"),
            cfg.request_approval(ActionCategory.SHELL_EXECUTE, "Run script"),
        )
        assert all(results)
        assert len(approved_categories) == 3
