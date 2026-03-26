"""Tests for MCP data models, dataclasses, and pure logic.

Covers all testable units that do NOT require an active MCP server connection:
- MCPTransport enum (mcp_config)
- MCPServerConfig Pydantic model + validators (mcp_config)
- MCPConfig Pydantic model (mcp_config)
- ResourceType enum (mcp_resource)
- MCPResource Pydantic model (mcp_resource)
- MCPResourceContent model + properties (mcp_resource)
- ResourceTemplate model (mcp_resource)
- ResourceSubscription model (mcp_resource)
- ResourceListResult model (mcp_resource)
- ResourceReadResult model (mcp_resource)
- ServerHealth dataclass + methods (mcp)
- CachedToolSchema dataclass + is_expired (mcp)
- ToolUsageStats dataclass + properties + record_call (mcp)
- MCPClientManager._matches_template (mcp)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.domain.models.mcp_config import MCPConfig, MCPServerConfig, MCPTransport
from app.domain.models.mcp_resource import (
    MCPResource,
    MCPResourceContent,
    ResourceListResult,
    ResourceReadResult,
    ResourceSubscription,
    ResourceTemplate,
    ResourceType,
)
from app.domain.services.tools.mcp import (
    CachedToolSchema,
    MCPClientManager,
    ServerHealth,
    ToolUsageStats,
)

# ---------------------------------------------------------------------------
# MCPTransport enum
# ---------------------------------------------------------------------------


class TestMCPTransport:
    def test_values_are_string_enums(self) -> None:
        assert MCPTransport.STDIO == "stdio"
        assert MCPTransport.SSE == "sse"
        assert MCPTransport.STREAMABLE_HTTP == "streamable-http"

    def test_members_accessible_by_value(self) -> None:
        assert MCPTransport("stdio") is MCPTransport.STDIO
        assert MCPTransport("sse") is MCPTransport.SSE
        assert MCPTransport("streamable-http") is MCPTransport.STREAMABLE_HTTP

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            MCPTransport("websocket")

    def test_enum_count(self) -> None:
        assert len(MCPTransport) == 3


class TestMCPServerConfig:
    # --- stdio transport ---

    def test_valid_stdio_config(self) -> None:
        cfg = MCPServerConfig(transport=MCPTransport.STDIO, command="npx")
        assert cfg.transport == MCPTransport.STDIO
        assert cfg.command == "npx"
        assert cfg.enabled is True
        assert cfg.args is None
        assert cfg.env is None

    def test_stdio_with_args_and_env(self) -> None:
        cfg = MCPServerConfig(
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "server"],
            env={"DEBUG": "1"},
        )
        assert cfg.args == ["-m", "server"]
        assert cfg.env == {"DEBUG": "1"}

    def test_valid_sse_config(self) -> None:
        cfg = MCPServerConfig(transport=MCPTransport.SSE, url="http://localhost:8080/sse")
        assert cfg.transport == MCPTransport.SSE
        assert cfg.url == "http://localhost:8080/sse"
        assert cfg.command is None

    def test_valid_streamable_http_config(self) -> None:
        cfg = MCPServerConfig(
            transport=MCPTransport.STREAMABLE_HTTP,
            url="https://mcp.example.com/stream",
            headers={"Authorization": "Bearer token"},
        )
        assert cfg.transport == MCPTransport.STREAMABLE_HTTP
        assert cfg.headers == {"Authorization": "Bearer token"}

    def test_enabled_defaults_to_true(self) -> None:
        cfg = MCPServerConfig(transport=MCPTransport.STDIO, command="node")
        assert cfg.enabled is True

    def test_enabled_can_be_set_false(self) -> None:
        cfg = MCPServerConfig(transport=MCPTransport.STDIO, command="node", enabled=False)
        assert cfg.enabled is False

    def test_description_optional(self) -> None:
        cfg = MCPServerConfig(
            transport=MCPTransport.STDIO,
            command="node",
            description="My server",
        )
        assert cfg.description == "My server"

    def test_extra_fields_allowed(self) -> None:
        cfg = MCPServerConfig(transport=MCPTransport.STDIO, command="node", custom_key="value")
        assert cfg.custom_key == "value"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# MCPConfig Pydantic model
# ---------------------------------------------------------------------------


class TestMCPConfig:
    def test_empty_config(self) -> None:
        cfg = MCPConfig()
        assert cfg.mcp_servers == {}

    def test_alias_mcp_servers_camel_case(self) -> None:
        raw = {
            "mcpServers": {
                "my-server": {
                    "transport": "stdio",
                    "command": "node",
                }
            }
        }
        cfg = MCPConfig.model_validate(raw)
        assert "my-server" in cfg.mcp_servers
        assert cfg.mcp_servers["my-server"].command == "node"

    def test_multiple_servers(self) -> None:
        cfg = MCPConfig(
            mcp_servers={
                "stdio-srv": MCPServerConfig(transport=MCPTransport.STDIO, command="node"),
                "http-srv": MCPServerConfig(transport=MCPTransport.SSE, url="http://localhost"),
            }
        )
        assert len(cfg.mcp_servers) == 2
        assert "stdio-srv" in cfg.mcp_servers
        assert "http-srv" in cfg.mcp_servers

    def test_model_dump_round_trip(self) -> None:
        cfg = MCPConfig(mcp_servers={"srv": MCPServerConfig(transport=MCPTransport.STDIO, command="npx")})
        dumped = cfg.model_dump()
        assert "mcp_servers" in dumped
        assert "srv" in dumped["mcp_servers"]

    def test_extra_fields_allowed(self) -> None:
        cfg = MCPConfig(mcp_servers={}, extra_setting="value")
        assert cfg.extra_setting == "value"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ResourceType enum
# ---------------------------------------------------------------------------


class TestResourceType:
    def test_values(self) -> None:
        assert ResourceType.TEXT == "text"
        assert ResourceType.BLOB == "blob"

    def test_from_value(self) -> None:
        assert ResourceType("text") is ResourceType.TEXT
        assert ResourceType("blob") is ResourceType.BLOB

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            ResourceType("json")

    def test_count(self) -> None:
        assert len(ResourceType) == 2


# ---------------------------------------------------------------------------
# MCPResource Pydantic model
# ---------------------------------------------------------------------------


class TestMCPResource:
    def test_minimal_fields(self) -> None:
        res = MCPResource(
            uri="file:///tmp/data.txt",
            name="data.txt",
            server_name="file-server",
        )
        assert res.uri == "file:///tmp/data.txt"
        assert res.name == "data.txt"
        assert res.server_name == "file-server"
        assert res.description is None
        assert res.mime_type is None
        assert res.size_bytes is None
        assert res.last_modified is None
        assert res.annotations == {}

    def test_full_fields(self) -> None:
        now = datetime.now(UTC)
        res = MCPResource(
            uri="db://users/42",
            name="User record",
            description="User profile data",
            mime_type="application/json",
            server_name="db-server",
            size_bytes=1024,
            last_modified=now,
            annotations={"owner": "admin"},
        )
        assert res.mime_type == "application/json"
        assert res.size_bytes == 1024
        assert res.annotations == {"owner": "admin"}

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            MCPResource(uri="file:///x", server_name="srv")  # missing name

    def test_annotations_default_is_empty_dict(self) -> None:
        res = MCPResource(uri="u", name="n", server_name="s")
        assert res.annotations == {}
        # Ensure it is a new object each time (not shared mutable default)
        res2 = MCPResource(uri="u2", name="n2", server_name="s")
        res.annotations["key"] = "val"
        assert res2.annotations == {}


# ---------------------------------------------------------------------------
# MCPResourceContent model + properties
# ---------------------------------------------------------------------------


class TestMCPResourceContent:
    def test_text_content(self) -> None:
        rc = MCPResourceContent(
            uri="file:///hello.txt",
            resource_type=ResourceType.TEXT,
            text="Hello World",
            mime_type="text/plain",
        )
        assert rc.is_text is True
        assert rc.content == "Hello World"

    def test_blob_content(self) -> None:
        payload = b"\x00\x01\x02"
        rc = MCPResourceContent(
            uri="file:///img.png",
            resource_type=ResourceType.BLOB,
            blob=payload,
            mime_type="image/png",
        )
        assert rc.is_text is False
        assert rc.content == payload

    def test_text_content_returns_none_when_no_text(self) -> None:
        rc = MCPResourceContent(
            uri="u",
            resource_type=ResourceType.TEXT,
            text=None,
        )
        assert rc.content is None

    def test_blob_content_returns_none_when_no_blob(self) -> None:
        rc = MCPResourceContent(
            uri="u",
            resource_type=ResourceType.BLOB,
            blob=None,
        )
        assert rc.content is None

    def test_defaults(self) -> None:
        rc = MCPResourceContent(uri="u", resource_type=ResourceType.TEXT)
        assert rc.text is None
        assert rc.blob is None
        assert rc.mime_type is None


# ---------------------------------------------------------------------------
# ResourceTemplate model
# ---------------------------------------------------------------------------


class TestResourceTemplate:
    def test_minimal(self) -> None:
        tmpl = ResourceTemplate(
            uri_template="file://{path}",
            name="File template",
            server_name="file-server",
        )
        assert tmpl.uri_template == "file://{path}"
        assert tmpl.name == "File template"
        assert tmpl.description is None
        assert tmpl.mime_type is None

    def test_full_fields(self) -> None:
        tmpl = ResourceTemplate(
            uri_template="db://users/{user_id}/posts/{post_id}",
            name="User post",
            description="A user's post record",
            mime_type="application/json",
            server_name="db-server",
        )
        assert tmpl.mime_type == "application/json"
        assert tmpl.description == "A user's post record"

    def test_missing_required_raises(self) -> None:
        with pytest.raises(ValidationError):
            ResourceTemplate(uri_template="t://{x}", server_name="s")  # missing name


# ---------------------------------------------------------------------------
# ResourceSubscription model
# ---------------------------------------------------------------------------


class TestResourceSubscription:
    def test_defaults(self) -> None:
        sub = ResourceSubscription(uri="file:///watch.log", server_name="file-server")
        assert sub.active is True
        assert isinstance(sub.subscribed_at, datetime)
        # Should be timezone-aware UTC
        assert sub.subscribed_at.tzinfo is not None

    def test_inactive_subscription(self) -> None:
        sub = ResourceSubscription(
            uri="file:///watch.log",
            server_name="file-server",
            active=False,
        )
        assert sub.active is False

    def test_subscribed_at_is_close_to_now(self) -> None:
        before = datetime.now(UTC)
        sub = ResourceSubscription(uri="u", server_name="s")
        after = datetime.now(UTC)
        assert before <= sub.subscribed_at <= after


# ---------------------------------------------------------------------------
# ResourceListResult model
# ---------------------------------------------------------------------------


class TestResourceListResult:
    def test_empty_defaults(self) -> None:
        result = ResourceListResult()
        assert result.resources == []
        assert result.templates == []
        assert result.total_count == 0
        assert result.servers_queried == []
        assert result.errors == {}

    def test_with_data(self) -> None:
        res = MCPResource(uri="u", name="n", server_name="srv")
        result = ResourceListResult(
            resources=[res],
            total_count=1,
            servers_queried=["srv"],
            errors={"other-srv": "timeout"},
        )
        assert len(result.resources) == 1
        assert result.total_count == 1
        assert result.errors == {"other-srv": "timeout"}


# ---------------------------------------------------------------------------
# ResourceReadResult model
# ---------------------------------------------------------------------------


class TestResourceReadResult:
    def test_successful_read(self) -> None:
        content = MCPResourceContent(
            uri="file:///hello.txt",
            resource_type=ResourceType.TEXT,
            text="data",
        )
        result = ResourceReadResult(
            success=True,
            content=content,
            read_time_ms=42.5,
        )
        assert result.success is True
        assert result.content is not None
        assert result.error is None

    def test_failed_read(self) -> None:
        result = ResourceReadResult(success=False, error="Connection refused")
        assert result.success is False
        assert result.content is None
        assert result.error == "Connection refused"

    def test_default_read_time(self) -> None:
        result = ResourceReadResult(success=True)
        assert result.read_time_ms == 0


# ---------------------------------------------------------------------------
# ServerHealth dataclass
# ---------------------------------------------------------------------------


class TestServerHealth:
    def test_defaults(self) -> None:
        h = ServerHealth(server_name="my-server")
        assert h.server_name == "my-server"
        assert h.healthy is True
        assert h.consecutive_failures == 0
        assert h.last_error is None
        assert h.tools_count == 0
        assert h.avg_response_time_ms == 0.0
        assert h.response_time_samples == []
        assert h.max_response_samples == 50
        assert h.success_count == 0
        assert h.failure_count == 0
        assert h.degraded is False
        assert h.priority == 100

    def test_success_rate_no_calls_returns_one(self) -> None:
        h = ServerHealth(server_name="srv")
        assert h.success_rate == 1.0

    def test_success_rate_all_success(self) -> None:
        h = ServerHealth(server_name="srv")
        h.success_count = 10
        h.failure_count = 0
        assert h.success_rate == 1.0

    def test_success_rate_mixed(self) -> None:
        h = ServerHealth(server_name="srv")
        h.success_count = 7
        h.failure_count = 3
        assert h.success_rate == pytest.approx(0.7)

    def test_record_response_time_single(self) -> None:
        h = ServerHealth(server_name="srv")
        h.record_response_time(200.0)
        assert h.response_time_samples == [200.0]
        assert h.avg_response_time_ms == pytest.approx(200.0)

    def test_record_response_time_average(self) -> None:
        h = ServerHealth(server_name="srv")
        h.record_response_time(100.0)
        h.record_response_time(300.0)
        assert h.avg_response_time_ms == pytest.approx(200.0)

    def test_record_response_time_caps_at_max_samples(self) -> None:
        h = ServerHealth(server_name="srv", max_response_samples=3)
        for i in range(5):
            h.record_response_time(float(i * 100))
        # Only last 3 values kept: 200, 300, 400
        assert len(h.response_time_samples) == 3
        assert h.response_time_samples == [200.0, 300.0, 400.0]

    def test_record_success_increments_count(self) -> None:
        h = ServerHealth(server_name="srv")
        h.record_success()
        assert h.success_count == 1
        h.record_success()
        assert h.success_count == 2

    def test_record_failure_increments_count(self) -> None:
        h = ServerHealth(server_name="srv")
        h.record_failure()
        assert h.failure_count == 1

    def test_degraded_when_success_rate_below_90(self) -> None:
        h = ServerHealth(server_name="srv")
        # 8 successes, 2 failures = 80% success rate
        for _ in range(8):
            h.record_success()
        for _ in range(2):
            h.record_failure()
        assert h.degraded is True

    def test_not_degraded_when_success_rate_at_90(self) -> None:
        h = ServerHealth(server_name="srv")
        for _ in range(9):
            h.record_success()
        h.record_failure()
        # 90% — exactly at threshold, not degraded
        assert h.degraded is False

    def test_priority_high_for_perfect_server(self) -> None:
        h = ServerHealth(server_name="srv")
        for _ in range(10):
            h.record_success()
        assert h.priority == 100

    def test_priority_reduced_for_slow_server(self) -> None:
        h = ServerHealth(server_name="srv")
        for _ in range(10):
            h.record_success()
        # Force a slow avg response time directly
        h.avg_response_time_ms = 3000.0
        # Recalculate priority manually
        h._update_reliability()
        # Penalty: (3000-2000)/100 = 10, so priority = 100 - 10 = 90
        assert h.priority == 90

    def test_priority_capped_at_zero_for_extremely_slow(self) -> None:
        h = ServerHealth(server_name="srv")
        for _ in range(10):
            h.record_success()
        h.avg_response_time_ms = 100_000.0  # absurdly slow
        h._update_reliability()
        assert h.priority == max(0, 100 - 30)  # penalty capped at 30

    def test_to_dict_keys(self) -> None:
        h = ServerHealth(server_name="srv")
        d = h.to_dict()
        expected_keys = {
            "server_name",
            "healthy",
            "degraded",
            "last_check",
            "last_error",
            "consecutive_failures",
            "tools_count",
            "avg_response_time_ms",
            "success_rate",
            "priority",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self) -> None:
        h = ServerHealth(server_name="test-srv", healthy=False, tools_count=5)
        h.last_error = "Connection refused"
        h.consecutive_failures = 2
        d = h.to_dict()
        assert d["server_name"] == "test-srv"
        assert d["healthy"] is False
        assert d["tools_count"] == 5
        assert d["last_error"] == "Connection refused"
        assert d["consecutive_failures"] == 2

    def test_to_dict_last_check_is_iso_string(self) -> None:
        h = ServerHealth(server_name="srv")
        d = h.to_dict()
        # Should be parseable ISO 8601
        parsed = datetime.fromisoformat(d["last_check"])
        assert isinstance(parsed, datetime)

    def test_to_dict_success_rate_is_percentage(self) -> None:
        h = ServerHealth(server_name="srv")
        h.success_count = 7
        h.failure_count = 3
        d = h.to_dict()
        assert d["success_rate"] == pytest.approx(70.0, abs=0.1)

    def test_update_reliability_no_op_when_no_calls(self) -> None:
        h = ServerHealth(server_name="srv")
        # Should not raise and should not change defaults
        h._update_reliability()
        assert h.degraded is False
        assert h.priority == 100


# ---------------------------------------------------------------------------
# CachedToolSchema dataclass
# ---------------------------------------------------------------------------


class TestCachedToolSchema:
    def test_not_expired_immediately(self) -> None:
        cache = CachedToolSchema(tools=[], ttl_seconds=300)
        assert cache.is_expired() is False

    def test_expired_when_past_ttl(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=400)
        cache = CachedToolSchema(tools=[], cached_at=past, ttl_seconds=300)
        assert cache.is_expired() is True

    def test_not_expired_just_before_ttl(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=299)
        cache = CachedToolSchema(tools=[], cached_at=past, ttl_seconds=300)
        assert cache.is_expired() is False

    def test_short_ttl_expired(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=2)
        cache = CachedToolSchema(tools=[], cached_at=past, ttl_seconds=1)
        assert cache.is_expired() is True

    def test_default_ttl_is_300(self) -> None:
        cache = CachedToolSchema(tools=[])
        assert cache.ttl_seconds == 300

    def test_tools_stored(self) -> None:
        mock_tool = MagicMock()
        mock_tool.name = "my_tool"
        cache = CachedToolSchema(tools=[mock_tool])
        assert len(cache.tools) == 1
        assert cache.tools[0].name == "my_tool"


# ---------------------------------------------------------------------------
# ToolUsageStats dataclass
# ---------------------------------------------------------------------------


class TestToolUsageStats:
    def test_defaults(self) -> None:
        stats = ToolUsageStats(tool_name="my_tool")
        assert stats.tool_name == "my_tool"
        assert stats.call_count == 0
        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.total_duration_ms == 0
        assert stats.last_used is None
        assert stats.min_duration_ms == float("inf")
        assert stats.max_duration_ms == 0
        assert stats.timeout_count == 0
        assert stats.last_error is None

    def test_avg_duration_no_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        assert stats.avg_duration_ms == 0

    def test_success_rate_no_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        assert stats.success_rate == 1.0

    def test_is_reliable_no_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        assert stats.is_reliable is True

    def test_record_call_success(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=True, duration_ms=100.0)
        assert stats.call_count == 1
        assert stats.success_count == 1
        assert stats.failure_count == 0
        assert stats.total_duration_ms == 100.0
        assert stats.min_duration_ms == 100.0
        assert stats.max_duration_ms == 100.0
        assert stats.last_error is None
        assert stats.last_used is not None

    def test_record_call_failure(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=False, duration_ms=50.0, error="Timeout")
        assert stats.failure_count == 1
        assert stats.success_count == 0
        assert stats.last_error == "Timeout"

    def test_record_call_timeout(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=False, duration_ms=120_000.0, timeout=True)
        assert stats.timeout_count == 1

    def test_record_call_no_timeout_by_default(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=True, duration_ms=10.0)
        assert stats.timeout_count == 0

    def test_avg_duration_multiple_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=True, duration_ms=100.0)
        stats.record_call(success=True, duration_ms=200.0)
        assert stats.avg_duration_ms == pytest.approx(150.0)

    def test_min_max_duration_tracking(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=True, duration_ms=500.0)
        stats.record_call(success=True, duration_ms=50.0)
        stats.record_call(success=True, duration_ms=300.0)
        assert stats.min_duration_ms == 50.0
        assert stats.max_duration_ms == 500.0

    def test_success_rate_all_success(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        for _ in range(5):
            stats.record_call(success=True, duration_ms=10.0)
        assert stats.success_rate == pytest.approx(1.0)

    def test_success_rate_mixed(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        for _ in range(8):
            stats.record_call(success=True, duration_ms=10.0)
        for _ in range(2):
            stats.record_call(success=False, duration_ms=10.0)
        assert stats.success_rate == pytest.approx(0.8)

    def test_is_reliable_below_threshold(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        for _ in range(8):
            stats.record_call(success=True, duration_ms=10.0)
        for _ in range(2):
            stats.record_call(success=False, duration_ms=10.0)
        assert stats.is_reliable is False

    def test_is_reliable_at_threshold(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        for _ in range(9):
            stats.record_call(success=True, duration_ms=10.0)
        stats.record_call(success=False, duration_ms=10.0)
        # 90% — exactly at threshold
        assert stats.is_reliable is True

    def test_last_used_updated_on_call(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        before = datetime.now(UTC)
        stats.record_call(success=True, duration_ms=1.0)
        after = datetime.now(UTC)
        assert stats.last_used is not None
        assert before <= stats.last_used <= after

    def test_to_dict_keys(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        d = stats.to_dict()
        expected = {
            "tool_name",
            "call_count",
            "success_count",
            "failure_count",
            "success_rate",
            "avg_duration_ms",
            "min_duration_ms",
            "max_duration_ms",
            "timeout_count",
            "last_used",
            "is_reliable",
        }
        assert set(d.keys()) == expected

    def test_to_dict_min_none_when_no_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        d = stats.to_dict()
        # min is float('inf') before any call — serialized as None
        assert d["min_duration_ms"] is None

    def test_to_dict_last_used_none_when_no_calls(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        d = stats.to_dict()
        assert d["last_used"] is None

    def test_to_dict_last_used_iso_after_call(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=True, duration_ms=5.0)
        d = stats.to_dict()
        assert d["last_used"] is not None
        parsed = datetime.fromisoformat(d["last_used"])
        assert isinstance(parsed, datetime)

    def test_to_dict_success_rate_is_percentage(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        for _ in range(3):
            stats.record_call(success=True, duration_ms=10.0)
        stats.record_call(success=False, duration_ms=10.0)
        d = stats.to_dict()
        assert d["success_rate"] == pytest.approx(75.0, abs=0.1)

    def test_multiple_errors_last_error_is_latest(self) -> None:
        stats = ToolUsageStats(tool_name="tool")
        stats.record_call(success=False, duration_ms=1.0, error="First error")
        stats.record_call(success=False, duration_ms=1.0, error="Second error")
        assert stats.last_error == "Second error"


# ---------------------------------------------------------------------------
# MCPClientManager._matches_template (pure URI-matching logic)
# ---------------------------------------------------------------------------


class TestMatchesTemplate:
    """Tests for MCPClientManager._matches_template without a server connection."""

    @pytest.fixture()
    def manager(self) -> MCPClientManager:
        # No config needed — _matches_template is pure
        return MCPClientManager(config=None)

    def test_multi_placeholder_match(self, manager: MCPClientManager) -> None:
        assert manager._matches_template("db://users/42/posts/7", "db://users/{user_id}/posts/{post_id}") is True

    def test_no_placeholder_exact_match(self, manager: MCPClientManager) -> None:
        assert manager._matches_template("static://resource", "static://resource") is True

    def test_no_match_different_scheme(self, manager: MCPClientManager) -> None:
        assert manager._matches_template("http://host/path", "file://{path}") is False

    def test_placeholder_does_not_match_slash(self, manager: MCPClientManager) -> None:
        # {placeholder} maps to [^/]+ — should not cross path segments
        assert manager._matches_template("db://users/42/extra/segment", "db://users/{user_id}") is False

    def test_empty_template_matches_empty_uri(self, manager: MCPClientManager) -> None:
        assert manager._matches_template("", "") is True

    def test_uri_prefix_not_matched_as_full(self, manager: MCPClientManager) -> None:
        # Pattern is anchored — prefix without full path should not match
        assert manager._matches_template("db://users/42/extra", "db://users/{user_id}") is False

    def test_partial_template_no_match(self, manager: MCPClientManager) -> None:
        assert manager._matches_template("db://users/", "db://users/{user_id}") is False

    def test_invalid_regex_in_template_returns_false(self, manager: MCPClientManager) -> None:
        # A template that generates an invalid regex should return False gracefully
        # Use a template with unbalanced brackets to trigger re.error
        assert manager._matches_template("some://uri", "some://[broken") is False
