"""Tests for AutonomyConfig — permission flags, safety limits, approval logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.services.agents.autonomy_config import (
    CONFIRMATION_REQUIRED,
    ActionCategory,
    ApprovalRequest,
    AutonomyConfig,
    AutonomyLevel,
    PermissionFlags,
    SafetyLimits,
)

# ---------------------------------------------------------------------------
# AutonomyLevel / ActionCategory enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_autonomy_levels(self):
        assert AutonomyLevel.SUPERVISED.value == "supervised"
        assert AutonomyLevel.GUIDED.value == "guided"
        assert AutonomyLevel.AUTONOMOUS.value == "autonomous"
        assert AutonomyLevel.UNRESTRICTED.value == "unrestricted"

    def test_action_categories(self):
        assert len(ActionCategory) == 10

    def test_confirmation_required_supervised_all(self):
        assert CONFIRMATION_REQUIRED[AutonomyLevel.SUPERVISED] == set(ActionCategory)

    def test_confirmation_required_unrestricted_empty(self):
        assert CONFIRMATION_REQUIRED[AutonomyLevel.UNRESTRICTED] == set()


# ---------------------------------------------------------------------------
# PermissionFlags
# ---------------------------------------------------------------------------


class TestPermissionFlags:
    def test_defaults(self):
        pf = PermissionFlags()
        assert pf.allow_credential_access is True
        assert pf.allow_file_system_delete is False
        assert pf.allow_payment_operations is False
        assert pf.allow_system_config is False

    def test_is_domain_allowed_default(self):
        pf = PermissionFlags()
        assert pf.is_domain_allowed("example.com") is True

    def test_is_domain_blocked(self):
        pf = PermissionFlags()
        assert pf.is_domain_allowed("localhost") is False
        assert pf.is_domain_allowed("127.0.0.1") is False
        assert pf.is_domain_allowed("some.internal.service") is False

    def test_is_domain_allowed_with_allowlist(self):
        pf = PermissionFlags(allowed_domains={"example.com", "api.test.com"})
        assert pf.is_domain_allowed("example.com") is True
        assert pf.is_domain_allowed("unknown.com") is False

    def test_blocked_takes_priority(self):
        pf = PermissionFlags(allowed_domains={"localhost"})
        assert pf.is_domain_allowed("localhost") is False

    def test_is_path_allowed_default(self):
        pf = PermissionFlags()
        assert pf.is_path_allowed("/tmp/file.txt") is True

    def test_is_path_blocked(self):
        pf = PermissionFlags()
        assert pf.is_path_allowed("/etc/passwd") is False
        assert pf.is_path_allowed("/var/log/syslog") is False
        assert pf.is_path_allowed("/root/.ssh/id_rsa") is False

    def test_is_path_allowed_with_allowlist(self):
        pf = PermissionFlags(allowed_paths={"/tmp", "/workspace"})
        assert pf.is_path_allowed("/tmp/output.txt") is True
        assert pf.is_path_allowed("/opt/data.txt") is False

    def test_blocked_paths_override_allowed(self):
        pf = PermissionFlags(allowed_paths={"/etc", "/tmp"})
        assert pf.is_path_allowed("/etc/passwd") is False


# ---------------------------------------------------------------------------
# SafetyLimits
# ---------------------------------------------------------------------------


class TestSafetyLimits:
    def test_defaults(self):
        sl = SafetyLimits()
        assert sl.max_iterations == 200
        assert sl.max_tool_calls == 300
        assert sl.max_execution_time_seconds == 3600
        assert sl.max_cost_usd is None

    def test_start_run_resets(self):
        sl = SafetyLimits()
        sl.current_iterations = 50
        sl.current_tool_calls = 100
        sl.current_tokens = 5000
        sl.current_cost = 1.5
        sl.start_run()
        assert sl.current_iterations == 0
        assert sl.current_tool_calls == 0
        assert sl.current_tokens == 0
        assert sl.current_cost == 0.0
        assert sl.start_time is not None

    def test_increment_iteration_within_limit(self):
        sl = SafetyLimits(max_iterations=5)
        for _ in range(5):
            assert sl.increment_iteration() is True

    def test_increment_iteration_exceeds_limit(self):
        sl = SafetyLimits(max_iterations=2)
        sl.increment_iteration()
        sl.increment_iteration()
        assert sl.increment_iteration() is False

    def test_increment_tool_calls_within(self):
        sl = SafetyLimits(max_tool_calls=10)
        assert sl.increment_tool_calls(5) is True

    def test_increment_tool_calls_exceeds(self):
        sl = SafetyLimits(max_tool_calls=5)
        sl.increment_tool_calls(6)
        assert sl.current_tool_calls == 6

    def test_add_tokens_within(self):
        sl = SafetyLimits(max_tokens_per_run=1000)
        assert sl.add_tokens(500) is True

    def test_add_tokens_exceeds(self):
        sl = SafetyLimits(max_tokens_per_run=100)
        assert sl.add_tokens(200) is False

    def test_add_cost_no_limit(self):
        sl = SafetyLimits(max_cost_usd=None)
        assert sl.add_cost(999.0) is True

    def test_add_cost_within_limit(self):
        sl = SafetyLimits(max_cost_usd=10.0)
        assert sl.add_cost(5.0) is True

    def test_add_cost_exceeds_limit(self):
        sl = SafetyLimits(max_cost_usd=1.0)
        assert sl.add_cost(2.0) is False

    def test_check_time_limit_no_start(self):
        sl = SafetyLimits()
        assert sl.check_time_limit() is True

    def test_check_time_limit_within(self):
        sl = SafetyLimits(max_execution_time_seconds=3600)
        sl.start_run()
        assert sl.check_time_limit() is True

    def test_check_time_limit_exceeded(self):
        sl = SafetyLimits(max_execution_time_seconds=10)
        sl.start_run()
        sl.start_time = datetime.now(UTC) - timedelta(seconds=20)
        assert sl.check_time_limit() is False

    def test_check_all_limits_ok(self):
        sl = SafetyLimits()
        sl.start_run()
        ok, reason = sl.check_all_limits()
        assert ok is True
        assert reason is None

    def test_check_all_limits_iteration_exceeded(self):
        sl = SafetyLimits(max_iterations=1)
        sl.current_iterations = 5
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Iteration" in reason

    def test_check_all_limits_tool_calls_exceeded(self):
        sl = SafetyLimits(max_tool_calls=1)
        sl.current_tool_calls = 5
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Tool call" in reason

    def test_check_all_limits_tokens_exceeded(self):
        sl = SafetyLimits(max_tokens_per_run=100)
        sl.current_tokens = 200
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Token" in reason

    def test_check_all_limits_cost_exceeded(self):
        sl = SafetyLimits(max_cost_usd=1.0)
        sl.current_cost = 2.0
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Cost" in reason

    def test_check_all_limits_time_exceeded(self):
        sl = SafetyLimits(max_execution_time_seconds=1)
        sl.start_run()
        sl.start_time = datetime.now(UTC) - timedelta(seconds=10)
        ok, reason = sl.check_all_limits()
        assert ok is False
        assert "Time" in reason

    def test_get_remaining(self):
        sl = SafetyLimits(max_iterations=100, max_tool_calls=50, max_tokens_per_run=10000)
        sl.start_run()
        sl.current_iterations = 30
        sl.current_tool_calls = 10
        sl.current_tokens = 2000
        remaining = sl.get_remaining()
        assert remaining["iterations"] == 70
        assert remaining["tool_calls"] == 40
        assert remaining["tokens"] == 8000
        assert remaining["cost_usd"] is None


# ---------------------------------------------------------------------------
# ApprovalRequest
# ---------------------------------------------------------------------------


class TestApprovalRequest:
    def test_to_dict(self):
        req = ApprovalRequest(
            action_category=ActionCategory.PAYMENT,
            action_description="Process payment $50",
            tool_name="stripe_charge",
            risk_level="critical",
        )
        d = req.to_dict()
        assert d["action_category"] == "payment"
        assert d["action_description"] == "Process payment $50"
        assert d["tool_name"] == "stripe_charge"
        assert d["risk_level"] == "critical"
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# AutonomyConfig — core logic
# ---------------------------------------------------------------------------


class TestAutonomyConfig:
    def test_default_level_guided(self):
        config = AutonomyConfig()
        assert config.level == AutonomyLevel.GUIDED

    def test_custom_level(self):
        config = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        assert config.level == AutonomyLevel.AUTONOMOUS

    # -- requires_approval -----------------------------------------------
    def test_supervised_requires_all(self):
        config = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        assert config.requires_approval(ActionCategory.EXTERNAL_REQUEST) is True
        assert config.requires_approval(ActionCategory.BROWSER_NAVIGATE) is True

    def test_guided_requires_critical(self):
        config = AutonomyConfig(level=AutonomyLevel.GUIDED)
        assert config.requires_approval(ActionCategory.PAYMENT) is True
        assert config.requires_approval(ActionCategory.CREDENTIAL_ACCESS) is True
        assert config.requires_approval(ActionCategory.EXTERNAL_REQUEST) is False

    def test_autonomous_minimal_approval(self):
        config = AutonomyConfig(level=AutonomyLevel.AUTONOMOUS)
        assert config.requires_approval(ActionCategory.PAYMENT) is True
        assert config.requires_approval(ActionCategory.SYSTEM_CONFIG) is True
        assert config.requires_approval(ActionCategory.FILE_WRITE) is False

    def test_unrestricted_no_approval(self):
        # Payment & delete are disabled by default in PermissionFlags,
        # so enable them explicitly to test pure autonomy level logic.
        pf = PermissionFlags(allow_payment_operations=True, allow_file_system_delete=True)
        config = AutonomyConfig(level=AutonomyLevel.UNRESTRICTED, permissions=pf)
        assert config.requires_approval(ActionCategory.PAYMENT) is False
        assert config.requires_approval(ActionCategory.SHELL_EXECUTE) is False

    def test_disabled_permission_forces_approval(self):
        pf = PermissionFlags(allow_file_system_write=False)
        config = AutonomyConfig(level=AutonomyLevel.UNRESTRICTED, permissions=pf)
        assert config.requires_approval(ActionCategory.FILE_WRITE) is True

    # -- is_action_allowed -----------------------------------------------
    def test_action_allowed_default(self):
        config = AutonomyConfig()
        assert config.is_action_allowed(ActionCategory.EXTERNAL_REQUEST) is True

    def test_action_blocked_by_permission(self):
        pf = PermissionFlags(allow_payment_operations=False)
        config = AutonomyConfig(permissions=pf)
        assert config.is_action_allowed(ActionCategory.PAYMENT) is False

    def test_action_allowed_for_unknown_category(self):
        config = AutonomyConfig()
        # NETWORK_REQUEST is not in permission_map, should default True
        assert config.is_action_allowed(ActionCategory.NETWORK_REQUEST) is True

    # -- categorize_tool -------------------------------------------------
    def test_categorize_credential_tool(self):
        config = AutonomyConfig()
        assert config.categorize_tool("get_password") == ActionCategory.CREDENTIAL_ACCESS
        assert config.categorize_tool("auth_token") == ActionCategory.CREDENTIAL_ACCESS

    def test_categorize_file_write(self):
        config = AutonomyConfig()
        assert config.categorize_tool("file_write") == ActionCategory.FILE_WRITE
        assert config.categorize_tool("save_document") == ActionCategory.FILE_WRITE

    def test_categorize_file_delete(self):
        config = AutonomyConfig()
        assert config.categorize_tool("file_delete") == ActionCategory.FILE_DELETE
        assert config.categorize_tool("rm_file") == ActionCategory.FILE_DELETE

    def test_categorize_shell(self):
        config = AutonomyConfig()
        assert config.categorize_tool("shell_exec") == ActionCategory.SHELL_EXECUTE
        assert config.categorize_tool("bash_command") == ActionCategory.SHELL_EXECUTE

    def test_categorize_browser(self):
        config = AutonomyConfig()
        assert config.categorize_tool("browser_navigate") == ActionCategory.BROWSER_NAVIGATE
        assert config.categorize_tool("click_element") == ActionCategory.BROWSER_NAVIGATE

    def test_categorize_payment(self):
        config = AutonomyConfig()
        assert config.categorize_tool("process_payment") == ActionCategory.PAYMENT
        assert config.categorize_tool("purchase_item") == ActionCategory.PAYMENT

    def test_categorize_search(self):
        config = AutonomyConfig()
        assert config.categorize_tool("search_web") == ActionCategory.EXTERNAL_REQUEST

    def test_categorize_data_mod(self):
        config = AutonomyConfig()
        assert config.categorize_tool("update_record") == ActionCategory.DATA_MODIFICATION

    def test_categorize_unknown(self):
        config = AutonomyConfig()
        assert config.categorize_tool("some_random_tool") == ActionCategory.NETWORK_REQUEST


# ---------------------------------------------------------------------------
# AutonomyConfig — async approval
# ---------------------------------------------------------------------------


class TestAutonomyConfigApproval:
    @pytest.mark.asyncio()
    async def test_no_approval_needed(self):
        config = AutonomyConfig(level=AutonomyLevel.UNRESTRICTED)
        result = await config.request_approval(ActionCategory.FILE_WRITE, "write file")
        assert result is True

    @pytest.mark.asyncio()
    async def test_action_blocked(self):
        pf = PermissionFlags(allow_payment_operations=False)
        config = AutonomyConfig(permissions=pf)
        result = await config.request_approval(ActionCategory.PAYMENT, "pay $50")
        assert result is False

    @pytest.mark.asyncio()
    async def test_approval_callback_approved(self):
        config = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        config.set_approval_callback(AsyncMock(return_value=True))
        result = await config.request_approval(ActionCategory.FILE_WRITE, "write file")
        assert result is True

    @pytest.mark.asyncio()
    async def test_approval_callback_denied(self):
        config = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        config.set_approval_callback(AsyncMock(return_value=False))
        result = await config.request_approval(ActionCategory.FILE_WRITE, "write file")
        assert result is False

    @pytest.mark.asyncio()
    async def test_approval_callback_error(self):
        config = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        config.set_approval_callback(AsyncMock(side_effect=RuntimeError("boom")))
        result = await config.request_approval(ActionCategory.FILE_WRITE, "write file")
        assert result is False

    @pytest.mark.asyncio()
    async def test_no_callback_pending(self):
        config = AutonomyConfig(level=AutonomyLevel.SUPERVISED)
        result = await config.request_approval(ActionCategory.FILE_WRITE, "write file")
        assert result is False
        assert len(config._pending_approvals) == 1


# ---------------------------------------------------------------------------
# AutonomyConfig — limits and status
# ---------------------------------------------------------------------------


class TestAutonomyConfigLimitsAndStatus:
    def test_check_limits(self):
        config = AutonomyConfig()
        config.start_run()
        ok, _reason = config.check_limits()
        assert ok is True

    def test_start_run_clears_pending(self):
        config = AutonomyConfig()
        config._pending_approvals.append(
            ApprovalRequest(action_category=ActionCategory.FILE_WRITE, action_description="x"),
        )
        config.start_run()
        assert len(config._pending_approvals) == 0

    def test_get_status(self):
        config = AutonomyConfig()
        config.start_run()
        status = config.get_status()
        assert status["autonomy_level"] == "guided"
        assert status["within_limits"] is True
        assert status["pending_approvals"] == 0
        assert "remaining" in status
        assert "current_stats" in status


# ---------------------------------------------------------------------------
# AutonomyConfig — from_settings
# ---------------------------------------------------------------------------


class TestAutonomyConfigFromSettings:
    def test_from_settings_defaults(self):
        settings = SimpleNamespace()
        config = AutonomyConfig.from_settings(settings)
        assert config.level == AutonomyLevel.GUIDED

    def test_from_settings_autonomous(self):
        settings = SimpleNamespace(autonomy_level="autonomous")
        config = AutonomyConfig.from_settings(settings)
        assert config.level == AutonomyLevel.AUTONOMOUS

    def test_from_settings_invalid_level(self):
        settings = SimpleNamespace(autonomy_level="banana")
        config = AutonomyConfig.from_settings(settings)
        assert config.level == AutonomyLevel.GUIDED

    def test_from_settings_permissions(self):
        settings = SimpleNamespace(
            allow_file_system_delete=True,
            allow_payment_operations=True,
        )
        config = AutonomyConfig.from_settings(settings)
        assert config.permissions.allow_file_system_delete is True
        assert config.permissions.allow_payment_operations is True

    def test_from_settings_limits(self):
        settings = SimpleNamespace(
            max_iterations=10,
            max_tool_calls=20,
            max_tokens_per_run=1000,
            max_cost_usd=5.0,
        )
        config = AutonomyConfig.from_settings(settings)
        assert config.limits.max_iterations == 10
        assert config.limits.max_tool_calls == 20
        assert config.limits.max_cost_usd == 5.0
