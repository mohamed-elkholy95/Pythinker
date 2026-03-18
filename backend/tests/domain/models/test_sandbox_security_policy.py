import pytest

from app.domain.models.sandbox_security_policy import SandboxSecurityPolicy


class TestSandboxSecurityPolicy:
    def test_default_caps_include_sys_chroot(self):
        """SYS_CHROOT must be in the default capability allowlist."""
        policy = SandboxSecurityPolicy()
        assert "SYS_CHROOT" in policy.cap_add_allowlist

    def test_sys_chroot_accepted_by_validator(self):
        """Attempting to add SYS_CHROOT must succeed."""
        policy = SandboxSecurityPolicy(
            cap_add_allowlist=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]
        )
        assert "SYS_CHROOT" in policy.cap_add_allowlist

    def test_valid_caps_accepted(self):
        """All valid capabilities including SYS_CHROOT must pass."""
        policy = SandboxSecurityPolicy(
            cap_add_allowlist=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]
        )
        assert len(policy.cap_add_allowlist) == 5

    def test_cap_drop_must_include_all(self):
        """cap_drop must contain ALL."""
        with pytest.raises(ValueError, match="must include ALL"):
            SandboxSecurityPolicy(cap_drop=["NET_RAW"])

    def test_empty_cap_drop_rejected(self):
        """Empty cap_drop must be rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            SandboxSecurityPolicy(cap_drop=[])
