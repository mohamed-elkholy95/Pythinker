"""Tests for DockerSandbox._normalize_address().

Ensures that SANDBOX_ADDRESS values containing scheme and/or port are
correctly stripped down to a bare hostname or IP for DNS resolution
and container naming.
"""

from __future__ import annotations

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


class TestNormalizeAddress:
    """Unit tests for _normalize_address static method."""

    def test_bare_hostname(self) -> None:
        assert DockerSandbox._normalize_address("sandbox") == "sandbox"

    def test_bare_ip(self) -> None:
        assert DockerSandbox._normalize_address("172.18.0.5") == "172.18.0.5"

    def test_http_scheme_with_port(self) -> None:
        assert DockerSandbox._normalize_address("http://sandbox:8080") == "sandbox"

    def test_https_scheme_with_port(self) -> None:
        assert DockerSandbox._normalize_address("https://sandbox:443") == "sandbox"

    def test_scheme_only(self) -> None:
        assert DockerSandbox._normalize_address("http://sandbox") == "sandbox"

    def test_port_only(self) -> None:
        assert DockerSandbox._normalize_address("sandbox:8080") == "sandbox"

    def test_case_insensitive_scheme(self) -> None:
        assert DockerSandbox._normalize_address("HTTP://Sandbox:8080") == "Sandbox"

    def test_ip_with_scheme_and_port(self) -> None:
        assert DockerSandbox._normalize_address("http://172.18.0.5:8080") == "172.18.0.5"

    def test_whitespace_stripped(self) -> None:
        assert DockerSandbox._normalize_address("  http://sandbox:8080  ") == "sandbox"

    def test_empty_string(self) -> None:
        assert DockerSandbox._normalize_address("") == ""

    def test_localhost(self) -> None:
        assert DockerSandbox._normalize_address("http://localhost:8080") == "localhost"
