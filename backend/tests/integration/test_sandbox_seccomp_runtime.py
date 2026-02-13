"""Integration tests for sandbox seccomp profile compatibility.

Verifies shell, file, and browser operations succeed under the seccomp profile.
Requires a running sandbox at SANDBOX_ADDRESS (e.g. localhost:8083 for dev).
Skips if sandbox unreachable.
"""

import os
import sys

import httpx
import pytest

# Sandbox API base URL - from env or dev default
SANDBOX_URL = os.environ.get("SANDBOX_TEST_URL", "http://localhost:8083")


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
        r = client.post(
            f"{SANDBOX_URL}/api/v1/shell/exec",
            json={"id": "seccomp-test", "exec_dir": "/tmp", "command": "echo ok"},
        )
        r.raise_for_status()
    return "seccomp-test"


@pytest.mark.skipif(not _sandbox_reachable(), reason="Sandbox not reachable")
class TestSeccompShellCompatibility:
    """Basic shell commands must pass under seccomp."""

    def test_ls(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{SANDBOX_URL}/api/v1/shell/exec",
                json={"id": "seccomp-ls", "exec_dir": "/tmp", "command": "ls -la /tmp"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True

    def test_python3(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{SANDBOX_URL}/api/v1/shell/exec",
                json={"id": "seccomp-py", "exec_dir": "/tmp", "command": "python3 -c 'print(1+1)'"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert "2" in str(data.get("data", ""))

    def test_node(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{SANDBOX_URL}/api/v1/shell/exec",
                json={"id": "seccomp-node", "exec_dir": "/tmp", "command": "node -e 'console.log(1+1)'"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True


@pytest.mark.skipif(not _sandbox_reachable(), reason="Sandbox not reachable")
class TestSeccompFileCompatibility:
    """File operations must pass under seccomp."""

    def test_file_write_read(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            wr = client.post(
                f"{SANDBOX_URL}/api/v1/file/write",
                json={"file": "/tmp/seccomp_test.txt", "content": "hello"},
            )
            assert wr.status_code == 200
            rd = client.post(
                f"{SANDBOX_URL}/api/v1/file/read",
                json={"file": "/tmp/seccomp_test.txt"},
            )
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
