# Docker Rootless and Userns-Remap Isolation Playbook

**Context:** Task 8 — Runtime isolation modes for higher security deployments.

---

## Overview

Beyond standard Docker hardening (cap_drop, seccomp, no-new-privileges), two stronger isolation modes are available:

| Mode | Description | Use Case |
|------|-------------|----------|
| `standard` | Default Docker daemon | Development, CI |
| `userns-remap` | User namespace remapping | Shared host, multi-tenant |
| `rootless` | Rootless Docker daemon | Maximum isolation |

---

## Configuration

Add to `.env`:

```bash
# Docker daemon/runtime isolation mode
DOCKER_ISOLATION_MODE=standard  # standard | userns-remap | rootless

# Sandbox security profile (compat = broad allowlist, hardened = tightened)
SANDBOX_SECURITY_PROFILE=compat  # compat | hardened
```

---

## Host Prerequisites

### userns-remap

1. Edit `/etc/docker/daemon.json`:
   ```json
   {
     "userns-remap": "default"
   }
   ```
2. Restart Docker: `sudo systemctl restart docker`
3. Existing containers may need recreation.

### Rootless

1. Install rootless Docker: `curl -fsSL https://get.docker.com/rootless | sh`
2. Use `$XDG_RUNTIME_DIR/docker.sock` instead of `/var/run/docker.sock`
3. Compose must use the rootless socket path.

---

## Socket Path Differences

| Mode | Docker socket |
|------|---------------|
| standard | `/var/run/docker.sock` |
| rootless | `$XDG_RUNTIME_DIR/docker.sock` (e.g. `~/.local/run/docker.sock`) |

When using rootless, set `DOCKER_HOST`:

```bash
export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock
```

---

## Limitations and Caveats

- **Rootless:** No kernel module loading; some networking features limited.
- **Chrome for Testing:** Works in rootless; `--no-sandbox` still required for container-level isolation.
- **Performance:** Rootless can add ~5–10% overhead vs standard.

---

## Rollback

1. Restore `daemon.json` (remove `userns-remap`) and restart Docker.
2. For rootless, switch `DOCKER_HOST` back to `/var/run/docker.sock` and use the standard daemon.

---

## References

- [Docker Rootless mode](https://docs.docker.com/engine/security/rootless/)
- [Docker userns-remap](https://docs.docker.com/engine/security/userns-remap/)
