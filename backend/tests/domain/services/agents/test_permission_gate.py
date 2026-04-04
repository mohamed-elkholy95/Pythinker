"""Tests for PermissionGateMiddleware and PermissionPolicy."""

from __future__ import annotations

import pytest

from app.domain.models.tool_permission import PermissionAction, PermissionPolicy, PermissionTier, ToolPermissionRule
from app.domain.services.agents.middleware import MiddlewareContext, MiddlewareSignal, ToolCallInfo
from app.domain.services.agents.middleware_adapters.permission_gate import PermissionGateMiddleware
from app.domain.services.tools.base import BaseTool, tool
from app.domain.services.tools.metadata_index import ToolMetadataIndex


def _ctx(active_tier: PermissionTier = PermissionTier.DANGER) -> MiddlewareContext:
    return MiddlewareContext(agent_id="agent-1", session_id="session-1", active_tier=active_tier)


def _call(name: str) -> ToolCallInfo:
    return ToolCallInfo(call_id="call-1", function_name=name, arguments={})


def _tool_index() -> ToolMetadataIndex:
    class PermissionTestTool(BaseTool):
        name = "permission_test"

        @tool(
            name="file_read",
            description="Read a file",
            parameters={},
            required=[],
            is_read_only=True,
            required_tier=PermissionTier.READ_ONLY,
        )
        async def file_read(self):
            pass

        @tool(
            name="file_write",
            description="Write a file",
            parameters={},
            required=[],
            required_tier=PermissionTier.WORKSPACE_WRITE,
        )
        async def file_write(self):
            pass

        @tool(
            name="shell_exec",
            description="Run a shell command",
            parameters={},
            required=[],
            required_tier=PermissionTier.DANGER,
        )
        async def shell_exec(self):
            pass

    return ToolMetadataIndex([PermissionTestTool()])


# ── ToolPermissionRule ──────────────────────────────────────────────────


class TestToolPermissionRule:
    def test_exact_match(self):
        rule = ToolPermissionRule("shell_exec", PermissionAction.DENY)
        assert rule.matches("shell_exec") is True
        assert rule.matches("shell_view") is False

    def test_glob_wildcard(self):
        rule = ToolPermissionRule("shell_*", PermissionAction.DENY)
        assert rule.matches("shell_exec") is True
        assert rule.matches("shell_view") is True
        assert rule.matches("file_read") is False

    def test_catch_all_wildcard(self):
        rule = ToolPermissionRule("*", PermissionAction.ALLOW)
        assert rule.matches("anything") is True
        assert rule.matches("file_write") is True


# ── PermissionPolicy ────────────────────────────────────────────────────


class TestPermissionPolicy:
    def test_empty_policy_allows_all(self):
        policy = PermissionPolicy()
        action, _ = policy.evaluate("shell_exec")
        assert action == PermissionAction.ALLOW

    def test_deny_rule_matched(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("shell_exec", PermissionAction.DENY, "no shell")])
        denied, reason = policy.is_denied("shell_exec")
        assert denied is True
        assert reason == "no shell"

    def test_allow_rule_matched(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("file_read", PermissionAction.ALLOW)])
        denied, _ = policy.is_denied("file_read")
        assert denied is False

    def test_first_rule_wins(self):
        policy = PermissionPolicy(
            rules=[
                ToolPermissionRule("shell_*", PermissionAction.DENY, "first"),
                ToolPermissionRule("shell_exec", PermissionAction.ALLOW, "second"),
            ]
        )
        denied, reason = policy.is_denied("shell_exec")
        assert denied is True
        assert reason == "first"

    def test_no_matching_rule_allows(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("rm", PermissionAction.DENY)])
        denied, _ = policy.is_denied("file_read")
        assert denied is False

    def test_glob_deny_with_allow_fallback(self):
        """Deny shell_* but allow everything else."""
        policy = PermissionPolicy(
            rules=[
                ToolPermissionRule("shell_*", PermissionAction.DENY, "shell blocked"),
                ToolPermissionRule("*", PermissionAction.ALLOW),
            ]
        )
        assert policy.is_denied("shell_exec")[0] is True
        assert policy.is_denied("file_read")[0] is False


# ── PermissionGateMiddleware ────────────────────────────────────────────


class TestPermissionGateMiddleware:
    @pytest.mark.asyncio
    async def test_no_policy_allows_all(self):
        mw = PermissionGateMiddleware(tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(), _call("shell_exec"))
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_denied_tool_returns_skip_tool(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("shell_exec", PermissionAction.DENY, "blocked")])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(), _call("shell_exec"))
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert "blocked" in (result.message or "")

    @pytest.mark.asyncio
    async def test_allowed_tool_returns_continue(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("shell_exec", PermissionAction.DENY)])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(), _call("file_read"))
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_glob_deny_blocks_matching_tools(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("shell_*", PermissionAction.DENY, "no shell tools")])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())

        result_exec = await mw.before_tool_call(_ctx(), _call("shell_exec"))
        result_view = await mw.before_tool_call(_ctx(), _call("shell_view"))
        result_file = await mw.before_tool_call(_ctx(), _call("file_read"))

        assert result_exec.signal == MiddlewareSignal.SKIP_TOOL
        assert result_view.signal == MiddlewareSignal.SKIP_TOOL
        assert result_file.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_skip_tool_metadata_includes_tool_name(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("rm", PermissionAction.DENY, "destructive")])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(), _call("rm"))
        assert result.metadata.get("tool") == "rm"
        assert result.metadata.get("blocked_by") == "permission_gate"

    @pytest.mark.asyncio
    async def test_deny_without_reason_uses_default_message(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("shell_exec", PermissionAction.DENY)])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(), _call("shell_exec"))
        assert result.message is not None
        assert "shell_exec" in result.message

    @pytest.mark.asyncio
    async def test_tier_blocks_when_active_tier_is_too_low(self):
        mw = PermissionGateMiddleware(tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(active_tier=PermissionTier.READ_ONLY), _call("shell_exec"))
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert result.metadata.get("blocked_by") == "permission_gate"
        assert result.metadata.get("required_tier") == PermissionTier.DANGER.as_str()
        assert result.metadata.get("active_tier") == PermissionTier.READ_ONLY.as_str()
        assert "danger-full-access" in (result.message or "")

    @pytest.mark.asyncio
    async def test_tier_allows_when_active_tier_meets_requirement(self):
        mw = PermissionGateMiddleware(tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(active_tier=PermissionTier.WORKSPACE_WRITE), _call("file_write"))
        assert result.signal == MiddlewareSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_policy_denial_wins_before_tier_check(self):
        policy = PermissionPolicy(rules=[ToolPermissionRule("file_read", PermissionAction.DENY, "blocked by policy")])
        mw = PermissionGateMiddleware(policy=policy, tool_metadata_index=_tool_index())
        result = await mw.before_tool_call(_ctx(active_tier=PermissionTier.DANGER), _call("file_read"))
        assert result.signal == MiddlewareSignal.SKIP_TOOL
        assert result.message == "blocked by policy"

    def test_middleware_name(self):
        mw = PermissionGateMiddleware()
        assert mw.name == "permission_gate"
