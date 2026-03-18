"""Tests for hardened sandbox image policy.

Verify runtime stage uses non-root user, tini init, and reference packages.
Requires: docker run access and image pythinker-sandbox:hardened built locally.
Skip if Docker unavailable or image not found.
"""

import subprocess
import sys

import pytest

IMAGE = "pythinker-sandbox:hardened"


def _image_exists() -> bool:
    """Check if image exists locally."""
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _docker_run(cmd: list[str], image: str = IMAGE) -> tuple[int, str]:
    """Run command in image, return (exitcode, output)."""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--platform", "linux/amd64", image] + cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode, result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, str(e)


@pytest.mark.skipif(
    sys.platform != "linux" and sys.platform != "darwin",
    reason="Docker image tests run on Unix",
)
@pytest.mark.skipif(
    not _image_exists(),
    reason=f"Image {IMAGE} not built; run: docker build -t {IMAGE} ./sandbox",
)
class TestImagePolicy:
    """Hardened image policy checks."""

    def test_runs_as_ubuntu(self) -> None:
        """Runtime uses non-root user."""
        code, out = _docker_run(["whoami"])
        assert code == 0, out
        assert "ubuntu" in out.strip()

    def test_tini_present(self) -> None:
        """tini binary exists at /usr/bin/tini."""
        code, out = _docker_run(["test", "-f", "/usr/bin/tini"])
        assert code == 0, out

    def test_no_nopasswd_sudoers(self) -> None:
        """No NOPASSWD:ALL in sudoers."""
        code, out = _docker_run(
            ["bash", "-c", "cat /etc/sudoers.d/ubuntu 2>/dev/null || true"]
        )
        assert "NOPASSWD" not in out

    def test_dev_tools_absent(self) -> None:
        """Build-only tools absent from runtime."""
        code, out = _docker_run(
            [
                "bash",
                "-c",
                "which black flake8 pytest eslint jest yarn 2>/dev/null | wc -l",
            ]
        )
        assert code == 0, out
        assert out.strip() == "0"

    def test_reference_packages_present(self) -> None:
        """Key reference packages available."""
        code, out = _docker_run(
            [
                "bash",
                "-c",
                "dot -V 2>&1 && mysql --version 2>&1 && pdftotext -v 2>&1 | head -1",
            ]
        )
        assert code == 0, out
