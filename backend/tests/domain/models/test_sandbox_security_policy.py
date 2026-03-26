"""Tests for app.domain.models.sandbox_security_policy — Docker sandbox security.

Covers: SandboxSecurityPolicy defaults, field validators (cap_drop, cap_add_allowlist,
seccomp_profile_path).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.sandbox_security_policy import SandboxSecurityPolicy


class TestDefaults:
    """Test default values are secure."""

    def test_cap_drop_defaults_to_all(self):
        policy = SandboxSecurityPolicy()
        assert policy.cap_drop == ["ALL"]

    def test_cap_add_allowlist_defaults(self):
        policy = SandboxSecurityPolicy()
        assert set(policy.cap_add_allowlist) == {"CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE"}

    def test_require_no_new_privileges_default(self):
        policy = SandboxSecurityPolicy()
        assert policy.require_no_new_privileges is True

    def test_require_custom_seccomp_default(self):
        policy = SandboxSecurityPolicy()
        assert policy.require_custom_seccomp is True

    def test_seccomp_profile_path_default(self):
        policy = SandboxSecurityPolicy()
        assert policy.seccomp_profile_path == "sandbox/seccomp-sandbox.json"

    def test_readonly_rootfs_default(self):
        policy = SandboxSecurityPolicy()
        assert policy.readonly_rootfs is False

    def test_tmpfs_mounts_default_count(self):
        policy = SandboxSecurityPolicy()
        assert len(policy.tmpfs_mounts) == 4

    def test_chrome_no_sandbox_reason_present(self):
        policy = SandboxSecurityPolicy()
        assert "Chrome" in policy.chrome_no_sandbox_reason


class TestCapDropValidator:
    """Test cap_drop_must_include_all validator."""

    def test_rejects_empty_cap_drop(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            SandboxSecurityPolicy(cap_drop=[])

    def test_rejects_cap_drop_without_all(self):
        with pytest.raises(ValidationError, match="must include ALL"):
            SandboxSecurityPolicy(cap_drop=["NET_ADMIN"])

    def test_accepts_all_with_extras(self):
        policy = SandboxSecurityPolicy(cap_drop=["ALL", "EXTRA"])
        assert "ALL" in policy.cap_drop


class TestCapAddAllowlistValidator:
    """Test cap_add_must_be_allowlisted validator."""

    def test_rejects_disallowed_capability(self):
        with pytest.raises(ValidationError, match="not in allowlist"):
            SandboxSecurityPolicy(cap_add_allowlist=["SYS_ADMIN"])

    def test_rejects_net_admin(self):
        with pytest.raises(ValidationError, match="not in allowlist"):
            SandboxSecurityPolicy(cap_add_allowlist=["NET_ADMIN"])

    def test_accepts_valid_capabilities(self):
        policy = SandboxSecurityPolicy(cap_add_allowlist=["CHOWN", "SETGID"])
        assert policy.cap_add_allowlist == ["CHOWN", "SETGID"]

    def test_uppercases_input(self):
        policy = SandboxSecurityPolicy(cap_add_allowlist=["chown", "setuid"])
        assert policy.cap_add_allowlist == ["CHOWN", "SETUID"]

    def test_empty_allowlist_is_valid(self):
        policy = SandboxSecurityPolicy(cap_add_allowlist=[])
        assert policy.cap_add_allowlist == []

    def test_single_valid_capability(self):
        policy = SandboxSecurityPolicy(cap_add_allowlist=["NET_BIND_SERVICE"])
        assert policy.cap_add_allowlist == ["NET_BIND_SERVICE"]


class TestSeccompPathValidator:
    """Test seccomp_path_not_empty validator."""

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            SandboxSecurityPolicy(seccomp_profile_path="")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            SandboxSecurityPolicy(seccomp_profile_path="   ")

    def test_strips_whitespace(self):
        policy = SandboxSecurityPolicy(seccomp_profile_path="  path/to/seccomp.json  ")
        assert policy.seccomp_profile_path == "path/to/seccomp.json"

    def test_custom_path(self):
        policy = SandboxSecurityPolicy(seccomp_profile_path="/etc/seccomp/custom.json")
        assert policy.seccomp_profile_path == "/etc/seccomp/custom.json"


class TestModelSerialization:
    """Test Pydantic model serialization."""

    def test_to_dict(self):
        policy = SandboxSecurityPolicy()
        data = policy.model_dump()
        assert "cap_drop" in data
        assert "require_no_new_privileges" in data

    def test_from_dict(self):
        data = {
            "cap_drop": ["ALL"],
            "cap_add_allowlist": ["CHOWN"],
            "require_no_new_privileges": True,
            "require_custom_seccomp": False,
            "seccomp_profile_path": "test.json",
            "readonly_rootfs": True,
            "tmpfs_mounts": [],
        }
        policy = SandboxSecurityPolicy(**data)
        assert policy.readonly_rootfs is True
        assert policy.require_custom_seccomp is False

    def test_json_round_trip(self):
        original = SandboxSecurityPolicy()
        json_str = original.model_dump_json()
        restored = SandboxSecurityPolicy.model_validate_json(json_str)
        assert restored == original
