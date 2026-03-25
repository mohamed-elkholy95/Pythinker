"""Tests for RequestContext and ContextVar-based request context propagation.

Covers:
- RequestContext defaults and field assignment
- to_log_extra (only non-None/non-empty fields included)
- to_dict (all fields present)
- get_request_context default behaviour (returns stub when unset)
- set_request_context / get_request_context round-trip
- reset_request_context restores previous state
- request_context_scope context manager (enter, yield, exit)
- Convenience accessors: get_request_id, get_session_id, get_user_id, get_agent_id
- Mutating helpers: set_session_id, set_user_id, set_agent_id
- add_context_attribute
- Nested request_context_scope scopes
"""

import asyncio
from contextvars import copy_context

import pytest

from app.infrastructure.observability.context import (
    RequestContext,
    _request_context,
    add_context_attribute,
    get_agent_id,
    get_request_context,
    get_request_id,
    get_session_id,
    get_user_id,
    request_context_scope,
    reset_request_context,
    set_agent_id,
    set_request_context,
    set_session_id,
    set_user_id,
)

# ---------------------------------------------------------------------------
# Fixture: reset the ContextVar before every test so tests are fully isolated
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_context_var():
    """Reset _request_context to None before and after every test."""
    token = _request_context.set(None)
    yield
    _request_context.reset(token)


# ---------------------------------------------------------------------------
# RequestContext defaults
# ---------------------------------------------------------------------------


class TestRequestContextDefaults:
    def test_request_id_defaults_to_empty_string(self):
        ctx = RequestContext()
        assert ctx.request_id == ""

    def test_optional_fields_default_to_none(self):
        ctx = RequestContext()
        assert ctx.session_id is None
        assert ctx.user_id is None
        assert ctx.agent_id is None
        assert ctx.trace_id is None
        assert ctx.span_id is None
        assert ctx.client_ip is None
        assert ctx.user_agent is None
        assert ctx.path is None
        assert ctx.method is None

    def test_start_time_ms_defaults_to_zero(self):
        ctx = RequestContext()
        assert ctx.start_time_ms == 0.0

    def test_attributes_defaults_to_empty_dict(self):
        ctx = RequestContext()
        assert ctx.attributes == {}

    def test_attributes_are_not_shared_between_instances(self):
        ctx1 = RequestContext()
        ctx2 = RequestContext()
        ctx1.attributes["key"] = "value"
        assert "key" not in ctx2.attributes

    def test_explicit_field_assignment(self):
        ctx = RequestContext(
            request_id="req-1",
            session_id="sess-2",
            user_id="usr-3",
            agent_id="agt-4",
            trace_id="trc-5",
            span_id="spn-6",
            client_ip="127.0.0.1",
            user_agent="TestAgent/1.0",
            path="/api/test",
            method="POST",
            start_time_ms=1_700_000_000_000.0,
        )
        assert ctx.request_id == "req-1"
        assert ctx.session_id == "sess-2"
        assert ctx.user_id == "usr-3"
        assert ctx.agent_id == "agt-4"
        assert ctx.trace_id == "trc-5"
        assert ctx.span_id == "spn-6"
        assert ctx.client_ip == "127.0.0.1"
        assert ctx.user_agent == "TestAgent/1.0"
        assert ctx.path == "/api/test"
        assert ctx.method == "POST"
        assert ctx.start_time_ms == 1_700_000_000_000.0


# ---------------------------------------------------------------------------
# to_log_extra — only non-None, non-empty fields
# ---------------------------------------------------------------------------


class TestToLogExtra:
    def test_always_contains_request_id(self):
        ctx = RequestContext(request_id="abc")
        extra = ctx.to_log_extra()
        assert "request_id" in extra
        assert extra["request_id"] == "abc"

    def test_omits_none_optional_fields(self):
        ctx = RequestContext(request_id="abc")
        extra = ctx.to_log_extra()
        for field in ("session_id", "user_id", "agent_id", "trace_id", "span_id", "path", "method"):
            assert field not in extra, f"{field} should be absent when None"

    def test_includes_session_id_when_set(self):
        ctx = RequestContext(request_id="abc", session_id="sess-42")
        extra = ctx.to_log_extra()
        assert extra["session_id"] == "sess-42"

    def test_includes_user_id_when_set(self):
        ctx = RequestContext(request_id="abc", user_id="usr-7")
        extra = ctx.to_log_extra()
        assert extra["user_id"] == "usr-7"

    def test_includes_agent_id_when_set(self):
        ctx = RequestContext(request_id="abc", agent_id="agt-9")
        extra = ctx.to_log_extra()
        assert extra["agent_id"] == "agt-9"

    def test_includes_trace_and_span_ids_when_set(self):
        ctx = RequestContext(request_id="abc", trace_id="trc-1", span_id="spn-2")
        extra = ctx.to_log_extra()
        assert extra["trace_id"] == "trc-1"
        assert extra["span_id"] == "spn-2"

    def test_includes_path_and_method_when_set(self):
        ctx = RequestContext(request_id="abc", path="/ping", method="GET")
        extra = ctx.to_log_extra()
        assert extra["path"] == "/ping"
        assert extra["method"] == "GET"

    def test_all_optional_fields_present_when_all_set(self):
        ctx = RequestContext(
            request_id="r",
            session_id="s",
            user_id="u",
            agent_id="a",
            trace_id="t",
            span_id="sp",
            path="/x",
            method="DELETE",
        )
        extra = ctx.to_log_extra()
        assert set(extra.keys()) == {
            "request_id",
            "session_id",
            "user_id",
            "agent_id",
            "trace_id",
            "span_id",
            "path",
            "method",
        }

    def test_does_not_include_client_ip_or_user_agent(self):
        ctx = RequestContext(request_id="r", client_ip="1.2.3.4", user_agent="UA/1")
        extra = ctx.to_log_extra()
        assert "client_ip" not in extra
        assert "user_agent" not in extra


# ---------------------------------------------------------------------------
# to_dict — all fields always present
# ---------------------------------------------------------------------------


class TestToDict:
    def test_contains_all_keys(self):
        ctx = RequestContext()
        d = ctx.to_dict()
        expected_keys = {
            "request_id",
            "session_id",
            "user_id",
            "agent_id",
            "trace_id",
            "span_id",
            "client_ip",
            "user_agent",
            "path",
            "method",
            "start_time_ms",
            "attributes",
        }
        assert set(d.keys()) == expected_keys

    def test_none_values_are_present(self):
        ctx = RequestContext(request_id="r")
        d = ctx.to_dict()
        assert d["session_id"] is None
        assert d["user_id"] is None
        assert d["agent_id"] is None

    def test_values_match_instance_fields(self):
        ctx = RequestContext(
            request_id="req",
            session_id="sess",
            user_id="usr",
            agent_id="agt",
            path="/p",
            method="PUT",
            start_time_ms=42.0,
            attributes={"foo": "bar"},
        )
        d = ctx.to_dict()
        assert d["request_id"] == "req"
        assert d["session_id"] == "sess"
        assert d["user_id"] == "usr"
        assert d["agent_id"] == "agt"
        assert d["path"] == "/p"
        assert d["method"] == "PUT"
        assert d["start_time_ms"] == 42.0
        assert d["attributes"] == {"foo": "bar"}


# ---------------------------------------------------------------------------
# get_request_context — default when ContextVar is unset
# ---------------------------------------------------------------------------


class TestGetRequestContextDefault:
    def test_returns_request_context_instance(self):
        ctx = get_request_context()
        assert isinstance(ctx, RequestContext)

    def test_default_request_id_is_eight_chars(self):
        ctx = get_request_context()
        # Falls back to str(uuid4())[:8]
        assert len(ctx.request_id) == 8

    def test_default_context_has_no_session_or_user(self):
        ctx = get_request_context()
        assert ctx.session_id is None
        assert ctx.user_id is None
        assert ctx.agent_id is None

    def test_each_default_call_produces_unique_request_id(self):
        ids = {get_request_context().request_id for _ in range(20)}
        # With 8-hex chars and UUID4 entropy, collisions are astronomically unlikely
        assert len(ids) > 1


# ---------------------------------------------------------------------------
# set_request_context / get_request_context round-trip
# ---------------------------------------------------------------------------


class TestSetGetRoundTrip:
    def test_set_context_is_returned_by_get(self):
        ctx = RequestContext(request_id="fixed-id", session_id="sess-123")
        token = set_request_context(ctx)
        try:
            retrieved = get_request_context()
            assert retrieved is ctx
            assert retrieved.request_id == "fixed-id"
            assert retrieved.session_id == "sess-123"
        finally:
            reset_request_context(token)

    def test_set_returns_token(self):
        from contextvars import Token

        ctx = RequestContext(request_id="tok-test")
        token = set_request_context(ctx)
        assert isinstance(token, Token)
        reset_request_context(token)


# ---------------------------------------------------------------------------
# reset_request_context — restores previous state
# ---------------------------------------------------------------------------


class TestResetRequestContext:
    def test_reset_restores_none(self):
        ctx = RequestContext(request_id="before-reset")
        token = set_request_context(ctx)
        reset_request_context(token)
        # After reset, ContextVar is None — get_request_context() returns fallback
        assert _request_context.get() is None

    def test_reset_restores_previous_value(self):
        first = RequestContext(request_id="first")
        second = RequestContext(request_id="second")

        token1 = set_request_context(first)
        token2 = set_request_context(second)

        assert get_request_context().request_id == "second"

        reset_request_context(token2)
        assert get_request_context().request_id == "first"

        reset_request_context(token1)
        assert _request_context.get() is None


# ---------------------------------------------------------------------------
# request_context_scope context manager
# ---------------------------------------------------------------------------


class TestRequestContextScope:
    def test_context_is_available_inside_scope(self):
        with request_context_scope(request_id="scope-id", session_id="s1") as ctx:
            assert ctx.request_id == "scope-id"
            assert ctx.session_id == "s1"
            retrieved = get_request_context()
            assert retrieved is ctx

    def test_context_is_cleared_after_scope(self):
        with request_context_scope(request_id="temp"):
            pass
        assert _request_context.get() is None

    def test_auto_generates_request_id_when_none(self):
        with request_context_scope() as ctx:
            assert len(ctx.request_id) == 8

    def test_start_time_ms_is_set(self):
        with request_context_scope(request_id="ts-test") as ctx:
            assert ctx.start_time_ms > 0.0

    def test_scope_yields_the_request_context_instance(self):
        with request_context_scope(request_id="yield-test") as ctx:
            assert isinstance(ctx, RequestContext)

    def test_context_cleared_even_on_exception(self):
        try:
            with request_context_scope(request_id="exc-test"):
                raise ValueError("deliberate")
        except ValueError:
            pass
        assert _request_context.get() is None

    def test_nested_scopes_shadow_outer(self):
        with request_context_scope(request_id="outer", session_id="outer-sess") as outer:
            assert get_request_context().request_id == "outer"

            with request_context_scope(request_id="inner", session_id="inner-sess") as inner:
                assert get_request_context().request_id == "inner"
                assert inner.session_id == "inner-sess"

            # Outer is restored after inner scope exits
            assert get_request_context().request_id == "outer"
            assert get_request_context() is outer

    def test_deeply_nested_scopes_restore_in_order(self):
        with request_context_scope(request_id="L1") as l1:
            with request_context_scope(request_id="L2") as l2:
                with request_context_scope(request_id="L3") as l3:
                    assert get_request_context() is l3
                assert get_request_context() is l2
            assert get_request_context() is l1


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


class TestConvenienceAccessors:
    def test_get_request_id_returns_request_id(self):
        with request_context_scope(request_id="rid-42"):
            assert get_request_id() == "rid-42"

    def test_get_session_id_returns_none_when_unset(self):
        with request_context_scope(request_id="r"):
            assert get_session_id() is None

    def test_get_session_id_returns_value_when_set(self):
        with request_context_scope(request_id="r", session_id="sess-99"):
            assert get_session_id() == "sess-99"

    def test_get_user_id_returns_none_when_unset(self):
        with request_context_scope(request_id="r"):
            assert get_user_id() is None

    def test_get_user_id_returns_value_when_set(self):
        with request_context_scope(request_id="r", user_id="usr-77"):
            assert get_user_id() == "usr-77"

    def test_get_agent_id_returns_none_when_unset(self):
        with request_context_scope(request_id="r"):
            assert get_agent_id() is None

    def test_get_agent_id_returns_value_when_set(self):
        with request_context_scope(request_id="r", agent_id="agt-55"):
            assert get_agent_id() == "agt-55"

    def test_accessors_return_defaults_when_no_context_set(self):
        # ContextVar is None; accessors fall through to the fallback context
        rid = get_request_id()
        assert len(rid) == 8  # auto-generated fallback
        assert get_session_id() is None
        assert get_user_id() is None
        assert get_agent_id() is None


# ---------------------------------------------------------------------------
# Mutating helpers: set_session_id, set_user_id, set_agent_id
# ---------------------------------------------------------------------------


class TestMutatingHelpers:
    def test_set_session_id_updates_context(self):
        with request_context_scope(request_id="r") as ctx:
            assert ctx.session_id is None
            set_session_id("mutated-sess")
            assert ctx.session_id == "mutated-sess"
            assert get_session_id() == "mutated-sess"

    def test_set_user_id_updates_context(self):
        with request_context_scope(request_id="r") as ctx:
            set_user_id("mutated-usr")
            assert ctx.user_id == "mutated-usr"
            assert get_user_id() == "mutated-usr"

    def test_set_agent_id_updates_context(self):
        with request_context_scope(request_id="r") as ctx:
            set_agent_id("mutated-agt")
            assert ctx.agent_id == "mutated-agt"
            assert get_agent_id() == "mutated-agt"

    def test_set_session_id_noop_when_no_context(self):
        # No context set — helpers must not raise
        set_session_id("orphan-sess")
        assert _request_context.get() is None

    def test_set_user_id_noop_when_no_context(self):
        set_user_id("orphan-usr")
        assert _request_context.get() is None

    def test_set_agent_id_noop_when_no_context(self):
        set_agent_id("orphan-agt")
        assert _request_context.get() is None


# ---------------------------------------------------------------------------
# add_context_attribute
# ---------------------------------------------------------------------------


class TestAddContextAttribute:
    def test_adds_attribute_to_current_context(self):
        with request_context_scope(request_id="r") as ctx:
            add_context_attribute("env", "production")
            assert ctx.attributes["env"] == "production"

    def test_multiple_attributes_accumulate(self):
        with request_context_scope(request_id="r") as ctx:
            add_context_attribute("k1", "v1")
            add_context_attribute("k2", 99)
            assert ctx.attributes == {"k1": "v1", "k2": 99}

    def test_overwrites_existing_attribute_key(self):
        with request_context_scope(request_id="r") as ctx:
            add_context_attribute("key", "old")
            add_context_attribute("key", "new")
            assert ctx.attributes["key"] == "new"

    def test_noop_when_no_context_set(self):
        # Must not raise when ContextVar is None
        add_context_attribute("ghost", "value")
        assert _request_context.get() is None

    def test_attribute_values_can_be_any_type(self):
        with request_context_scope(request_id="r") as ctx:
            add_context_attribute("list_val", [1, 2, 3])
            add_context_attribute("dict_val", {"nested": True})
            add_context_attribute("int_val", 42)
            assert ctx.attributes["list_val"] == [1, 2, 3]
            assert ctx.attributes["dict_val"] == {"nested": True}
            assert ctx.attributes["int_val"] == 42


# ---------------------------------------------------------------------------
# Async isolation: context is isolated per async task
# ---------------------------------------------------------------------------


class TestAsyncContextIsolation:
    def test_context_does_not_leak_between_asyncio_tasks(self):
        """Each asyncio task gets its own copy of the ContextVar."""
        results: dict[str, str] = {}

        async def worker(name: str, request_id: str) -> None:
            with request_context_scope(request_id=request_id):
                await asyncio.sleep(0)
                results[name] = get_request_id()

        async def run():
            await asyncio.gather(
                worker("a", "id-for-a"),
                worker("b", "id-for-b"),
            )

        asyncio.run(run())
        assert results["a"] == "id-for-a"
        assert results["b"] == "id-for-b"

    def test_copy_context_inherits_parent_context(self):
        """copy_context() snapshot captures the current ContextVar value."""
        with request_context_scope(request_id="parent-id"):
            snapshot = copy_context()

        captured: list[str] = []

        def read_in_snapshot():
            captured.append(get_request_id())

        snapshot.run(read_in_snapshot)
        assert captured == ["parent-id"]
