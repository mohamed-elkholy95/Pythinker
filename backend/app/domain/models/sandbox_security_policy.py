"""Sandbox security policy model for Docker container hardening.

Provides a typed contract for security controls applied when creating
dynamic sandbox containers (SANDBOX_LIFECYCLE_MODE=dynamic).
"""

from pydantic import BaseModel, field_validator


class SandboxSecurityPolicy(BaseModel):
    """Typed security policy for Docker sandbox container creation.

    Defaults align with production docker-compose hardening.
    """

    cap_drop: list[str] = ["ALL"]
    cap_add_allowlist: list[str] = ["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]
    require_no_new_privileges: bool = True
    require_custom_seccomp: bool = True
    seccomp_profile_path: str = "sandbox/seccomp-sandbox.json"
    readonly_rootfs: bool = False
    tmpfs_mounts: list[str] = [
        "/run:size=50M,uid=1000,gid=1000",
        "/run/user/1000:size=10M,uid=1000,gid=1000,mode=0700",
        "/tmp:size=300M",
        "/home/ubuntu/.cache:size=150M,uid=1000,gid=1000,mode=0700",
    ]
    chrome_no_sandbox_reason: str = (
        "Chrome --no-sandbox is correct when container provides cap_drop+seccomp+no-new-privileges; "
        "Chrome's inner sandbox conflicts with container isolation."
    )

    @field_validator("cap_drop")
    @classmethod
    def cap_drop_must_include_all(cls, v: list[str]) -> list[str]:
        """Reject empty cap_drop or missing ALL."""
        if not v:
            raise ValueError("cap_drop cannot be empty; must include ALL")
        if "ALL" not in v:
            raise ValueError("cap_drop must include ALL for hardened sandbox")
        return v

    @field_validator("cap_add_allowlist")
    @classmethod
    def cap_add_must_be_allowlisted(cls, v: list[str]) -> list[str]:
        """Capabilities must be from the known allowlist."""
        allowed = {"CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"}
        for cap in v:
            if cap.upper() not in allowed:
                raise ValueError(f"cap_add '{cap}' not in allowlist: {sorted(allowed)}")
        return [c.upper() for c in v]

    @field_validator("seccomp_profile_path")
    @classmethod
    def seccomp_path_not_empty(cls, v: str) -> str:
        """Seccomp profile path must be non-empty when required."""
        if not v or not v.strip():
            raise ValueError("seccomp_profile_path cannot be empty when require_custom_seccomp is True")
        return v.strip()
