"""Service for resolving sandbox security policy from configuration."""

from functools import lru_cache

from app.core.config import get_settings
from app.domain.models.sandbox_security_policy import SandboxSecurityPolicy


@lru_cache(maxsize=1)
def get_sandbox_security_policy() -> SandboxSecurityPolicy:
    """Resolve sandbox security policy from settings.

    Returns the policy for use when creating dynamic sandbox containers.
    Cached to avoid repeated config access.
    """
    settings = get_settings()
    if settings.sandbox_seccomp_profile:
        seccomp_path = settings.sandbox_seccomp_profile
    elif settings.sandbox_seccomp_profile_mode == "hardened":
        seccomp_path = "sandbox/seccomp-sandbox.hardened.json"
    else:
        seccomp_path = "sandbox/seccomp-sandbox.compat.json"
    return SandboxSecurityPolicy(
        cap_drop=["ALL"],
        cap_add_allowlist=["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"],
        require_no_new_privileges=True,
        require_custom_seccomp=bool(seccomp_path),
        seccomp_profile_path=seccomp_path,
        readonly_rootfs=False,
        tmpfs_mounts=[
            "/run:size=50M,uid=1000,gid=1000",
            "/run/user/1000:size=10M,uid=1000,gid=1000,mode=0700",
            "/tmp:size=300M",
            "/home/ubuntu/.cache:size=150M,uid=1000,gid=1000,mode=0700",
        ],
        chrome_no_sandbox_reason=(
            "Chrome --no-sandbox is correct when container provides cap_drop+seccomp+no-new-privileges; "
            "Chrome's inner sandbox conflicts with container isolation."
        ),
    )
