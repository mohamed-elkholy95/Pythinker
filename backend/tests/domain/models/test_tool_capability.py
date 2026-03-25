"""Tests for RiskLevel, ToolCapability, and the TOOL_CAPABILITIES registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.tool_capability import (
    TOOL_CAPABILITIES,
    RiskLevel,
    ToolCapability,
    get_capability,
)
from app.domain.models.tool_name import ToolName

# ─────────────────────────────────────────────────────────────────────────────
# RiskLevel enum
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskLevelEnum:
    def test_all_five_members_exist(self) -> None:
        names = {m.name for m in RiskLevel}
        assert names == {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_safe_string_value(self) -> None:
        assert RiskLevel.SAFE == "safe"
        assert RiskLevel.SAFE.value == "safe"

    def test_low_string_value(self) -> None:
        assert RiskLevel.LOW == "low"
        assert RiskLevel.LOW.value == "low"

    def test_medium_string_value(self) -> None:
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.MEDIUM.value == "medium"

    def test_high_string_value(self) -> None:
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.HIGH.value == "high"

    def test_critical_string_value(self) -> None:
        assert RiskLevel.CRITICAL == "critical"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_is_str_subclass(self) -> None:
        assert isinstance(RiskLevel.SAFE, str)


# ─────────────────────────────────────────────────────────────────────────────
# ToolCapability model — defaults and construction
# ─────────────────────────────────────────────────────────────────────────────


class TestToolCapabilityDefaults:
    def test_default_parallelizable_is_false(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        assert cap.parallelizable is False

    def test_default_risk_level_is_safe(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        assert cap.risk_level == RiskLevel.SAFE

    def test_default_max_concurrent_is_one(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        assert cap.max_concurrent == 1

    def test_default_cacheable_is_false(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_WRITE)
        assert cap.cacheable is False

    def test_default_cache_ttl_seconds_is_zero(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_WRITE)
        assert cap.cache_ttl_seconds == 0

    def test_default_network_dependent_is_false(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        assert cap.network_dependent is False

    def test_default_idempotent_is_false(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_WRITE)
        assert cap.idempotent is False

    def test_default_phase_restrictions_is_empty_list(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        assert cap.phase_restrictions == []

    def test_all_fields_settable_via_constructor(self) -> None:
        cap = ToolCapability(
            name=ToolName.SHELL_EXEC,
            parallelizable=True,
            risk_level=RiskLevel.HIGH,
            phase_restrictions=["executing"],
            max_concurrent=4,
            cacheable=True,
            cache_ttl_seconds=120,
            network_dependent=True,
            idempotent=True,
        )
        assert cap.name == ToolName.SHELL_EXEC
        assert cap.parallelizable is True
        assert cap.risk_level == RiskLevel.HIGH
        assert cap.phase_restrictions == ["executing"]
        assert cap.max_concurrent == 4
        assert cap.cacheable is True
        assert cap.cache_ttl_seconds == 120
        assert cap.network_dependent is True
        assert cap.idempotent is True


class TestToolCapabilityFrozen:
    def test_cannot_mutate_name(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        with pytest.raises((ValidationError, TypeError)):
            cap.name = ToolName.FILE_WRITE  # type: ignore[misc]

    def test_cannot_mutate_risk_level(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ)
        with pytest.raises((ValidationError, TypeError)):
            cap.risk_level = RiskLevel.HIGH  # type: ignore[misc]

    def test_cannot_mutate_parallelizable(self) -> None:
        cap = ToolCapability(name=ToolName.FILE_READ, parallelizable=True)
        with pytest.raises((ValidationError, TypeError)):
            cap.parallelizable = False  # type: ignore[misc]

    def test_cannot_mutate_max_concurrent(self) -> None:
        cap = ToolCapability(name=ToolName.SHELL_EXEC, max_concurrent=2)
        with pytest.raises((ValidationError, TypeError)):
            cap.max_concurrent = 99  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — file operations
# ─────────────────────────────────────────────────────────────────────────────


class TestFileOperationRiskLevels:
    def test_file_read_is_safe(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_READ].risk_level == RiskLevel.SAFE

    def test_file_write_is_low(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_WRITE].risk_level == RiskLevel.LOW

    def test_file_delete_is_high(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_DELETE].risk_level == RiskLevel.HIGH

    def test_file_rename_is_medium(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_RENAME].risk_level == RiskLevel.MEDIUM

    def test_file_read_is_idempotent(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_READ].idempotent is True

    def test_file_read_is_cacheable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_READ].cacheable is True

    def test_file_read_cache_ttl_is_300(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_READ].cache_ttl_seconds == 300


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — shell operations
# ─────────────────────────────────────────────────────────────────────────────


class TestShellOperationCapabilities:
    def test_shell_exec_risk_is_medium(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SHELL_EXEC].risk_level == RiskLevel.MEDIUM

    def test_shell_kill_process_risk_is_high(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SHELL_KILL_PROCESS].risk_level == RiskLevel.HIGH

    def test_shell_view_risk_is_safe(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SHELL_VIEW].risk_level == RiskLevel.SAFE

    def test_shell_exec_max_concurrent_is_two(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SHELL_EXEC].max_concurrent == 2


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — browser / search operations
# ─────────────────────────────────────────────────────────────────────────────


class TestBrowserAndSearchCapabilities:
    def test_search_is_network_dependent(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SEARCH].network_dependent is True

    def test_browser_navigate_is_network_dependent(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.BROWSER_NAVIGATE].network_dependent is True

    def test_browser_get_content_is_network_dependent(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.BROWSER_GET_CONTENT].network_dependent is True

    def test_search_is_cacheable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SEARCH].cacheable is True

    def test_search_cache_ttl_is_1800(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SEARCH].cache_ttl_seconds == 1800


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — parallelizable tools
# ─────────────────────────────────────────────────────────────────────────────


class TestParallelizableTools:
    def test_file_read_is_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_READ].parallelizable is True

    def test_file_search_is_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_SEARCH].parallelizable is True

    def test_file_list_directory_is_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_LIST_DIRECTORY].parallelizable is True

    def test_browser_view_is_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.BROWSER_VIEW].parallelizable is True

    def test_file_write_is_not_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.FILE_WRITE].parallelizable is False

    def test_shell_exec_is_not_parallelizable(self) -> None:
        assert TOOL_CAPABILITIES[ToolName.SHELL_EXEC].parallelizable is False


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — cacheable tools have positive TTL
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheableToolsHavePositiveTTL:
    def test_all_cacheable_tools_have_positive_ttl(self) -> None:
        offenders: list[str] = []
        for tool_name, cap in TOOL_CAPABILITIES.items():
            if cap.cacheable and cap.cache_ttl_seconds <= 0:
                offenders.append(tool_name.value)
        assert offenders == [], f"Cacheable tools with non-positive TTL: {offenders}"

    def test_non_cacheable_tools_have_zero_ttl(self) -> None:
        offenders: list[str] = []
        for tool_name, cap in TOOL_CAPABILITIES.items():
            if not cap.cacheable and cap.cache_ttl_seconds != 0:
                offenders.append(tool_name.value)
        assert offenders == [], f"Non-cacheable tools with non-zero TTL: {offenders}"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — CRITICAL risk tools are never parallelizable
# ─────────────────────────────────────────────────────────────────────────────


class TestCriticalRiskNotParallelizable:
    def test_no_critical_risk_tool_is_parallelizable(self) -> None:
        offenders: list[str] = []
        for tool_name, cap in TOOL_CAPABILITIES.items():
            if cap.risk_level == RiskLevel.CRITICAL and cap.parallelizable:
                offenders.append(tool_name.value)
        assert offenders == [], f"CRITICAL-risk tools marked parallelizable: {offenders}"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL_CAPABILITIES registry — structural consistency
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistryConsistency:
    def test_registry_is_non_empty(self) -> None:
        assert len(TOOL_CAPABILITIES) > 0

    def test_all_entries_have_matching_name_field(self) -> None:
        mismatches: list[str] = []
        for key, cap in TOOL_CAPABILITIES.items():
            if cap.name != key:
                mismatches.append(f"{key.value!r} -> cap.name={cap.name.value!r}")
        assert mismatches == [], f"Registry key/name field mismatches: {mismatches}"

    def test_all_registry_values_are_tool_capability_instances(self) -> None:
        for key, cap in TOOL_CAPABILITIES.items():
            assert isinstance(cap, ToolCapability), f"{key.value!r} value is not a ToolCapability"

    def test_all_registry_keys_are_tool_name_instances(self) -> None:
        for key in TOOL_CAPABILITIES:
            assert isinstance(key, ToolName), f"Key {key!r} is not a ToolName"


# ─────────────────────────────────────────────────────────────────────────────
# get_capability helper
# ─────────────────────────────────────────────────────────────────────────────


class TestGetCapabilityHelper:
    def test_returns_capability_for_known_tool_name_enum(self) -> None:
        cap = get_capability(ToolName.FILE_READ)
        assert cap is not None
        assert cap.name == ToolName.FILE_READ

    def test_returns_capability_for_known_tool_name_string(self) -> None:
        cap = get_capability("file_read")
        assert cap is not None
        assert cap.name == ToolName.FILE_READ

    def test_returns_none_for_unknown_string(self) -> None:
        cap = get_capability("nonexistent_tool_xyz")
        assert cap is None

    def test_returns_none_for_empty_string(self) -> None:
        cap = get_capability("")
        assert cap is None
