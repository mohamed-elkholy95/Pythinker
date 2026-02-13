# Sandbox Deep Scan Analysis Report

**Date**: 2026-02-12  
**Last Updated**: 2026-02-12  
**Scope**: Docker sandbox image, backend sandbox design, implementation, lifecycle  
**Context7 Validation**: Docker best practices from `/websites/docker` (Score: 88.5/100)  
**Related**: [SANDBOX_PLAYWRIGHT_DESIGN_ENHANCEMENT_REPORT.md](./SANDBOX_PLAYWRIGHT_DESIGN_ENHANCEMENT_REPORT.md) — Chrome for Testing 128, Playwright design

---

## Executive Summary

This report identifies **issues** and **enhancement opportunities** in the Pythinker sandbox design and implementation, validated against Docker and container security best practices via Context7 MCP.

| Category | Issues | Enhancements | Resolved |
|----------|--------|--------------|----------|
| **Design** | 3 | 2 | 0 |
| **Security** | 4 | 3 | 0 |
| **Implementation** | 5 | 4 | 2 |
| **Docker/Image** | 4 | 5 | 0 |

---

## 1. Design Issues

### 1.1 Dual Sandbox Creation Paths (Dead Code)

**Location**: `backend/app/core/sandbox_manager.py`, `backend/app/application/services/agent_service.py`

**Issue**: Two sandbox creation mechanisms exist with different behavior:

- **EnhancedSandboxManager** + **ManagedSandbox**: Creates containers via ` ManagedSandbox.create()`, stores in `_sandboxes`, monitors health. Used only for `get_sandbox_stats()` in monitoring routes.
- **Actual allocation path**: `AgentService._get_or_create_sandbox()` uses `DockerSandbox.create()` (ephemeral) or `SandboxPool.acquire()` (pooled) or static `DockerSandbox.get()` (static mode).

**Impact**: `EnhancedSandboxManager` never creates sandboxes used by sessions. Stats report `total_sandboxes: 0` because `_sandboxes` is never populated by the real allocation path. Design confusion and misleading metrics.

**Evidence**: `CODE_QUALITY_REPORT.md` line 160: *"EnhancedSandboxManager (never used)"*

**Recommendation**: Either:
- Remove `EnhancedSandboxManager`/`ManagedSandbox` and derive stats from `SandboxPool` + session→sandbox mapping, or
- Unify design so one manager owns all sandbox creation and lifecycle.

---

### 1.2 SandboxPool Expects `container_id` but DockerSandbox Has None

**Location**: `backend/app/core/sandbox_pool.py`, `backend/app/infrastructure/external/sandbox/docker_sandbox.py`

**Issue**: Pool health monitor and OOM detection use `sandbox.container_id`:

```python
# sandbox_pool.py:825, 835, 842
status = await asyncio.to_thread(_check_container_status, sandbox.container_id)
```

`DockerSandbox` has `_container_name` and `id` (returns container name), but **no `container_id`** attribute. This causes `AttributeError` when:
- `_continuous_health_monitor()` runs
- OOM event processing compares `sandbox.container_id == container_id`

**Recommendation**: Add `container_id` to `DockerSandbox`:
- For ephemeral containers: store `container.short_id` in `_create_task()` before losing the container reference
- For static sandboxes: use container name or resolve via Docker API when needed (Docker accepts name in `containers.get()`)

---

### 1.3 ManagedSandbox vs DockerSandbox Config Divergence

**Location**: `backend/app/core/sandbox_manager.py` `_get_container_config()`

**Issue**: `ManagedSandbox._get_container_config()` omits:
- `ulimits` (nofile, nproc)
- `sandbox_seccomp_profile`
- Proxy env vars (`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`)

`DockerSandbox._create_task()` includes these. If `ManagedSandbox` were ever used for creation, containers would have weaker isolation and different behavior.

**Recommendation**: Align container config between both paths or remove `ManagedSandbox` creation path.

---

## 2. Security Issues

### 2.1 NOPASSWD Sudo for ubuntu User

**Location**: `sandbox/Dockerfile` line 55

```dockerfile
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu
```

**Issue**: Unrestricted root escalation. Any compromise of the `ubuntu` user yields root inside the container.

**Context7**: Docker best practices recommend running as non-root and minimizing privilege. Hardening guidance: *"running as a non-root user, reducing writable surfaces"*.

**Recommendation**: Remove sudo or restrict to specific commands only (e.g. `apt-get` for optional tool installs). Most sandbox operations run as `ubuntu` without sudo.

---

### 2.2 Single-Stage Image with Build Tools

**Location**: `sandbox/Dockerfile`

**Issue**: Image includes build tools (python3-dev, compilers, npm packages like cyclonedx, playwright browsers) in the final runtime image. Increases attack surface and image size.

**Context7**: Multi-stage builds separate build-time and runtime, producing smaller, more secure images.

**Recommendation**: Use multi-stage build:
- Stage 1: Install deps, build venv, install Playwright browsers
- Stage 2: Copy only runtime artifacts, exclude dev tools

---

### 2.3 fix_permissions Runs as Root

**Location**: `sandbox/supervisord.conf` `[program:fix_permissions]`

**Issue**: `fix_permissions.sh` runs as `user=root`. While needed for `chown`/`mkdir`, it increases exposure. Best practice is to minimize root usage.

**Recommendation**: Ensure script is minimal and exits quickly. Consider using `USER` directive in Dockerfile where possible (though initial setup may require root).

---

### 2.4 clone3 Blocked in Seccomp

**Location**: `sandbox/seccomp-sandbox.json`

```json
{"names":["clone3"],"action":"SCMP_ACT_ERRNO","errnoRet":38}
```

**Issue**: Newer glibc and runtimes (e.g. Go 1.17+, some Node versions) use `clone3`. Blocking it can cause subtle failures. Current stack (Python, Node 22, Chrome for Testing 128.0.6613.137) may work with `clone` fallback, but future upgrades could break.

**Recommendation**: Monitor for runtime issues. If needed, add `clone3` with appropriate argument filtering (similar to `clone`).

---

## 3. Implementation Issues

### 3.1 /run/user/1000 — RESOLVED

**Location**: `sandbox/fix-permissions.sh`

**Status**: Fixed. The script now creates `/run/user/1000` at startup (tmpfs overlays `/run` and wipes build-time directory). No action needed.

---

### 3.2 Chrome for Testing 128.0.6613.137 — RESOLVED

**Location**: `sandbox/Dockerfile`, `sandbox/supervisord.conf`, `backend/app/infrastructure/external/browser/playwright_browser.py`, `backend/app/domain/services/tools/playwright_tool.py`

**Status**: Implemented. Primary sandbox browser is now Chrome for Testing 128.0.6613.137 (Official Build) on Ubuntu 22.04 64-bit. User agents aligned to Chrome/128.0.6613.137. PPA Chromium retained as fallback for Playwright script tools. See [SANDBOX_PLAYWRIGHT_DESIGN_ENHANCEMENT_REPORT.md](./SANDBOX_PLAYWRIGHT_DESIGN_ENHANCEMENT_REPORT.md).

---

### 3.3 Config vs docker-compose Resource Mismatch

**Location**: `backend/app/core/config.py`, `docker-compose.yml`

| Setting | Config default | docker-compose |
|---------|----------------|----------------|
| sandbox_mem_limit | 4g | 3G (deploy.limits) |
| sandbox_cpu_limit | 1.5 | 1.5 ✓ |

**Issue**: Config `sandbox_mem_limit` is 4g, but compose uses 3G. Ephemeral containers (created by `DockerSandbox._create_task()`) use config (4g); compose sandboxes use 3G.

**Recommendation**: Align limits. Document that compose overrides apply for static sandboxes.

---

### 3.4 sandbox2 Missing VNC Ports (Production)

**Location**: `docker-compose.yml`

**Issue**: `sandbox` exposes VNC (5902:5900, 5901:5901); `sandbox2` does not. VNC via backend proxy still works (Docker network). Direct host access to sandbox2 VNC is impossible.

**Recommendation**: Add VNC ports to sandbox2 for parity, or document that only sandbox has direct VNC access.

---

### 3.5 Development VNC Ports Commented

**Location**: `docker-compose-development.yml`

**Issue**: VNC ports commented with note "using CDP screencast". VNC fallback still used by LiveViewer when CDP fails. Backend proxy path works, but direct VNC from host does not.

**Recommendation**: Uncomment ports if direct VNC debugging is needed, or add a short comment explaining proxy-based VNC flow.

---

### 3.6 Pool Health Monitor Uses `sandbox.container_id` Without Fallback

**Location**: `backend/app/core/sandbox_pool.py` lines 617–624, 828–836

**Issue**: `_check_sandbox_health` and `_monitor_docker_events` assume `sandbox.container_id`. DockerSandbox has `id` (container name) but no `container_id`. Docker `containers.get()` accepts name, so using `sandbox.id` would work for lookups.

**Recommendation**: Add `container_id` property to DockerSandbox returning `_container_name` for Docker API compatibility, or use `getattr(sandbox, 'container_id', sandbox.id)` in pool.

---

## 4. Dockerfile / Image Issues

### 4.1 No Multi-Stage Build

**Context7**: Multi-stage builds reduce image size and exclude build tools from runtime.

**Current**: Single stage with dev tools (bandit, mypy, cyclonedx-bom, etc.).

**Recommendation**: Split into builder + runtime stages. Copy venv, Node, and Playwright browsers into minimal runtime image.

---

### 4.2 Large Dependency Set

**Issue**: PPA (deadsnakes, xtradeb, github cli), Chrome for Testing 128.0.6613.137 + PPA Chromium (fallback), Playwright (chromium, firefox, webkit), many Python/JS dev tools. Increases size and vulnerability surface.

**Update**: Primary browser is now Chrome for Testing (version-pinned); PPA Chromium kept as fallback for Playwright scripts.

**Recommendation**: Separate dev and prod images, or move dev tools to optional layer.

---

### 4.3 software-properties-common Purged Late

**Location**: `sandbox/Dockerfile` line 213

**Issue**: Purged at end of build. Could be removed earlier in a multi-stage flow to reduce layer size.

---

### 4.4 No Read-Only Root Filesystem

**Context7**: Immutability and read-only root reduce writable attack surface.

**Issue**: Root filesystem is writable. Workspace and temp dirs need write access.

**Recommendation**: Consider `read_only` + explicit tmpfs/volumes for `/tmp`, `/workspace`, `/home/ubuntu/.cache` if compatible with all services.

---

## 5. Suggested Enhancements (Context7 Validated)

### 5.1 Multi-Stage Dockerfile (Docker Best Practice)

```dockerfile
# Stage 1: Builder
FROM ubuntu:22.04 AS builder
# ... install deps, create venv, playwright ...
WORKDIR /app
COPY requirements*.txt .
RUN pip install -r requirements.txt
RUN playwright install --with-deps chromium

# Stage 2: Runtime
FROM ubuntu:22.04
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright
# ... minimal runtime setup
USER ubuntu
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
```

### 5.2 Restrict Capabilities Further

**Context7**: *"remove all capabilities except those explicitly required"*.

**Current**: `cap_drop: ALL`, `cap_add`: CHOWN, SETGID, SETUID, NET_BIND_SERVICE, SYS_CHROOT.

**Enhancement**: Audit each cap. For example, `SYS_CHROOT` may only be needed if using chroot; consider dropping if unused.

### 5.3 Add OOM Score Adjusment

**Context7**: `--oom-score-adj` tunes OOM behavior.

**Enhancement**: Set `oom_score_adj` so sandbox containers are preferred for kill under memory pressure over critical host services.

### 5.4 Use Docker Health Check

**Current**: External health checks via API.

**Enhancement**: Add `HEALTHCHECK` in Dockerfile so Docker marks unhealthy containers and orchestrators can act.

```dockerfile
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1
```

### 5.5 Memory Reservation

**Context7**: `--memory-reservation` sets soft limit.

**Enhancement**: Add `deploy.resources.reservations.memory` in compose for more predictable scheduling.

---

## 6. Summary of Action Items

| Priority | Action | Status |
|----------|--------|--------|
| **High** | Add `container_id` (or equivalent) to DockerSandbox for SandboxPool health/OOM | Open |
| **High** | Resolve EnhancedSandboxManager/ManagedSandbox dead code — remove or unify | Open |
| **Medium** | Restrict or remove ubuntu NOPASSWD sudo | Open |
| **Medium** | Align ManagedSandbox container config with DockerSandbox if keeping both | Open |
| **Medium** | Align memory limits (config 4g vs compose 3G) | Open |
| **Low** | Add VNC ports to sandbox2 for parity | Open |
| **Low** | Multi-stage Dockerfile | Open |
| **Low** | Document VNC flow in dev compose | Open |
| **Low** | Add Dockerfile HEALTHCHECK | Open |

### Completed (2026-02-12)

| Action | Notes |
|--------|-------|
| Chrome for Testing 128.0.6613.137 | Primary browser in sandbox; UA aligned; config added |
| /run/user/1000 | fix-permissions.sh creates at startup |

---

## 7. Context7 References

| Topic | Library ID | Key Guidance |
|-------|------------|--------------|
| Base image hardening | /websites/docker | Non-root, minimal components, immutability |
| Multi-stage builds | /websites/docker | Separate build/runtime for smaller, more secure images |
| Capabilities | /websites/docker | Drop all, add only required |
| Resource limits | /websites/docker | Memory, CPU, ulimits for isolation |
| Security | /websites/docker | seccomp, no-new-privileges, least privilege |
| Playwright / Chrome | /microsoft/playwright-python, /microsoft/playwright | executablePath, channel for custom browsers |

---

*Report generated from deep scan of sandbox codebase and Context7 MCP validation. Updated 2026-02-12 with Chrome for Testing 128 implementation.*
