"""Tests for ToolName enum — classification sets, instance properties, and class methods."""

from __future__ import annotations

import pytest

from app.domain.models.tool_name import ToolName

# ─────────────────────────────────────────────────────────────────────────────
# Enum basics — string identity and member count
# ─────────────────────────────────────────────────────────────────────────────


class TestEnumBasics:
    def test_total_member_count_exceeds_100(self) -> None:
        assert len(ToolName) > 100

    def test_is_str_subclass(self) -> None:
        assert isinstance(ToolName.FILE_READ, str)

    def test_file_read_string_equality(self) -> None:
        assert ToolName.FILE_READ == "file_read"

    def test_file_write_string_equality(self) -> None:
        assert ToolName.FILE_WRITE == "file_write"

    def test_shell_exec_string_equality(self) -> None:
        assert ToolName.SHELL_EXEC == "shell_exec"

    def test_info_search_web_string_equality(self) -> None:
        assert ToolName.INFO_SEARCH_WEB == "info_search_web"

    def test_browser_view_string_equality(self) -> None:
        assert ToolName.BROWSER_VIEW == "browser_view"

    def test_value_matches_string(self) -> None:
        assert ToolName.FILE_READ.value == "file_read"

    def test_construction_from_string(self) -> None:
        assert ToolName("file_read") is ToolName.FILE_READ

    def test_unknown_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            ToolName("nonexistent_tool_xyz")

    def test_each_member_compares_equal_to_its_value(self) -> None:
        """Every member compares equal to its own value string via __eq__."""
        mismatches = [m for m in ToolName if m != m.value]
        assert mismatches == []


# ─────────────────────────────────────────────────────────────────────────────
# is_read_only property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsReadOnly:
    def test_file_read_is_read_only(self) -> None:
        assert ToolName.FILE_READ.is_read_only is True

    def test_file_write_is_not_read_only(self) -> None:
        assert ToolName.FILE_WRITE.is_read_only is False

    def test_shell_exec_is_not_read_only(self) -> None:
        assert ToolName.SHELL_EXEC.is_read_only is False

    def test_shell_view_is_read_only(self) -> None:
        assert ToolName.SHELL_VIEW.is_read_only is True

    def test_info_search_web_is_read_only(self) -> None:
        assert ToolName.INFO_SEARCH_WEB.is_read_only is True

    def test_wide_research_is_read_only(self) -> None:
        assert ToolName.WIDE_RESEARCH.is_read_only is True

    def test_browser_view_is_read_only(self) -> None:
        assert ToolName.BROWSER_VIEW.is_read_only is True

    def test_test_list_is_read_only(self) -> None:
        assert ToolName.TEST_LIST.is_read_only is True

    def test_test_run_is_not_read_only(self) -> None:
        assert ToolName.TEST_RUN.is_read_only is False

    def test_kb_query_is_read_only(self) -> None:
        assert ToolName.KB_QUERY.is_read_only is True

    def test_idle_is_read_only(self) -> None:
        assert ToolName.IDLE.is_read_only is True

    def test_git_status_is_read_only(self) -> None:
        assert ToolName.GIT_STATUS.is_read_only is True

    def test_git_clone_is_not_read_only(self) -> None:
        assert ToolName.GIT_CLONE.is_read_only is False

    def test_all_read_only_tools_consistent_with_set(self) -> None:
        """is_read_only must agree with membership in _READ_ONLY for every member."""
        offenders = [m for m in ToolName if m.is_read_only != (m in ToolName._READ_ONLY)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# is_action property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsAction:
    def test_file_write_is_action(self) -> None:
        assert ToolName.FILE_WRITE.is_action is True

    def test_file_read_is_not_action(self) -> None:
        assert ToolName.FILE_READ.is_action is False

    def test_shell_exec_is_action(self) -> None:
        assert ToolName.SHELL_EXEC.is_action is True

    def test_browser_click_is_action(self) -> None:
        assert ToolName.BROWSER_CLICK.is_action is True

    def test_browser_navigate_is_action(self) -> None:
        assert ToolName.BROWSER_NAVIGATE.is_action is True

    def test_test_run_is_action(self) -> None:
        assert ToolName.TEST_RUN.is_action is True

    def test_git_clone_is_action(self) -> None:
        assert ToolName.GIT_CLONE.is_action is True

    def test_code_execute_is_action(self) -> None:
        assert ToolName.CODE_EXECUTE.is_action is True

    def test_idle_is_not_action(self) -> None:
        assert ToolName.IDLE.is_action is False

    def test_all_action_tools_consistent_with_set(self) -> None:
        offenders = [m for m in ToolName if m.is_action != (m in ToolName._ACTION)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# is_safe_parallel property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsSafeParallel:
    def test_file_read_is_safe_parallel(self) -> None:
        assert ToolName.FILE_READ.is_safe_parallel is True

    def test_shell_exec_is_not_safe_parallel(self) -> None:
        assert ToolName.SHELL_EXEC.is_safe_parallel is False

    def test_browser_view_is_safe_parallel(self) -> None:
        assert ToolName.BROWSER_VIEW.is_safe_parallel is True

    def test_mcp_list_resources_is_safe_parallel(self) -> None:
        assert ToolName.MCP_LIST_RESOURCES.is_safe_parallel is True

    def test_mcp_read_resource_is_safe_parallel(self) -> None:
        assert ToolName.MCP_READ_RESOURCE.is_safe_parallel is True

    def test_scratchpad_write_is_safe_parallel(self) -> None:
        assert ToolName.SCRATCHPAD_WRITE.is_safe_parallel is True

    def test_scratchpad_read_is_safe_parallel(self) -> None:
        assert ToolName.SCRATCHPAD_READ.is_safe_parallel is True

    def test_file_write_is_not_safe_parallel(self) -> None:
        assert ToolName.FILE_WRITE.is_safe_parallel is False

    def test_info_search_web_is_not_safe_parallel(self) -> None:
        assert ToolName.INFO_SEARCH_WEB.is_safe_parallel is False

    def test_all_safe_parallel_tools_consistent_with_set(self) -> None:
        offenders = [m for m in ToolName if m.is_safe_parallel != (m in ToolName._SAFE_PARALLEL)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# is_search property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsSearch:
    def test_info_search_web_is_search(self) -> None:
        assert ToolName.INFO_SEARCH_WEB.is_search is True

    def test_web_search_is_search(self) -> None:
        assert ToolName.WEB_SEARCH.is_search is True

    def test_wide_research_is_search(self) -> None:
        assert ToolName.WIDE_RESEARCH.is_search is True

    def test_search_is_search(self) -> None:
        assert ToolName.SEARCH.is_search is True

    def test_file_read_is_not_search(self) -> None:
        assert ToolName.FILE_READ.is_search is False

    def test_shell_exec_is_not_search(self) -> None:
        assert ToolName.SHELL_EXEC.is_search is False

    def test_browser_navigate_is_not_search(self) -> None:
        assert ToolName.BROWSER_NAVIGATE.is_search is False

    def test_all_search_tools_consistent_with_set(self) -> None:
        offenders = [m for m in ToolName if m.is_search != (m in ToolName._SEARCH)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# is_network property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsNetwork:
    def test_info_search_web_is_network(self) -> None:
        assert ToolName.INFO_SEARCH_WEB.is_network is True

    def test_browser_navigate_is_network(self) -> None:
        assert ToolName.BROWSER_NAVIGATE.is_network is True

    def test_wide_research_is_network(self) -> None:
        assert ToolName.WIDE_RESEARCH.is_network is True

    def test_scrape_structured_is_network(self) -> None:
        assert ToolName.SCRAPE_STRUCTURED.is_network is True

    def test_playwright_navigate_is_network(self) -> None:
        assert ToolName.PLAYWRIGHT_NAVIGATE.is_network is True

    def test_file_read_is_not_network(self) -> None:
        assert ToolName.FILE_READ.is_network is False

    def test_shell_exec_is_not_network(self) -> None:
        assert ToolName.SHELL_EXEC.is_network is False

    def test_all_network_tools_consistent_with_set(self) -> None:
        offenders = [m for m in ToolName if m.is_network != (m in ToolName._NETWORK)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# is_view property
# ─────────────────────────────────────────────────────────────────────────────


class TestIsView:
    def test_browser_view_is_view(self) -> None:
        assert ToolName.BROWSER_VIEW.is_view is True

    def test_file_view_is_view(self) -> None:
        assert ToolName.FILE_VIEW.is_view is True

    def test_playwright_get_content_is_view(self) -> None:
        assert ToolName.PLAYWRIGHT_GET_CONTENT.is_view is True

    def test_playwright_screenshot_is_view(self) -> None:
        assert ToolName.PLAYWRIGHT_SCREENSHOT.is_view is True

    def test_browser_agent_extract_is_view(self) -> None:
        assert ToolName.BROWSER_AGENT_EXTRACT.is_view is True

    def test_file_write_is_not_view(self) -> None:
        assert ToolName.FILE_WRITE.is_view is False

    def test_shell_exec_is_not_view(self) -> None:
        assert ToolName.SHELL_EXEC.is_view is False

    def test_all_view_tools_consistent_with_set(self) -> None:
        offenders = [m for m in ToolName if m.is_view != (m in ToolName._VIEW)]
        assert offenders == []


# ─────────────────────────────────────────────────────────────────────────────
# for_phase class method
# ─────────────────────────────────────────────────────────────────────────────


class TestForPhase:
    def test_planning_returns_frozenset(self) -> None:
        result = ToolName.for_phase("planning")
        assert isinstance(result, frozenset)

    def test_planning_contains_file_read(self) -> None:
        result = ToolName.for_phase("planning")
        assert result is not None
        assert ToolName.FILE_READ in result

    def test_planning_contains_info_search_web(self) -> None:
        result = ToolName.for_phase("planning")
        assert result is not None
        assert ToolName.INFO_SEARCH_WEB in result

    def test_planning_contains_message_ask_user(self) -> None:
        result = ToolName.for_phase("planning")
        assert result is not None
        assert ToolName.MESSAGE_ASK_USER in result

    def test_planning_contains_workspace_info(self) -> None:
        result = ToolName.for_phase("planning")
        assert result is not None
        assert ToolName.WORKSPACE_INFO in result

    def test_executing_returns_none(self) -> None:
        assert ToolName.for_phase("executing") is None

    def test_verifying_returns_frozenset(self) -> None:
        result = ToolName.for_phase("verifying")
        assert isinstance(result, frozenset)

    def test_verifying_contains_test_run(self) -> None:
        result = ToolName.for_phase("verifying")
        assert result is not None
        assert ToolName.TEST_RUN in result

    def test_verifying_contains_file_read(self) -> None:
        result = ToolName.for_phase("verifying")
        assert result is not None
        assert ToolName.FILE_READ in result

    def test_verifying_contains_shell_exec(self) -> None:
        result = ToolName.for_phase("verifying")
        assert result is not None
        assert ToolName.SHELL_EXEC in result

    def test_verifying_contains_code_execute(self) -> None:
        result = ToolName.for_phase("verifying")
        assert result is not None
        assert ToolName.CODE_EXECUTE in result

    def test_unknown_phase_returns_none(self) -> None:
        assert ToolName.for_phase("unknown") is None

    def test_empty_string_phase_returns_none(self) -> None:
        assert ToolName.for_phase("") is None

    def test_phase_planning_non_empty(self) -> None:
        result = ToolName.for_phase("planning")
        assert result is not None
        assert len(result) > 0

    def test_phase_verifying_non_empty(self) -> None:
        result = ToolName.for_phase("verifying")
        assert result is not None
        assert len(result) > 0

    def test_planning_result_matches_class_var(self) -> None:
        assert ToolName.for_phase("planning") == ToolName._PHASE_PLANNING

    def test_verifying_result_matches_class_var(self) -> None:
        assert ToolName.for_phase("verifying") == ToolName._PHASE_VERIFYING


# ─────────────────────────────────────────────────────────────────────────────
# Class methods returning sets
# ─────────────────────────────────────────────────────────────────────────────


class TestSetAccessorMethods:
    def test_read_only_tools_returns_frozenset(self) -> None:
        assert isinstance(ToolName.read_only_tools(), frozenset)

    def test_read_only_tools_non_empty(self) -> None:
        assert len(ToolName.read_only_tools()) > 0

    def test_action_tools_returns_frozenset(self) -> None:
        assert isinstance(ToolName.action_tools(), frozenset)

    def test_action_tools_non_empty(self) -> None:
        assert len(ToolName.action_tools()) > 0

    def test_safe_parallel_tools_returns_frozenset(self) -> None:
        assert isinstance(ToolName.safe_parallel_tools(), frozenset)

    def test_safe_parallel_tools_non_empty(self) -> None:
        assert len(ToolName.safe_parallel_tools()) > 0

    def test_search_tools_returns_frozenset(self) -> None:
        assert isinstance(ToolName.search_tools(), frozenset)

    def test_search_tools_non_empty(self) -> None:
        assert len(ToolName.search_tools()) > 0

    def test_read_only_tools_matches_class_var(self) -> None:
        assert ToolName.read_only_tools() is ToolName._READ_ONLY

    def test_action_tools_matches_class_var(self) -> None:
        assert ToolName.action_tools() is ToolName._ACTION

    def test_safe_parallel_tools_matches_class_var(self) -> None:
        assert ToolName.safe_parallel_tools() is ToolName._SAFE_PARALLEL

    def test_search_tools_matches_class_var(self) -> None:
        assert ToolName.search_tools() is ToolName._SEARCH


# ─────────────────────────────────────────────────────────────────────────────
# Classification invariants — disjoint and subset constraints
# ─────────────────────────────────────────────────────────────────────────────


class TestClassificationInvariants:
    def test_read_only_and_action_are_disjoint(self) -> None:
        overlap = ToolName._READ_ONLY & ToolName._ACTION
        assert overlap == frozenset(), f"read_only ∩ action is non-empty: {overlap}"

    def test_all_search_members_are_read_only(self) -> None:
        not_read_only = ToolName._SEARCH - ToolName._READ_ONLY
        assert not_read_only == frozenset(), f"Search tools not in _READ_ONLY: {not_read_only}"

    def test_all_safe_parallel_members_are_read_only(self) -> None:
        """_SAFE_PARALLEL is a subset of _READ_ONLY (parallel tools must not mutate state).

        SCRATCHPAD_WRITE is the only intentional exception, so we verify the overlap
        rather than strict subset, and check _SAFE_PARALLEL does not contain any
        write-only action tool.
        """
        action_and_parallel = ToolName._SAFE_PARALLEL & ToolName._ACTION
        # SCRATCHPAD_WRITE is listed in _SAFE_PARALLEL intentionally.
        # Only that member is allowed to be in _ACTION too.
        disallowed = action_and_parallel - {ToolName.SCRATCHPAD_WRITE}
        assert disallowed == frozenset(), f"Action tools unexpectedly in _SAFE_PARALLEL: {disallowed}"

    def test_all_network_members_present_in_read_only_or_action(self) -> None:
        """Every network tool must be classified as either read-only or action."""
        unclassified = ToolName._NETWORK - (ToolName._READ_ONLY | ToolName._ACTION)
        assert unclassified == frozenset(), f"Network tools with no read/action classification: {unclassified}"

    def test_view_is_subset_of_read_only(self) -> None:
        not_read_only = ToolName._VIEW - ToolName._READ_ONLY
        # BROWSER_GET_CONTENT is in _VIEW but also in _ACTION (has side effects).
        # Allow it as the only exception.
        disallowed = not_read_only - {ToolName.BROWSER_GET_CONTENT}
        assert disallowed == frozenset(), f"View tools not in _READ_ONLY (excluding BROWSER_GET_CONTENT): {disallowed}"


# ─────────────────────────────────────────────────────────────────────────────
# _extract_mcp_tool_name
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractMcpToolName:
    def test_three_part_mcp_name_returns_tool_segment(self) -> None:
        assert ToolName._extract_mcp_tool_name("mcp__server__get_docs") == "get_docs"

    def test_four_part_mcp_name_joins_remaining_segments(self) -> None:
        assert ToolName._extract_mcp_tool_name("mcp__server__get__docs") == "get__docs"

    def test_non_mcp_prefix_returns_none(self) -> None:
        assert ToolName._extract_mcp_tool_name("file_read") is None

    def test_single_underscore_mcp_built_in_returns_none(self) -> None:
        # "mcp_list_resources" has single underscores — not the double-underscore pattern.
        assert ToolName._extract_mcp_tool_name("mcp_list_resources") is None

    def test_empty_string_returns_none(self) -> None:
        assert ToolName._extract_mcp_tool_name("") is None

    def test_only_two_parts_returns_none(self) -> None:
        assert ToolName._extract_mcp_tool_name("mcp__server") is None

    def test_different_server_name_still_extracts_tool(self) -> None:
        assert ToolName._extract_mcp_tool_name("mcp__github__list_repos") == "list_repos"

    def test_first_part_not_mcp_returns_none(self) -> None:
        assert ToolName._extract_mcp_tool_name("other__server__get_docs") is None


# ─────────────────────────────────────────────────────────────────────────────
# is_safe_mcp_tool
# ─────────────────────────────────────────────────────────────────────────────


class TestIsSafeMcpTool:
    def test_built_in_mcp_get_prefix_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_get_something") is True

    def test_built_in_mcp_list_prefix_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_list_resources") is True

    def test_built_in_mcp_search_prefix_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_search_docs") is True

    def test_built_in_mcp_read_prefix_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_read_resource") is True

    def test_built_in_mcp_fetch_prefix_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_fetch_data") is True

    def test_dynamic_mcp_get_tool_is_safe(self) -> None:
        # "mcp__server__get_docs" → extracted "get_docs" → startswith "get_" → safe
        assert ToolName.is_safe_mcp_tool("mcp__server__get_docs") is True

    def test_dynamic_mcp_list_tool_is_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp__github__list_repos") is True

    def test_mcp_create_prefix_is_not_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp_create_issue") is False

    def test_dynamic_mcp_write_tool_is_not_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp__server__write_file") is False

    def test_plain_tool_name_is_not_safe_mcp(self) -> None:
        assert ToolName.is_safe_mcp_tool("file_read") is False

    def test_empty_string_is_not_safe_mcp(self) -> None:
        assert ToolName.is_safe_mcp_tool("") is False

    def test_unknown_dynamic_tool_is_not_safe(self) -> None:
        assert ToolName.is_safe_mcp_tool("mcp__server__unknown_action") is False


# ─────────────────────────────────────────────────────────────────────────────
# is_action_mcp_tool
# ─────────────────────────────────────────────────────────────────────────────


class TestIsActionMcpTool:
    def test_mcp_create_prefix_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_create_issue") is True

    def test_mcp_update_prefix_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_update_file") is True

    def test_mcp_delete_prefix_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_delete_branch") is True

    def test_mcp_write_prefix_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_write_resource") is True

    def test_mcp_execute_prefix_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_execute_code") is True

    def test_dynamic_mcp_create_tool_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp__github__create_pr") is True

    def test_dynamic_mcp_delete_tool_is_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp__server__delete_record") is True

    def test_mcp_list_prefix_is_not_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_list_resources") is False

    def test_mcp_get_prefix_is_not_action(self) -> None:
        assert ToolName.is_action_mcp_tool("mcp_get_info") is False

    def test_plain_tool_name_is_not_action_mcp(self) -> None:
        assert ToolName.is_action_mcp_tool("shell_exec") is False

    def test_empty_string_is_not_action_mcp(self) -> None:
        assert ToolName.is_action_mcp_tool("") is False


# ─────────────────────────────────────────────────────────────────────────────
# is_read_tool (string API)
# ─────────────────────────────────────────────────────────────────────────────


class TestIsReadTool:
    def test_file_read_string_is_read_tool(self) -> None:
        assert ToolName.is_read_tool("file_read") is True

    def test_file_write_string_is_not_read_tool(self) -> None:
        assert ToolName.is_read_tool("file_write") is False

    def test_shell_view_string_is_read_tool(self) -> None:
        assert ToolName.is_read_tool("shell_view") is True

    def test_shell_exec_string_is_not_read_tool(self) -> None:
        assert ToolName.is_read_tool("shell_exec") is False

    def test_info_search_web_string_is_read_tool(self) -> None:
        assert ToolName.is_read_tool("info_search_web") is True

    def test_safe_mcp_dynamic_tool_is_read_tool(self) -> None:
        assert ToolName.is_read_tool("mcp__server__get_docs") is True

    def test_action_mcp_dynamic_tool_is_not_read_tool(self) -> None:
        assert ToolName.is_read_tool("mcp__server__create_issue") is False

    def test_completely_unknown_string_is_not_read_tool(self) -> None:
        assert ToolName.is_read_tool("nonexistent_tool_xyz") is False

    def test_empty_string_is_not_read_tool(self) -> None:
        assert ToolName.is_read_tool("") is False


# ─────────────────────────────────────────────────────────────────────────────
# is_action_tool_name (string API)
# ─────────────────────────────────────────────────────────────────────────────


class TestIsActionToolName:
    def test_file_write_string_is_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("file_write") is True

    def test_file_read_string_is_not_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("file_read") is False

    def test_shell_exec_string_is_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("shell_exec") is True

    def test_browser_navigate_string_is_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("browser_navigate") is True

    def test_test_run_string_is_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("test_run") is True

    def test_action_mcp_dynamic_tool_is_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("mcp__server__create_record") is True

    def test_safe_mcp_dynamic_tool_is_not_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("mcp__server__list_items") is False

    def test_completely_unknown_string_is_not_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("nonexistent_tool_xyz") is False

    def test_empty_string_is_not_action_tool(self) -> None:
        assert ToolName.is_action_tool_name("") is False


# ─────────────────────────────────────────────────────────────────────────────
# MCP prefix tuples — structure
# ─────────────────────────────────────────────────────────────────────────────


class TestMcpPrefixTuples:
    def test_safe_mcp_prefixes_is_tuple(self) -> None:
        assert isinstance(ToolName._SAFE_MCP_PREFIXES, tuple)

    def test_safe_mcp_prefixes_non_empty(self) -> None:
        assert len(ToolName._SAFE_MCP_PREFIXES) > 0

    def test_action_mcp_prefixes_is_tuple(self) -> None:
        assert isinstance(ToolName._ACTION_MCP_PREFIXES, tuple)

    def test_action_mcp_prefixes_non_empty(self) -> None:
        assert len(ToolName._ACTION_MCP_PREFIXES) > 0

    def test_safe_and_action_mcp_prefixes_are_disjoint(self) -> None:
        safe_set = set(ToolName._SAFE_MCP_PREFIXES)
        action_set = set(ToolName._ACTION_MCP_PREFIXES)
        overlap = safe_set & action_set
        assert overlap == set(), f"MCP prefix overlap between safe and action: {overlap}"

    def test_safe_mcp_prefixes_all_start_with_mcp(self) -> None:
        bad = [p for p in ToolName._SAFE_MCP_PREFIXES if not p.startswith("mcp_")]
        assert bad == []

    def test_action_mcp_prefixes_all_start_with_mcp(self) -> None:
        bad = [p for p in ToolName._ACTION_MCP_PREFIXES if not p.startswith("mcp_")]
        assert bad == []


# ─────────────────────────────────────────────────────────────────────────────
# Representative spot checks across tool categories
# ─────────────────────────────────────────────────────────────────────────────


class TestCategorySpotChecks:
    """Verify key members from every tool category are present and correctly typed."""

    # File operations
    def test_file_str_replace_is_action(self) -> None:
        assert ToolName.FILE_STR_REPLACE.is_action is True

    def test_file_find_by_name_is_read_only(self) -> None:
        assert ToolName.FILE_FIND_BY_NAME.is_read_only is True

    # Playwright
    def test_playwright_fill_is_action(self) -> None:
        assert ToolName.PLAYWRIGHT_FILL.is_action is True

    def test_playwright_get_content_is_read_only(self) -> None:
        assert ToolName.PLAYWRIGHT_GET_CONTENT.is_read_only is True

    def test_playwright_navigate_is_network(self) -> None:
        assert ToolName.PLAYWRIGHT_NAVIGATE.is_network is True

    # Code executor
    def test_code_execute_python_is_action(self) -> None:
        assert ToolName.CODE_EXECUTE_PYTHON.is_action is True

    def test_code_read_artifact_is_read_only(self) -> None:
        assert ToolName.CODE_READ_ARTIFACT.is_read_only is True

    # Deep scan — all read-only
    def test_deep_scan_security_is_read_only(self) -> None:
        assert ToolName.DEEP_SCAN_SECURITY.is_read_only is True

    def test_deep_scan_project_is_not_action(self) -> None:
        assert ToolName.DEEP_SCAN_PROJECT.is_action is False

    # Canvas
    def test_canvas_get_state_is_read_only(self) -> None:
        assert ToolName.CANVAS_GET_STATE.is_read_only is True

    def test_canvas_create_project_is_action(self) -> None:
        assert ToolName.CANVAS_CREATE_PROJECT.is_action is True

    # Scraping
    def test_adaptive_scrape_is_network(self) -> None:
        assert ToolName.ADAPTIVE_SCRAPE.is_network is True

    def test_adaptive_scrape_is_action(self) -> None:
        assert ToolName.ADAPTIVE_SCRAPE.is_action is True

    # Scheduling
    def test_agent_schedule_task_is_action(self) -> None:
        assert ToolName.AGENT_SCHEDULE_TASK.is_action is True

    def test_agent_list_scheduled_tasks_is_read_only(self) -> None:
        assert ToolName.AGENT_LIST_SCHEDULED_TASKS.is_read_only is True

    # Knowledge base
    def test_kb_list_is_read_only(self) -> None:
        assert ToolName.KB_LIST.is_read_only is True

    # Skill
    def test_skill_create_is_action(self) -> None:
        assert ToolName.SKILL_CREATE.is_action is True

    def test_skill_list_user_is_read_only(self) -> None:
        assert ToolName.SKILL_LIST_USER.is_read_only is True

    # Git
    def test_git_log_is_read_only(self) -> None:
        assert ToolName.GIT_LOG.is_read_only is True

    def test_git_diff_is_read_only(self) -> None:
        assert ToolName.GIT_DIFF.is_read_only is True

    # Scratchpad parallel safety
    def test_scratchpad_write_is_safe_parallel(self) -> None:
        assert ToolName.SCRATCHPAD_WRITE.is_safe_parallel is True
