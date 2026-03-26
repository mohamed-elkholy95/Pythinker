"""Tests for ResourceManager lifecycle management."""

import pytest

from app.core.resource_manager import (
    ManagedResource,
    ResourceManager,
    ResourceState,
)


@pytest.fixture
def manager():
    return ResourceManager()


# ─────────────────────────────────────────────────────────────
# ManagedResource
# ─────────────────────────────────────────────────────────────


class TestManagedResource:
    async def test_shutdown_with_sync_handler(self):
        cleaned = []
        mr = ManagedResource(
            name="test",
            resource="value",
            cleanup_handler=lambda r: cleaned.append(r),
            state=ResourceState.ACTIVE,
        )
        result = await mr.shutdown()
        assert result is True
        assert mr.state == ResourceState.SHUTDOWN
        assert cleaned == ["value"]

    async def test_shutdown_with_async_handler(self):
        cleaned = []

        async def cleanup(r):
            cleaned.append(r)

        mr = ManagedResource(
            name="test",
            resource="async_val",
            cleanup_handler=cleanup,
            state=ResourceState.ACTIVE,
        )
        result = await mr.shutdown()
        assert result is True
        assert cleaned == ["async_val"]

    async def test_shutdown_no_handler(self):
        mr = ManagedResource(name="test", resource="val", state=ResourceState.ACTIVE)
        result = await mr.shutdown()
        assert result is True
        assert mr.state == ResourceState.SHUTDOWN

    async def test_shutdown_already_shutdown(self):
        mr = ManagedResource(name="test", resource="val", state=ResourceState.SHUTDOWN)
        result = await mr.shutdown()
        assert result is True

    async def test_shutdown_handler_error(self):
        def bad_cleanup(r):
            raise RuntimeError("cleanup failed")

        mr = ManagedResource(
            name="test",
            resource="val",
            cleanup_handler=bad_cleanup,
            state=ResourceState.ACTIVE,
        )
        result = await mr.shutdown()
        assert result is False
        assert mr.state == ResourceState.ERROR
        assert "cleanup failed" in mr.last_error

    async def test_shutdown_records_duration(self):
        mr = ManagedResource(name="test", resource="val", state=ResourceState.ACTIVE)
        await mr.shutdown()
        assert mr.shutdown_duration_ms >= 0


# ─────────────────────────────────────────────────────────────
# ResourceManager.register
# ─────────────────────────────────────────────────────────────


class TestRegister:
    async def test_register_basic(self, manager):
        mr = await manager.register("db", resource="connection")
        assert mr.name == "db"
        assert mr.state == ResourceState.ACTIVE
        assert manager.get("db") == "connection"

    async def test_register_with_priority(self, manager):
        mr = await manager.register("cache", resource="redis", priority=10)
        assert mr.priority == 10

    async def test_register_with_depends(self, manager):
        await manager.register("db", resource="pg")
        mr = await manager.register("cache", resource="redis", depends_on=["db"])
        assert mr.depends_on == ["db"]

    async def test_register_duplicate_raises(self, manager):
        await manager.register("db", resource="pg")
        with pytest.raises(ValueError, match="already registered"):
            await manager.register("db", resource="pg2")

    async def test_register_with_metadata(self, manager):
        mr = await manager.register("db", resource="pg", metadata={"version": "15"})
        assert mr.metadata == {"version": "15"}


# ─────────────────────────────────────────────────────────────
# ResourceManager.unregister
# ─────────────────────────────────────────────────────────────


class TestUnregister:
    async def test_unregister_with_cleanup(self, manager):
        cleaned = []
        await manager.register("db", resource="conn", cleanup_handler=lambda r: cleaned.append(r))
        result = await manager.unregister("db")
        assert result is True
        assert cleaned == ["conn"]
        assert manager.get("db") is None

    async def test_unregister_without_cleanup(self, manager):
        cleaned = []
        await manager.register("db", resource="conn", cleanup_handler=lambda r: cleaned.append(r))
        result = await manager.unregister("db", cleanup=False)
        assert result is True
        assert cleaned == []

    async def test_unregister_nonexistent(self, manager):
        result = await manager.unregister("nope")
        assert result is False


# ─────────────────────────────────────────────────────────────
# ResourceManager.get / get_managed
# ─────────────────────────────────────────────────────────────


class TestGet:
    async def test_get_existing(self, manager):
        await manager.register("db", resource="conn")
        assert manager.get("db") == "conn"

    async def test_get_nonexistent(self, manager):
        assert manager.get("missing") is None

    async def test_get_managed(self, manager):
        await manager.register("db", resource="conn")
        mr = manager.get_managed("db")
        assert isinstance(mr, ManagedResource)
        assert mr.name == "db"

    async def test_get_managed_nonexistent(self, manager):
        assert manager.get_managed("missing") is None


# ─────────────────────────────────────────────────────────────
# ResourceManager.shutdown_all
# ─────────────────────────────────────────────────────────────


class TestShutdownAll:
    async def test_shutdown_all_basic(self, manager):
        order = []
        await manager.register("a", resource="1", cleanup_handler=lambda r: order.append("a"))
        await manager.register("b", resource="2", cleanup_handler=lambda r: order.append("b"))
        results = await manager.shutdown_all()
        assert results["a"] is True
        assert results["b"] is True

    async def test_shutdown_empty(self, manager):
        results = await manager.shutdown_all()
        assert results == {}

    async def test_shutdown_partial_failure(self, manager):
        await manager.register("good", resource="1", cleanup_handler=lambda r: None)
        await manager.register(
            "bad", resource="2", cleanup_handler=lambda r: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        results = await manager.shutdown_all()
        assert results["good"] is True
        assert results["bad"] is False


# ─────────────────────────────────────────────────────────────
# ResourceManager.get_status / get_health
# ─────────────────────────────────────────────────────────────


class TestStatus:
    async def test_get_status(self, manager):
        await manager.register("db", resource="conn", priority=5)
        status = manager.get_status()
        assert status["total"] == 1
        assert status["is_shutting_down"] is False
        assert "db" in status["resources"]
        assert status["resources"]["db"]["state"] == "active"
        assert status["resources"]["db"]["priority"] == 5

    async def test_get_health_active(self, manager):
        await manager.register("db", resource="conn")
        health = manager.get_health()
        assert health["db"] == "healthy"

    async def test_get_health_after_error(self, manager):
        await manager.register(
            "bad", resource="x", cleanup_handler=lambda r: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        mr = manager.get_managed("bad")
        mr.state = ResourceState.ERROR
        health = manager.get_health()
        assert health["bad"] == "error"

    def test_empty_status(self, manager):
        status = manager.get_status()
        assert status["total"] == 0

    def test_empty_health(self, manager):
        assert manager.get_health() == {}
