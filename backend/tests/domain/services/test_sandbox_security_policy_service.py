"""Tests for sandbox security policy service and model."""

from unittest.mock import patch

import pytest

from app.domain.models.sandbox_security_policy import SandboxSecurityPolicy
from app.domain.services.sandbox_security_policy_service import get_sandbox_security_policy


class TestSandboxSecurityPolicyDefaults:
    """Policy defaults must match production compose."""

    def test_cap_drop_includes_all(self) -> None:
        policy = SandboxSecurityPolicy()
        assert "ALL" in policy.cap_drop

    def test_cap_add_allowlist_matches_production(self) -> None:
        policy = SandboxSecurityPolicy()
        expected = {"CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"}
        assert set(policy.cap_add_allowlist) == expected

    def test_require_no_new_privileges_default_true(self) -> None:
        policy = SandboxSecurityPolicy()
        assert policy.require_no_new_privileges is True

    def test_require_custom_seccomp_default_true(self) -> None:
        policy = SandboxSecurityPolicy()
        assert policy.require_custom_seccomp is True

    def test_seccomp_profile_path_default(self) -> None:
        policy = SandboxSecurityPolicy()
        assert "seccomp" in policy.seccomp_profile_path
        assert policy.seccomp_profile_path.endswith(".json")

    def test_chrome_no_sandbox_documented(self) -> None:
        policy = SandboxSecurityPolicy()
        assert "container" in policy.chrome_no_sandbox_reason.lower()
        assert "no-sandbox" in policy.chrome_no_sandbox_reason.lower()


class TestSandboxSecurityPolicyValidation:
    """Reject dangerous combinations."""

    def test_empty_cap_drop_rejected(self) -> None:
        with pytest.raises(ValueError, match="cap_drop cannot be empty"):
            SandboxSecurityPolicy(cap_drop=[])

    def test_cap_drop_without_all_rejected(self) -> None:
        with pytest.raises(ValueError, match="cap_drop must include ALL"):
            SandboxSecurityPolicy(cap_drop=["NET_RAW"])

    def test_cap_add_disallowed_capability_rejected(self) -> None:
        with pytest.raises(ValueError, match="not in allowlist"):
            SandboxSecurityPolicy(cap_add_allowlist=["SYS_ADMIN", "CHOWN"])

    def test_cap_add_allowlisted_succeeds(self) -> None:
        policy = SandboxSecurityPolicy(cap_add_allowlist=["CHOWN", "SETGID"])
        assert "CHOWN" in policy.cap_add_allowlist
        assert "SETGID" in policy.cap_add_allowlist

    def test_empty_seccomp_path_rejected_when_required(self) -> None:
        with pytest.raises(ValueError, match="seccomp_profile_path cannot be empty"):
            SandboxSecurityPolicy(seccomp_profile_path="", require_custom_seccomp=True)


class TestSandboxSecurityPolicyService:
    """Policy service resolves from config."""

    def test_get_policy_returns_valid_policy(self) -> None:
        with patch("app.domain.services.sandbox_security_policy_service.get_settings") as mock:
            mock.return_value.sandbox_seccomp_profile = "sandbox/seccomp-sandbox.json"
            # Clear cache to pick up mock
            get_sandbox_security_policy.cache_clear()
            try:
                policy = get_sandbox_security_policy()
                assert policy.cap_drop == ["ALL"]
                assert "CHOWN" in policy.cap_add_allowlist
                assert policy.seccomp_profile_path == "sandbox/seccomp-sandbox.json"
            finally:
                get_sandbox_security_policy.cache_clear()

    def test_get_policy_uses_compat_seccomp_when_config_none_mode_compat(self) -> None:
        with patch("app.domain.services.sandbox_security_policy_service.get_settings") as mock:
            mock.return_value.sandbox_seccomp_profile = None
            mock.return_value.sandbox_seccomp_profile_mode = "compat"
            get_sandbox_security_policy.cache_clear()
            try:
                policy = get_sandbox_security_policy()
                assert policy.seccomp_profile_path == "sandbox/seccomp-sandbox.compat.json"
            finally:
                get_sandbox_security_policy.cache_clear()

    def test_get_policy_uses_hardened_seccomp_when_mode_hardened(self) -> None:
        with patch("app.domain.services.sandbox_security_policy_service.get_settings") as mock:
            mock.return_value.sandbox_seccomp_profile = None
            mock.return_value.sandbox_seccomp_profile_mode = "hardened"
            get_sandbox_security_policy.cache_clear()
            try:
                policy = get_sandbox_security_policy()
                assert policy.seccomp_profile_path == "sandbox/seccomp-sandbox.hardened.json"
            finally:
                get_sandbox_security_policy.cache_clear()
