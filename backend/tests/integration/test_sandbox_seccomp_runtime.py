"""Integration tests for sandbox seccomp profile compatibility.

Verifies shell, file, and browser operations succeed under the seccomp profile.
Requires a running sandbox at SANDBOX_ADDRESS (e.g. localhost:8083 for dev).
Skips if sandbox unreachable.
"""

import os
import sys

import httpx
import pytest

pytestmark = [pytest.mark.integration]

# Sandbox API base URL - from env or dev default
SANDBOX_URL = os.environ.get("SANDBOX_TEST_URL", "http://localhost:8083")
SANDBOX_SECRET = os.environ.get("SANDBOX_TEST_SECRET") or os.environ.get("SANDBOX_API_SECRET")


def _sandbox_auth_headers() -> dict[str, str]:
    """Build auth headers for sandbox API requests when a secret is configured."""
    if not SANDBOX_SECRET:
        return {}
    return {"x-sandbox-secret": SANDBOX_SECRET}


def _post_json(client: httpx.Client, path: str, payload: dict[str, str]) -> httpx.Response:
    """Post JSON to sandbox API, skipping when auth is required but credentials are missing."""
    response = client.post(f"{SANDBOX_URL}{path}", json=payload, headers=_sandbox_auth_headers())
    if response.status_code == 403 and not SANDBOX_SECRET:
        pytest.skip(
            "Sandbox API secret is enabled. Set SANDBOX_TEST_SECRET or SANDBOX_API_SECRET "
            "to run seccomp runtime integration tests."
        )
    return response


def _sandbox_reachable() -> bool:
    """Check if sandbox API is reachable."""
    try:
        r = httpx.get(f"{SANDBOX_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture
def session_id() -> str:
    """Create a test session for shell/file ops."""
    if not _sandbox_reachable():
        pytest.skip(f"Sandbox not reachable at {SANDBOX_URL}")
    with httpx.Client(timeout=10.0) as client:
        r = _post_json(
            client,
            "/api/v1/shell/exec",
            {"id": "seccomp-test", "exec_dir": "/tmp", "command": "echo ok"},
        )
        r.raise_for_status()
    return "seccomp-test"


@pytest.mark.skipif(not _sandbox_reachable(), reason="Sandbox not reachable")
class TestSeccompShellCompatibility:
    """Basic shell commands must pass under seccomp."""

    def test_ls(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = _post_json(
                client,
                "/api/v1/shell/exec",
                {"id": "seccomp-ls", "exec_dir": "/tmp", "command": "ls -la /tmp"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True

    def test_python3(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = _post_json(
                client,
                "/api/v1/shell/exec",
                {"id": "seccomp-py", "exec_dir": "/tmp", "command": "python3 -c 'print(1+1)'"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert "2" in str(data.get("data", ""))

    def test_node(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = _post_json(
                client,
                "/api/v1/shell/exec",
                {"id": "seccomp-node", "exec_dir": "/tmp", "command": "node -e 'console.log(1+1)'"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True


@pytest.mark.skipif(not _sandbox_reachable(), reason="Sandbox not reachable")
class TestSeccompFileCompatibility:
    """File operations must pass under seccomp."""

    def test_file_write_read(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            wr = _post_json(
                client,
                "/api/v1/file/write",
                {"file": "/tmp/seccomp_test.txt", "content": "hello"},
            )
            assert wr.status_code == 200
            rd = _post_json(client, "/api/v1/file/read", {"file": "/tmp/seccomp_test.txt"})
        assert rd.status_code == 200
        assert rd.json().get("success") is True
        data = rd.json().get("data") or {}
        assert "hello" in str(data.get("content", data))


@pytest.mark.skipif(
    sys.platform != "linux" and sys.platform != "darwin",
    reason="Docker required",
)
def test_dangerous_syscalls_blocked_in_container() -> None:
    """mount/reboot etc. should be blocked by seccomp (container-level check).

    When running inside the sandbox container, unprivileged mount fails.
    This is a sanity check - we run a command that would need mount.
    """
    # Try to run a container with our seccomp profile and ensure mount is blocked
    # For now we skip - would need docker-in-docker or specific test harness
    pytest.skip("Requires running command inside sandbox container; covered by e2e")
