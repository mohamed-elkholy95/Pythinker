"""AuthService Redis counter behavior tests."""

import pytest

from app.application.services import auth_service as auth_service_module
from app.application.services.auth_service import AuthService


class _Settings:
    account_lockout_enabled = True
    account_lockout_reset_minutes = 5


class _DisabledSettings:
    account_lockout_enabled = False
    account_lockout_reset_minutes = 5


class _FakeRedisClient:
    def __init__(self):
        self.script_text: str | None = None
        self.called_keys: list[str] = []
        self.called_args: list[int] = []
        self.incr_calls: list[str] = []
        self.expire_calls: list[tuple[str, int]] = []
        self._incr_value = 3

    def register_script(self, script: str):
        self.script_text = script

        async def _execute(*, keys: list[str], args: list[int], client=None) -> int:
            self.called_keys = keys
            self.called_args = args
            return 3

        return _execute

    async def incr(self, key: str) -> int:
        self.incr_calls.append(key)
        return self._incr_value

    async def expire(self, key: str, seconds: int) -> bool:
        self.expire_calls.append((key, seconds))
        return True


class _FakeRedisWrapper:
    def __init__(self, client: _FakeRedisClient, fail_execute_with_retry: bool = False):
        self.client = client
        self.fail_execute_with_retry = fail_execute_with_retry

    async def initialize(self) -> None:
        return None

    async def execute_with_retry(self, operation, *args, **kwargs):
        if self.fail_execute_with_retry:
            raise RuntimeError("script execution failed")
        kwargs.pop("operation_name", None)
        return await operation(*args, **kwargs)

    async def call(self, method_name: str, *args, **kwargs):
        method = getattr(self.client, method_name)
        return await method(*args, **kwargs)


class _UserRepositoryStub:
    async def email_exists(self, email: str) -> bool:  # pragma: no cover - not used in these tests
        return False


class _TokenServiceStub:
    pass


@pytest.mark.asyncio
async def test_increment_failed_attempts_uses_atomic_counter_script(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(auth_service_module, "get_redis", lambda: _FakeRedisWrapper(client))

    service = AuthService(_UserRepositoryStub(), _TokenServiceStub())
    attempts = await service._increment_failed_attempts("User@Example.com")

    assert attempts == 3
    assert client.script_text is not None
    assert "INCR" in client.script_text
    assert "EXPIRE" in client.script_text
    assert client.called_keys == ["auth:failed_attempts:user@example.com"]
    assert client.called_args == [300]


@pytest.mark.asyncio
async def test_increment_failed_attempts_short_circuits_when_lockout_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: _DisabledSettings())
    service = AuthService(_UserRepositoryStub(), _TokenServiceStub())

    attempts = await service._increment_failed_attempts("user@example.com")

    assert attempts == 0


@pytest.mark.asyncio
async def test_increment_failed_attempts_falls_back_when_script_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeRedisClient()
    client._incr_value = 1
    wrapper = _FakeRedisWrapper(client, fail_execute_with_retry=True)
    monkeypatch.setattr(auth_service_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(auth_service_module, "get_redis", lambda: wrapper)

    service = AuthService(_UserRepositoryStub(), _TokenServiceStub())
    attempts = await service._increment_failed_attempts("User@Example.com")

    assert attempts == 1
    assert client.incr_calls == ["auth:failed_attempts:user@example.com"]
    assert client.expire_calls == [("auth:failed_attempts:user@example.com", 300)]
