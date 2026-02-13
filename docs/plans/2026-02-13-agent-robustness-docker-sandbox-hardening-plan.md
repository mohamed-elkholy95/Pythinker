# Agent Robustness + Docker Sandbox Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Task 1 Status:** ✅ Completed 2026-02-13. Baseline artifacts: `docs/reports/2026-02-13-agent-sandbox-threat-model.md`, `docs/reports/2026-02-13-docker-hardening-baseline.md`.

**Task 2 Status:** ✅ Completed 2026-02-13. Policy contract: `backend/app/domain/models/sandbox_security_policy.py`, `backend/app/domain/services/sandbox_security_policy_service.py`. Dynamic sandbox creation uses policy.

**Task 3 Status:** ✅ Completed 2026-02-13. Dev compose hardened; `docs/reports/2026-02-13-compose-hardening-diff.md`; `backend/tests/core/test_compose_hardening.py`.

**Task 4 Status:** ✅ Completed 2026-02-13. Multi-stage Dockerfile (builder + runtime), tini init, USER ubuntu, dev tools removed from runtime, pnpm 10.29.2, /run/user/1000 tmpfs in compose, `sandbox/.dockerignore`, `sandbox/tests/test_image_policy.py`.

**Task 5 Status:** ✅ Completed 2026-02-13. Profile split: `seccomp-sandbox.compat.json`, `seccomp-sandbox.hardened.json`; `SANDBOX_SECCOMP_PROFILE_MODE` config; policy service resolves profile by mode; `backend/tests/integration/test_sandbox_seccomp_runtime.py`; `docs/reports/2026-02-13-seccomp-compat-matrix.md`.

**Task 6 Status:** ✅ Completed 2026-02-13. Idempotent teardown early-exit; fire-and-forget task cleanup tests; double-stop and warmup-cancellation tests; `find_by_id_and_user_id` in FakeSessionRepository.

**Goal:** Harden agent execution and sandbox isolation while improving failure recovery, deterministic teardown, and runtime safety for Docker-based development deployments.

**Architecture:** Treat hardening as three coupled layers: (1) container/runtime isolation, (2) sandbox lifecycle and execution safety controls, and (3) agent orchestration robustness and guardrails. Implement each layer behind explicit config flags, add failing tests first, and ship with measurable security/reliability SLO gates.

**Tech Stack:** Docker/Compose, Linux seccomp/capabilities, FastAPI, asyncio, Playwright/CDP, Python (Pydantic v2), pytest, Prometheus/Grafana.

---

## Context7 Validation Basis (Fetched 2026-02-13)

- Source library: `/docker/docs` (Docker official docs, Score: 87.5/100).
- Confirmed hardening controls to enforce:
1. `no-new-privileges`, `cap_drop`, custom `seccomp` profiles, `read_only`, `tmpfs`, and resource limits.
2. Multi-stage builds, minimal runtime images, non-root execution, version pinning for critical binaries.
3. Rootless mode and `userns-remap` as higher-isolation options for daemon/runtime.

- Docker Compose production pattern (from Context7 `/docker/docs` — containerize guide):
```yaml
# Reference pattern: production service with full hardening
security_opt:
  - no-new-privileges:true
read_only: true
tmpfs:
  - /tmp
deploy:
  resources:
    limits:
      memory: '2G'
      cpus: '1.0'
    reservations:
      memory: '512M'
      cpus: '0.25'
```

- Non-root user pattern (from Context7 `/docker/docs` — scout policy):
```dockerfile
FROM alpine AS builder
COPY Makefile ./src /
RUN make build

FROM alpine AS runtime
COPY --from=builder bin/production /app
USER nonroot
ENTRYPOINT ["/app/production"]
```

## Reference Sandbox Environment Specification (2026-02-13)

> Source: `Detailed Report of Installed Apps, OS, and Chromium Version/` — audited from a production-grade sandbox environment.

The reference environment defines the **target runtime specification** for the Pythinker sandbox image. All packages, versions, and configurations below are verified working together. Task 4 must produce a Dockerfile whose runtime stage matches this specification.

### Base OS

| Property | Value |
|----------|-------|
| OS | Ubuntu 22.04.5 LTS |
| Kernel | 6.1.102 x86_64 |
| Architecture | x86_64 (linux/amd64) |

### Core Tool Versions (pinned)

| Tool | Version | Notes |
|------|---------|-------|
| Chromium | 128.0.6613.137 | Keep Chrome for Testing binary (version-matched, CDP-optimized) |
| Python | 3.11.0rc1 | Via deadsnakes PPA (already in our Dockerfile) |
| Node.js | v22.13.0 | Via NVM (already pinned) |
| NPM | 10.9.2 | Bundled with Node.js |
| PNPM | 10.29.2 | Update from current 10.28.1 |
| Git | 2.34.1 | Via apt |
| Curl | 7.81.0 | Via apt |
| Wget | 1.21.2 | Via apt |
| GitHub CLI | 2.81.0 | Via apt repo |

### APT Packages — MISSING from Current Dockerfile (must add)

**Container Infrastructure (CRITICAL):**
- `tini` — Proper PID 1 init process for signal handling (zombie reaping, SIGTERM propagation). Use as `ENTRYPOINT ["/usr/bin/tini", "--"]` wrapping supervisord.

**Productivity & Document Processing:**
- `libreoffice` (full suite: calc, writer, draw, impress, math, base) — Document conversion/generation
- `code-server` 4.104.3 — VS Code web IDE for interactive coding
- `poppler-utils` — PDF utilities (required by `pdf2image` Python package)
- `graphviz` — Graph/diagram visualization

**Database & Networking:**
- `mysql-client` / `mysql-client-core-8.0` — MySQL database connectivity
- `openssh-server` + `openssh-client` — SSH access to sandbox
- `net-tools` — Network diagnostics (ifconfig, netstat)
- `chrony` — NTP time synchronization for distributed logging

**System Utilities:**
- `lsof` — List open files (process diagnostics)
- `psmisc` — Process management (killall, fuser, pstree)
- `make` — Build automation
- `patch` — File patching
- `vim` — Full text editor
- `nano` — Simple text editor
- `xclip` — X11 clipboard utility
- `xdg-utils` — Desktop integration utilities

**Java Runtime:**
- `default-jre` / `openjdk-11-jre` — Java Runtime Environment for JVM-based tools

**Multimedia & Graphics:**
- `gstreamer1.0-plugins-base`, `gstreamer1.0-plugins-good`, `gstreamer1.0-plugins-bad`, `gstreamer1.0-plugins-ugly`, `gstreamer1.0-libav`, `gstreamer1.0-tools` — Full GStreamer multimedia stack
- `pulseaudio` + `pulseaudio-utils` — Audio server
- `vulkan-tools` + `mesa-vulkan-drivers` — GPU/Vulkan support
- `mesa-utils` + `mesa-common-dev` — Mesa 3D utilities
- `ocl-icd-libopencl1` — OpenCL support

**X11/GUI Enhancements:**
- `libgtk-3-0` + `libgtk2.0-0` — GTK2/3 libraries for GUI applications
- `xinit` — X session initialization
- `xorg-dev` + `xserver-xorg-dev` + `xserver-xorg-core` — Full X.org server
- `tcl` + `tk` — Tcl/Tk scripting/GUI toolkit

### APT Packages — TO REMOVE from Runtime (dev-only, not in reference)

- `language-pack-zh-hans` — Chinese locale (English-only runtime, already removed in rebrand)
- `software-properties-common` — Already purged at end of current Dockerfile (keep this purge)

### npm Global Packages — TO REMOVE from Runtime (dev-only, not in reference)

The reference environment has only `npm` and `pnpm` globally. Remove these dev-only globals from runtime:
- `prettier`, `eslint`, `typescript`, `jest`, `@types/node`, `@cyclonedx/cyclonedx-npm` — Linting/testing tools (install per-project, not globally)
- `yarn` — Package manager (reference doesn't use it)

**Keep in runtime:**
- `pnpm` (update to `10.29.2`)
- `@anthropic-ai/mcpb` (MCP tooling, Pythinker-specific)
- `@mermaid-js/mermaid-cli` (diagram generation, agent capability)

### Python Packages (runtime)

`requirements.runtime.txt` already matches the reference environment exactly — no changes needed. All 93 packages are version-pinned and aligned.

### Python Dev Tools — TO REMOVE from Runtime (not in reference)

These are installed in the current Dockerfile but absent from the reference runtime. Move to build stage only:
- `black`, `flake8`, `pylint`, `mypy`, `bandit` — Linting/security tools
- `pytest`, `pytest-cov`, `pytest-asyncio` — Testing tools
- `isort`, `autopep8` — Formatting tools
- `cyclonedx-bom` — SBOM generation

### Design Decisions

| Decision | Current | Reference | Action |
|----------|---------|-----------|--------|
| Container init | None (supervisord is PID 1) | `tini` 0.19.0 | **ADD** `tini` as ENTRYPOINT wrapping supervisord |
| Browser | Chrome for Testing binary | apt `chromium-browser` | **KEEP** Chrome for Testing (version-pinned, CDP-optimized, matches our CDP port config) |
| NVM location | `/usr/local/nvm` (system) | `/home/ubuntu/.nvm` (user) | **KEEP** `/usr/local/nvm` (system-wide is better for Docker, avoids user-profile sourcing) |
| Playwright browsers | chromium + firefox + webkit | Not in reference pip | **KEEP** all three (agent needs multi-browser support) |

---

## Current State Assessment (2026-02-13 Snapshot)

### Already Hardened (Production `docker-compose.yml`)

The production compose file already enforces a strong baseline for both `sandbox` and `sandbox2`:
- `security_opt: [no-new-privileges:true, seccomp:./sandbox/seccomp-sandbox.json]`
- `cap_drop: [ALL]` with selective `cap_add: [CHOWN, SETGID, SETUID, NET_BIND_SERVICE, SYS_CHROOT]`
- Resource limits: `memory: 3G`, `cpus: 1.5`, `pids: 300`, reservation `memory: 768M`
- `tmpfs` mounts for `/run`, `/tmp`, `/home/ubuntu/.cache`
- `ulimits` for nofile (65536) and nproc (4096/8192)
- `shm_size: 2gb` per Playwright Docker docs
- Healthchecks with interval/timeout/retries

### Remaining Gaps

1. **Development compose (`docker-compose-development.yml`)** has NO security controls: no `security_opt`, no `cap_drop`/`cap_add`, no seccomp profile. This means local development runs with full privileges.
2. **`sandbox/Dockerfile`** is single-stage, includes broad dev tooling (black, flake8, pylint, mypy, bandit, jest, eslint, etc.) in runtime image, and has `NOPASSWD:ALL` sudo. No `USER` instruction — container entrypoint runs as root.
3. **Seccomp profile** (`sandbox/seccomp-sandbox.json`) has 330+ allowed syscalls with default `SCMP_ACT_ERRNO`. No audit data exists to confirm which syscalls are actually used vs. unnecessarily allowed.
4. **Backend policy enforcement** is spread across `config.py`, `docker_sandbox.py`, and orchestration services without a single typed security policy contract. The dynamic sandbox creation path (`DockerSandbox._create_task()`) does not reference a centralized policy.
5. **Chrome `--no-sandbox` flag**: Used in all compose files. This is **architecturally correct** — Chrome's inner sandbox is intentionally disabled because equivalent isolation is provided at the container level via seccomp + capabilities + no-new-privileges. This should be **documented, not removed**.
6. **Agent lifecycle gaps**: Existing services have circuit breaker, session locking, and orphan reaper, but specific edge cases (double-stop, warmup cancellation during chat start, fire-and-forget task leaks) need targeted hardening.
7. **Security critic exists** but may not be enforced as a **mandatory hard gate** before execution — needs verification and enhancement, not creation from scratch.

## Non-Negotiable Success Criteria

1. Sandbox default runtime is non-root, no privileged container mode, no ambient extra capabilities beyond documented allowlist.
2. Agent task lifecycle is idempotent for create/warm/chat/stop/delete and leak-free under retries/cancellations/timeouts.
3. Security policy violations are blocked early with typed errors and structured telemetry.
4. Compose and dynamic sandbox paths enforce equivalent hardening baselines.

---

### Task 1: Establish Hardening Baseline and Threat Model

**Files:**
- Create: `docs/reports/2026-02-13-agent-sandbox-threat-model.md`
- Create: `docs/reports/2026-02-13-docker-hardening-baseline.md`
- Modify: `docs/plans/2026-02-13-agent-robustness-docker-sandbox-hardening-plan.md`
- Test: N/A (documentation + measured baseline)

**Step 1: Capture runtime configuration inventory**

Run:
```bash
cd /Users/panda/Desktop/Projects/Pythinker
rg -n "no-new-privileges|cap_drop|cap_add|seccomp|read_only|tmpfs|user:|privileged|--no-sandbox|--disable-setuid-sandbox|shm_size|pids" docker-compose*.yml sandbox/Dockerfile -S
```
Expected: all active hardening knobs and anti-hardening flags are enumerated.

**Step 2: Capture live container security settings**

Run:
```bash
docker inspect pythinker-sandbox-1 | jq '.[0].HostConfig | {Privileged, ReadonlyRootfs, SecurityOpt, CapDrop, CapAdd, PidsLimit, Memory, NanoCpus}'
```
Expected: JSON evidence for actual runtime controls.

**Step 3: Document existing hardening baseline**

Record what is already enforced in production compose (see "Already Hardened" section above) and what is missing in dev compose. This establishes the before-state for the hardening report.

**Step 4: Produce threat model**

Document threat paths:
1. Prompt-to-shell escape attempts.
2. Sandbox-to-host breakout vectors.
3. Cross-session data bleed.
4. Resource exhaustion and denial-of-service loops.

**Step 5: Commit baseline artifacts**

```bash
git add docs/reports/2026-02-13-agent-sandbox-threat-model.md docs/reports/2026-02-13-docker-hardening-baseline.md docs/plans/2026-02-13-agent-robustness-docker-sandbox-hardening-plan.md
git commit -m "docs: add sandbox threat model and docker hardening baseline"
```

---

### Task 2: Centralize Sandbox Security Policy Contract

**Files:**
- Create: `backend/app/domain/models/sandbox_security_policy.py`
- Create: `backend/app/domain/services/sandbox_security_policy_service.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/infrastructure/external/sandbox/docker_sandbox.py`
- Test: `backend/tests/domain/services/test_sandbox_security_policy_service.py`
- Test: `backend/tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py`

**Step 1: Write failing tests for policy defaults and validation**

Add tests for:
1. Default capability allowlist matches production compose (`cap_drop: ALL`, `cap_add: [CHOWN, SETGID, SETUID, NET_BIND_SERVICE, SYS_CHROOT]`).
2. Required seccomp path presence.
3. Rejection of dangerous combinations (example: allow privileged or empty cap_drop).
4. Chrome `--no-sandbox` is documented as intentionally correct when container-level isolation is active.

**Step 2: Run failing tests**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_sandbox_security_policy_service.py tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py -v
```

**Step 3: Implement policy contract**

Add typed Pydantic v2 policy model with:
1. `cap_drop: list[str]` default `["ALL"]`.
2. `cap_add_allowlist: list[str]` default `["CHOWN", "SETGID", "SETUID", "NET_BIND_SERVICE", "SYS_CHROOT"]`.
3. `require_no_new_privileges: bool` default `True`.
4. `require_custom_seccomp: bool` default `True`.
5. `seccomp_profile_path: str` default `"sandbox/seccomp-sandbox.json"`.
6. `readonly_rootfs: bool` default `False` (sandbox needs writable paths — see Task 3).
7. `tmpfs_mounts: list[str]` default `["/run:size=50M", "/tmp:size=300M", "/home/ubuntu/.cache:size=150M"]`.
8. `chrome_no_sandbox_reason: str` — documents why `--no-sandbox` is correct inside hardened containers.

Use `@field_validator` with `@classmethod` for validation (per Pydantic v2 best practices).

**Step 4: Wire policy into Docker sandbox create path (critical for dynamic mode)**

Ensure `DockerSandbox._create_task()` resolves security options from the policy service, not scattered literals. This is the primary enforcement point — compose files handle static mode, but dynamic sandbox creation via the Docker API must also apply the policy contract. Verify the policy is applied when `SANDBOX_LIFECYCLE_MODE=dynamic`.

**Step 5: Re-run tests and commit**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_sandbox_security_policy_service.py tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py -v
git add backend/app/domain/models/sandbox_security_policy.py backend/app/domain/services/sandbox_security_policy_service.py backend/app/core/config.py backend/app/infrastructure/external/sandbox/docker_sandbox.py backend/tests/domain/services/test_sandbox_security_policy_service.py backend/tests/infrastructure/external/sandbox/test_docker_sandbox_security_policy.py
git commit -m "feat: centralize sandbox security policy and enforce in docker sandbox creation"
```

---

### Task 3: Harden Compose Runtime Defaults (Static + Dev + Dokploy)

**Files:**
- Modify: `docker-compose.yml` (minimal changes — already hardened)
- Modify: `docker-compose-development.yml` (primary target — add security controls)
- Modify: `docker-compose.dokploy.yml`
- Create: `docs/reports/2026-02-13-compose-hardening-diff.md`
- Test: `backend/tests/integration/test_sandbox_http_pooling.py`
- Test: `backend/tests/core/test_sandbox_lifecycle_mode.py`

**Step 1: Write failing config policy tests**

Create tests that parse compose files and assert:
1. `security_opt` includes `no-new-privileges:true` (ALL compose files).
2. `cap_drop` includes `ALL` (ALL compose files).
3. `pids` and memory/cpu constraints are defined (ALL compose files).
4. Chrome `--no-sandbox` is present AND a comment documents why it is correct: container-level isolation (seccomp + cap_drop + no-new-privileges) provides equivalent sandboxing, making Chrome's inner sandbox redundant and conflicting.

> **Important:** Do NOT test for removal of `--no-sandbox`. Chrome's inner sandbox uses `clone()`, `setuid`, and PID namespaces that conflict with container-level restrictions. When the container provides `cap_drop: ALL` + seccomp + `no-new-privileges`, Chrome's sandbox is redundant. `--no-sandbox` delegates sandboxing to the container. This is the documented Playwright/Docker pattern.

**Step 2: Implement hardened profile structure**

Add profile-based environment strategy:
1. `SANDBOX_SECURITY_PROFILE=compat|hardened`.
2. Hardened default in non-dev compose (production already has this).
3. Dev compose gets the same controls as production — the compat fallback is only for edge cases where host constraints prevent full hardening (e.g., Docker Desktop on macOS without seccomp support).

**Step 3: Inventory sandbox write paths before considering `read_only`**

Before enabling `read_only: true` for the sandbox, run `docker diff` on a running sandbox after a typical session to capture all filesystem writes. Known write paths that must be preserved:

| Path | Type | Purpose |
|------|------|---------|
| `/home/ubuntu/.local/pythinker_sandbox.db` | Volume/tmpfs | SQLite framework DB |
| `/home/ubuntu/.config/` | Volume | Browser profiles, openbox config |
| `/workspace` | Volume | User code execution workspace |
| `/app/sandbox_context.json` | Volume | Context output |
| `/app/sandbox_context.md` | Volume | Context output |
| `/opt/base-python-venv/` | Volume | Python venv template |
| `/var/log/supervisor/` | tmpfs | Supervisord logs (if not /dev/stdout) |
| `/run/user/1000/` | tmpfs | XDG runtime dir |
| `/tmp/chrome` | tmpfs (already) | Chrome user data dir |
| `/tmp/supervisor.sock` | tmpfs (already) | Supervisord socket |
| `/tmp/supervisord.pid` | tmpfs (already) | Supervisord pidfile |
| `/home/ubuntu/.cache` | tmpfs (already) | Browser/tool caches |

**Decision:** `read_only: true` for the sandbox requires too many volume/tmpfs exceptions to be worthwhile at this stage. Enable `read_only: true` only for stateless services (backend, frontend) where it's straightforward. Revisit sandbox `read_only` after multi-stage Dockerfile work (Task 4) reduces write surface.

**Step 4: Add security controls to dev compose**

Add to `docker-compose-development.yml` sandbox service:
```yaml
security_opt:
  - no-new-privileges:true
  - seccomp:./sandbox/seccomp-sandbox.json
cap_drop:
  - ALL
cap_add:
  - CHOWN
  - SETGID
  - SETUID
  - NET_BIND_SERVICE
  - SYS_CHROOT
```

**Step 5: Validate with integration tests**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/integration/test_sandbox_http_pooling.py tests/core/test_sandbox_lifecycle_mode.py -v
```

**Step 6: Commit**

```bash
git add docker-compose.yml docker-compose-development.yml docker-compose.dokploy.yml docs/reports/2026-02-13-compose-hardening-diff.md backend/tests/integration/test_sandbox_http_pooling.py backend/tests/core/test_sandbox_lifecycle_mode.py
git commit -m "feat: enforce compose hardening baseline with profile-driven sandbox security"
```

---

### Task 4: Refactor Sandbox Image to Hardened Multi-Stage Runtime

> **Scope:** This task implements the multi-stage Dockerfile, integrates the reference environment packages (see "Reference Sandbox Environment Specification" above), adds `tini` init, switches to non-root execution, and removes dev-only tooling from runtime.

**Files:**
- Modify: `sandbox/Dockerfile`
- Modify: `sandbox/supervisord.conf`
- Modify: `sandbox/requirements.runtime.txt`
- Modify: `sandbox/README.md`
- Create: `sandbox/.dockerignore`
- Test: `sandbox/tests/test_api_file.py`
- Test: `sandbox/tests/test_service_path_normalization.py`

**Step 1: Write failing image policy checks**

Add checks ensuring:
1. Runtime stage uses non-root user (`USER ubuntu`).
2. Build-only tools are absent in final image: `black`, `flake8`, `pylint`, `mypy`, `bandit`, `pytest`, `pytest-cov`, `pytest-asyncio`, `isort`, `autopep8`, `cyclonedx-bom`.
3. Dev-only npm globals are absent: `prettier`, `eslint`, `typescript`, `jest`, `@types/node`, `@cyclonedx/cyclonedx-npm`, `yarn`.
4. No `NOPASSWD:ALL` in final runtime path.
5. `tini` binary exists at `/usr/bin/tini`.
6. Reference environment packages are present: `libreoffice --version`, `java -version`, `mysql --version`, `graphviz -V`, `code-server --version`.

**Step 2: Implement multi-stage split with reference environment packages**

Stage breakdown:

```dockerfile
# ============================================================
# Stage 1: BUILDER — heavy installs, dev tools, Playwright
# ============================================================
FROM ubuntu:22.04 AS builder
# - Python 3.11 from deadsnakes PPA
# - Node.js 22.13.0 via NVM at /usr/local/nvm
# - Chrome for Testing 128.0.6613.137 at /opt/chrome-for-testing
# - Playwright browsers (chromium, firefox, webkit) via playwright install --with-deps
# - Python dev tools (black, flake8, pylint, mypy, bandit, pytest, etc.) — BUILD ONLY
# - npm dev tools (prettier, eslint, typescript, jest, etc.) — BUILD ONLY
# - Base Python venv template at /opt/base-python-venv (from requirements.runtime.txt)
# - pnpm global tools: @anthropic-ai/mcpb, @mermaid-js/mermaid-cli

# ============================================================
# Stage 2: RUNTIME — production sandbox image
# ============================================================
FROM ubuntu:22.04 AS runtime
```

**Runtime stage APT packages (ordered by category):**

```bash
# Container infrastructure
tini

# Core system tools (already in current Dockerfile)
sudo bc curl wget gnupg ca-certificates socat supervisor
xterm perl xauth x11-xkb-utils xkb-data x11-utils dbus-x11

# VNC/display stack (already in current Dockerfile)
x11vnc websockify xvfb openbox x11-xserver-utils x11-apps xdotool

# Reference environment: productivity & document processing (NEW)
libreoffice poppler-utils graphviz

# Reference environment: code-server web IDE (NEW)
# Install via: curl -fsSL https://code-server.dev/install.sh | sh -s -- --version=4.104.3
code-server

# Reference environment: database & networking (NEW)
mysql-client openssh-server openssh-client net-tools chrony

# Reference environment: system utilities (NEW)
lsof psmisc make patch vim nano xclip xdg-utils

# Reference environment: Java runtime (NEW)
default-jre

# Reference environment: multimedia & graphics (NEW)
gstreamer1.0-plugins-base gstreamer1.0-plugins-good
gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly
gstreamer1.0-libav gstreamer1.0-tools
pulseaudio pulseaudio-utils
vulkan-tools mesa-vulkan-drivers mesa-utils mesa-common-dev
ocl-icd-libopencl1

# Reference environment: X11/GUI enhancements (NEW)
libgtk-3-0 libgtk2.0-0 xinit
xorg-dev xserver-xorg-dev xserver-xorg-core
tcl tk

# Fonts (already in current Dockerfile)
fonts-noto-cjk fonts-noto-color-emoji locales

# Dev tools kept in runtime (already in current Dockerfile)
ripgrep jq git tree zip unzip ffmpeg imagemagick
```

**Copy from builder stage (not re-installed in runtime):**
```dockerfile
COPY --from=builder /opt/chrome-for-testing /opt/chrome-for-testing
COPY --from=builder /opt/base-python-venv /opt/base-python-venv
COPY --from=builder /usr/local/nvm /usr/local/nvm
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin/python3.11 /usr/local/bin/python3.11
# Playwright browser binaries (chromium, firefox, webkit)
COPY --from=builder /home/ubuntu/.cache/ms-playwright /home/ubuntu/.cache/ms-playwright
# pnpm globals (mcpb, mermaid-cli)
COPY --from=builder /home/ubuntu/.local/share/pnpm /home/ubuntu/.local/share/pnpm
```

**NOT copied to runtime (dev-only, stays in builder):**
- Python: black, flake8, pylint, mypy, bandit, pytest, pytest-cov, pytest-asyncio, isort, autopep8, cyclonedx-bom
- npm: prettier, eslint, typescript, jest, @types/node, @cyclonedx/cyclonedx-npm, yarn

**Step 3: Add `tini` as container init process**

`tini` provides proper PID 1 behavior: zombie process reaping, signal forwarding (SIGTERM, SIGINT), and clean shutdown. Without it, supervisord as PID 1 does not reap orphaned zombie processes.

```dockerfile
# Install tini
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*

# Use tini as entrypoint, wrapping supervisord
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]
```

Update `supervisord.conf` to remove `fix_permissions` program (permissions fixed at build time).

**Step 4: Switch to non-root container execution**

Supervisord currently runs as root (entrypoint) but already delegates all child processes to `user=ubuntu` in `supervisord.conf`. The only exception is `fix_permissions` (priority=1, runs once as root).

To eliminate root:
1. Move permission fixes into the Dockerfile `RUN` layer (build-time, not runtime).
2. Remove the `fix_permissions` supervisor program from `supervisord.conf`.
3. Add `USER ubuntu` instruction before `ENTRYPOINT` in Dockerfile.
4. Run supervisord as ubuntu under tini: `ENTRYPOINT ["/usr/bin/tini", "--"]` + `CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"]`.
5. Remove `NOPASSWD:ALL` sudoers entry from runtime stage.
6. Verify all services in `supervisord.conf` still start correctly (all already have `user=ubuntu`; remove the now-redundant `user=` directives or keep for clarity).

> **Note:** Xvfb, x11vnc, openbox, websockify, and both uvicorn instances already run as `user=ubuntu`. No port bindings are below 1024 (ports: 5900, 5901, 8080, 8082, 8222, 9222). This change is safe.

**Step 5: Update npm global versions**

- Update `pnpm` from `10.28.1` to `10.29.2` (match reference environment).
- Remove `yarn` from global install (not in reference; available per-project if needed).

**Step 6: Pin critical binaries (not base image digests)**

- Pin Chrome for Testing version: already pinned to `128.0.6613.137` (keep as-is).
- Pin NVM version: already pinned to `v0.39.7` (keep as-is).
- Pin Node version: already pinned to `22.13.0` (keep as-is).
- Pin code-server: `4.104.3`.
- Base image `ubuntu:22.04`: Use tag, not digest. Digest pinning creates maintenance burden (must update on every security patch). Use `--pull=always` in CI instead.

**Step 7: Build and run sandbox test suite**

```bash
cd /Users/panda/Desktop/Projects/Pythinker
docker build -t pythinker-sandbox:hardened ./sandbox
conda activate pythinker && cd sandbox && pytest -q
```

Verify non-root execution:
```bash
docker run --rm pythinker-sandbox:hardened whoami
# Expected: ubuntu
docker run --rm pythinker-sandbox:hardened id
# Expected: uid=1000(ubuntu) gid=1000(ubuntu) groups=1000(ubuntu)
```

Verify reference environment packages:
```bash
docker run --rm pythinker-sandbox:hardened bash -c "
  libreoffice --version &&
  java -version 2>&1 | head -1 &&
  mysql --version &&
  dot -V 2>&1 &&
  code-server --version | head -1 &&
  tini --version &&
  python3.11 --version &&
  node --version &&
  pnpm --version
"
# Expected: all commands succeed with versions matching reference spec
```

Verify dev tools are ABSENT:
```bash
docker run --rm pythinker-sandbox:hardened bash -c "
  which black 2>/dev/null && echo 'FAIL: black found' || echo 'OK: black absent';
  which flake8 2>/dev/null && echo 'FAIL: flake8 found' || echo 'OK: flake8 absent';
  which eslint 2>/dev/null && echo 'FAIL: eslint found' || echo 'OK: eslint absent';
  which jest 2>/dev/null && echo 'FAIL: jest found' || echo 'OK: jest absent';
  which yarn 2>/dev/null && echo 'FAIL: yarn found' || echo 'OK: yarn absent';
  cat /etc/sudoers.d/ubuntu 2>/dev/null && echo 'FAIL: sudoers found' || echo 'OK: sudoers absent'
"
# Expected: all "OK: ... absent"
```

**Step 8: Commit**

```bash
git add sandbox/Dockerfile sandbox/supervisord.conf sandbox/requirements.runtime.txt sandbox/README.md sandbox/.dockerignore sandbox/tests/test_api_file.py sandbox/tests/test_service_path_normalization.py
git commit -m "feat: convert sandbox image to hardened multi-stage runtime with reference env parity and tini init"
```

---

### Task 5: Seccomp Tightening With Compatibility Gate

**Files:**
- Modify: `sandbox/seccomp-sandbox.json`
- Create: `sandbox/seccomp-sandbox.compat.json`
- Create: `backend/tests/integration/test_sandbox_seccomp_runtime.py`
- Create: `docs/reports/2026-02-13-seccomp-compat-matrix.md`

**Step 1: Audit actually-used syscalls**

Before tightening, collect empirical data on which syscalls are actually invoked during a typical sandbox session:

```bash
# Option A: strace on a running container (requires SYS_PTRACE capability temporarily)
docker exec --privileged pythinker-sandbox-1 strace -f -c -p 1 -o /tmp/strace_summary.txt &
# Run a typical agent session, then stop strace
docker exec pythinker-sandbox-1 cat /tmp/strace_summary.txt

# Option B: Use seccomp audit mode to log blocked syscalls
# Temporarily set defaultAction to SCMP_ACT_LOG and review dmesg/audit logs
```

Document the actually-used syscall set in `docs/reports/2026-02-13-seccomp-compat-matrix.md`.

**Step 2: Write failing seccomp compatibility tests**

Create tests for:
1. Shell tool basic commands pass (ls, cat, python3, node).
2. Browser startup and navigation pass (Chrome + Playwright).
3. File operations pass (read, write, mkdir, chmod).
4. Known dangerous syscalls remain blocked (e.g., `mount`, `reboot`, `kexec_load`, `init_module`).

**Step 3: Split profiles**

1. `seccomp-sandbox.json` — current profile renamed to compat baseline.
2. `seccomp-sandbox.hardened.json` — tightened profile based on audit data, removing syscalls not observed in Step 1.
3. `seccomp-sandbox.compat.json` — copy of current profile for fallback.

**Step 4: Wire profile selection**

Config knob:
1. `SANDBOX_SECCOMP_PROFILE_MODE=hardened|compat`.
2. Default to `compat` initially (Phase A), switch to `hardened` in Phase C.

**Step 5: Execute compatibility matrix**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/integration/test_sandbox_seccomp_runtime.py -v
```

**Step 6: Commit**

```bash
git add sandbox/seccomp-sandbox.json sandbox/seccomp-sandbox.compat.json sandbox/seccomp-sandbox.hardened.json backend/tests/integration/test_sandbox_seccomp_runtime.py docs/reports/2026-02-13-seccomp-compat-matrix.md
git commit -m "feat: introduce hardened and compatibility seccomp profiles with runtime tests"
```

---

### Task 6: Strengthen Agent Runtime State Machine and Cancellation Safety

**Existing State:** The codebase already has substantial lifecycle management:
- `sandbox_pool.py`: Circuit breaker (5 failures, exponential backoff max 300s), orphan reaper, TTL eviction, Docker events monitoring for OOM kills, continuous health checks.
- `agent_domain_service.py`: Session-level locking, parallel sandbox initialization, 20s browser timeout with exponential backoff, deduplication (5-minute window).
- `agent_service.py`: Stale session cleanup, event stream deduplication, fire-and-forget memory extraction on completion.
- `agent_task_runner.py`: Multi-flow routing, tool event enrichment, pending action confirmation for security-sensitive operations.

**Target:** Fix specific edge cases, not rebuild the state machine.

**Files:**
- Modify: `backend/app/application/services/agent_service.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/core/sandbox_pool.py`
- Test: `backend/tests/domain/services/test_agent_task_runner_cleanup.py`
- Test: `backend/tests/application/services/test_agent_service_sandbox_lifecycle.py`
- Test: `backend/tests/application/services/test_agent_service_warmup_cancellation.py`

**Step 1: Investigate and document specific failure modes**

Before writing tests, collect evidence from the monitoring stack (per project debugging workflow):
```bash
# Check for double-stop or stop-after-delete errors
docker logs pythinker-backend-1 --tail 500 2>&1 | grep -iE "already stopped|stop.*after.*delete|double.*stop|invalid.*state.*transition"

# Check for leaked tasks (tasks that never completed)
# Loki: {container_name="pythinker-backend-1"} |= "fire_and_forget" |~ "error|exception|timeout"

# Check sandbox pool acquire/release races
# Prometheus: rate(pythinker_sandbox_health_check_total{status="failed"}[5m])
```

Document the specific failure modes found. If no evidence is found for a failure mode, deprioritize its test.

**Step 2: Write failing idempotency tests for confirmed gaps**

Cover (prioritized by evidence):
1. Double-stop: calling stop on an already-stopped session should be a no-op, not raise.
2. Stop-after-delete: calling stop after sandbox deletion should be a no-op.
3. Warmup cancellation: if a chat request arrives while sandbox is still warming up, the warmup should be cancelled cleanly without orphan connections.
4. Sandbox pool acquire/release under timeout race: acquiring a sandbox that times out during health check should release the slot back to the pool.

**Step 3: Fix confirmed gaps with targeted changes**

Add guards for:
1. Idempotent stop: check state before attempting teardown; return early if already stopped/deleted.
2. Warmup cancellation: track warmup tasks with `asyncio.Task` references; cancel on chat start if still pending.
3. Pool timeout safety: wrap acquire in `asyncio.wait_for` with cleanup in `finally` block.

**Step 4: Enforce bounded retries and task cleanup**

Guarantee all fire-and-forget tasks are tracked via a task registry and exceptions are consumed with structured logging (not silently swallowed).

**Step 5: Run focused tests**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_cleanup.py tests/application/services/test_agent_service_sandbox_lifecycle.py tests/application/services/test_agent_service_warmup_cancellation.py -v
```

**Step 6: Commit**

```bash
git add backend/app/application/services/agent_service.py backend/app/domain/services/agent_task_runner.py backend/app/domain/services/agent_domain_service.py backend/app/core/sandbox_pool.py backend/tests/domain/services/test_agent_task_runner_cleanup.py backend/tests/application/services/test_agent_service_sandbox_lifecycle.py backend/tests/application/services/test_agent_service_warmup_cancellation.py
git commit -m "fix: harden agent runtime state transitions and cancellation safety"
```

---

### Task 7: Enhance Pre-Execution Security Critic Gates

**Existing State:** `security_critic.py` already implements:
- Static pattern detection: `os.system`, `subprocess` with `shell=True`, `eval`, `exec`, and more.
- LLM-based semantic analysis for complex threats.
- Risk level classification: SAFE, LOW, MEDIUM, HIGH, CRITICAL.
- PII and credential detection.
- Language-specific rules (Python vs Bash).

`guardrails.py` already implements:
- InputGuardrails: injection attacks, jailbreaks, ambiguity, sensitive data.
- OutputGuardrails: content leakage, harmful output, relevance, consistency.
- Enhanced PII detection (SSN, credit cards, API keys, AWS credentials, private keys).

**Target:** Enhance the existing critic to enforce it as a **mandatory hard gate** before execution (currently it may be advisory-only), add new detection patterns, and wire audit telemetry.

**Files:**
- Modify: `backend/app/domain/services/agents/security_critic.py`
- Modify: `backend/app/domain/services/agents/guardrails.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Test: `backend/tests/domain/services/agents/test_security_critic.py`
- Create: `backend/tests/domain/services/agents/test_execution_security_gate.py`

**Step 1: Verify current enforcement behavior**

Before writing tests, check whether the security critic is currently:
- A hard gate (blocks execution) or advisory (logs warning, continues).
- Called for ALL tool executions or only specific ones.
- Consistently invoked in all execution paths (PlanActFlow, DiscussFlow, CoordinatorFlow).

```bash
# Search for how security_critic is called in execution paths
cd /Users/panda/Desktop/Projects/Pythinker
rg -n "security_critic|SecurityCritic" backend/app/domain/services/agents/ -S
```

**Step 2: Write failing gate tests for new enforcement**

Add tests where dangerous shell/code operations:
1. Are blocked before sandbox execution when risk is CRITICAL or HIGH.
2. Emit structured violation events (not just log lines).
3. Return actionable user-safe errors (not raw exceptions).
4. Medium risk requires explicit override flag in development mode (`SECURITY_CRITIC_ALLOW_MEDIUM_RISK=true`).

**Step 3: Enhance critic with new patterns**

New patterns to detect (beyond existing set):
1. Container escape attempts: `nsenter`, `unshare`, `/proc/*/ns/*`, `docker.sock` access.
2. Network exfiltration: `curl` to internal metadata endpoints (`169.254.169.254`), reverse shells.
3. Privilege escalation: `chmod +s`, `chown root`, writing to `/etc/passwd` or `/etc/sudoers`.
4. Crypto mining indicators: known mining pool domains, `stratum+tcp://` URLs.

**Step 4: Wire mandatory gate into execution pipeline**

Ensure the critic is called as a hard gate in `execution.py` before dispatching to sandbox. If the critic returns HIGH or CRITICAL, the execution must be blocked and a structured `SecurityViolationEvent` emitted.

**Step 5: Add audit telemetry**

Add to `prometheus_metrics.py` (extend existing metrics, do not duplicate):
1. `pythinker_security_gate_blocks_total` (labels: `risk_level`, `pattern_type`).
2. `pythinker_security_gate_overrides_total` (labels: `override_reason`).

**Step 6: Run tests**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/agents/test_security_critic.py tests/domain/services/agents/test_execution_security_gate.py -v
```

**Step 7: Commit**

```bash
git add backend/app/domain/services/agents/security_critic.py backend/app/domain/services/agents/guardrails.py backend/app/domain/services/agents/execution.py backend/tests/domain/services/agents/test_security_critic.py backend/tests/domain/services/agents/test_execution_security_gate.py
git commit -m "feat: enforce security critic as mandatory execution gate with audit metrics"
```

---

### Task 8: Add Runtime Isolation Modes (Rootless/Userns-Remap) Playbook

**Files:**
- Create: `docs/guides/DOCKER_ROOTLESS_USERNS_PLAYBOOK.md`
- Modify: `docker-compose-development.yml`
- Modify: `docker-compose.dokploy.yml`
- Modify: `.env.example`
- Test: `backend/tests/core/test_config.py`

**Step 1: Add configurable daemon/runtime mode flags**

Env additions:
1. `DOCKER_ISOLATION_MODE=standard|userns-remap|rootless`.
2. `SANDBOX_SECURITY_PROFILE=compat|hardened`.

**Step 2: Document host prerequisites and limitations**

Include:
1. Socket path differences for rootless (`$XDG_RUNTIME_DIR/docker.sock` vs `/var/run/docker.sock`).
2. Performance and compatibility caveats (rootless has no kernel module loading, limited networking).
3. Chrome for Testing compatibility with rootless Docker.
4. Rollback instructions (switch back to standard mode).

**Step 3: Add config parsing tests**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/core/test_config.py -v
```

**Step 4: Commit**

```bash
git add docs/guides/DOCKER_ROOTLESS_USERNS_PLAYBOOK.md docker-compose-development.yml docker-compose.dokploy.yml .env.example backend/tests/core/test_config.py
git commit -m "docs: add rootless and userns-remap isolation playbook with config flags"
```

---

### Task 9: Security + Reliability Observability and Alerting

**Existing State:** `prometheus_metrics.py` already has 12+ organized metric groups covering: LLM, Tool, Session, Screenshot, Browser, Sandbox, Circuit Breaker, Cache, Token Budget, Delivery Integrity, HTTP Pool, and Qdrant. The sandbox group already includes `sandbox_health_check_total`, `sandbox_oom_kills_total`, `sandbox_runtime_crashes_total`.

**Target:** Add only the **net-new metrics** needed for hardening observability. Do not duplicate existing metrics.

**Files:**
- Modify: `backend/app/infrastructure/observability/prometheus_metrics.py`
- Modify: `prometheus/alert_rules.yml`
- Modify: `grafana/dashboards/pythinker-agent-enhancements.json`
- Modify: `MONITORING.md`
- Test: `backend/tests/infrastructure/observability/test_agent_metrics.py`

**Step 1: Write failing metric coverage tests for NEW metrics only**

Add tests for these net-new counters/histograms:
1. `pythinker_security_gate_blocks_total` (labels: `risk_level`, `pattern_type`) — from Task 7.
2. `pythinker_security_gate_overrides_total` (labels: `override_reason`) — from Task 7.
3. `pythinker_task_cancellation_leaks_total` — fire-and-forget tasks that weren't properly cleaned up.
4. `pythinker_sandbox_policy_violations_total` (labels: `violation_type`) — policy contract violations caught at creation time.

Do NOT add metrics that already exist in the sandbox, circuit breaker, or browser metric groups.

**Step 2: Add alerts**

Rules:
1. `SandboxCreationFailureBurst`: `rate(pythinker_sandbox_health_check_total{status="failed"}[5m]) > 0.5` — burst of sandbox failures.
2. `BrowserReconnectStorm`: `rate(pythinker_sandbox_connection_attempts_total[5m]) > 2` — repeated forced browser reconnects.
3. `SecurityBlockRatioRising`: `rate(pythinker_security_gate_blocks_total[15m]) > 0.1` — rising security block ratio.

**Step 3: Validate dashboards and alert syntax**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/infrastructure/observability/test_agent_metrics.py -v
promtool check rules prometheus/alert_rules.yml
```

**Step 4: Commit**

```bash
git add backend/app/infrastructure/observability/prometheus_metrics.py prometheus/alert_rules.yml grafana/dashboards/pythinker-agent-enhancements.json MONITORING.md backend/tests/infrastructure/observability/test_agent_metrics.py
git commit -m "feat: add hardening telemetry and alerts for sandbox and agent safety"
```

---

### Task 10: End-to-End Hardening Verification and Regression Gate

**Files:**
- Create: `docs/reports/2026-02-13-hardening-verification-report.md`
- Modify: `AGENTS.md` (verification checklist section if needed)
- Modify: `README.md` (security profile usage)

**Step 1: Run full required checks**

```bash
cd frontend && bun run lint && bun run type-check
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

**Step 2: Run focused integration checks**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/integration/test_agent_e2e.py tests/integration/test_sandbox_oom_e2e.py tests/integration/test_sandbox_http_pooling.py -v
```

**Step 3: Verify non-root execution and tini init in built image**

```bash
docker build -t pythinker-sandbox:hardened ./sandbox
docker run --rm pythinker-sandbox:hardened whoami  # Expected: ubuntu
docker run --rm pythinker-sandbox:hardened cat /etc/sudoers.d/ubuntu  # Expected: file not found or no NOPASSWD
docker run --rm pythinker-sandbox:hardened tini --version  # Expected: tini version 0.19.0
```

**Step 4: Verify reference environment parity**

```bash
docker run --rm pythinker-sandbox:hardened bash -c "
  libreoffice --version &&
  java -version 2>&1 | head -1 &&
  mysql --version &&
  dot -V 2>&1 &&
  code-server --version | head -1 &&
  python3.11 --version &&
  node --version &&
  pnpm --version &&
  pdftotext -v 2>&1 | head -1
"
# Expected: all commands succeed with versions matching reference spec

# Verify dev tools are ABSENT
docker run --rm pythinker-sandbox:hardened bash -c "
  which black flake8 eslint jest yarn 2>/dev/null | wc -l
"
# Expected: 0 (none found)
```

**Step 5: Verify security controls in running container**

```bash
docker inspect pythinker-sandbox-1 | jq '.[0].HostConfig | {Privileged, ReadonlyRootfs, SecurityOpt, CapDrop, CapAdd, PidsLimit, Memory, NanoCpus}'
# Expected: Privileged=false, SecurityOpt includes no-new-privileges and seccomp, CapDrop=["ALL"], CapAdd=[only allowlisted]
```

**Step 6: Record final security posture**

Document:
1. What is hardened and enforced (before/after comparison with Task 1 baseline).
2. What remains in compatibility mode and why.
3. Explicit rollback commands for each hardening layer.
4. Chrome `--no-sandbox` rationale: documented as intentionally correct.
5. Reference environment parity: which packages are aligned, any intentional deviations.

**Step 7: Commit final report**

```bash
git add docs/reports/2026-02-13-hardening-verification-report.md AGENTS.md README.md
git commit -m "docs: publish hardening verification report and operator guidance"
```

---

## Rollout Strategy

1. **Phase A:** Ship policy contract + observability first (no behavior change). Tasks 1, 2, 9.
2. **Phase B:** Enable hardened profile in CI and staging-equivalent local stack. Tasks 3, 4, 5. Dev compose gets security controls. Sandbox image becomes multi-stage + non-root. Seccomp starts in compat mode.
3. **Phase C:** Make hardened profile default; keep compat profile as explicit fallback. Tasks 6, 7, 8. Agent lifecycle hardened. Security critic becomes mandatory gate. Seccomp switches to hardened. Task 10 validates everything.

## Rollback Strategy

1. Set `SANDBOX_SECURITY_PROFILE=compat` — disables hardened compose controls.
2. Set `SANDBOX_SECCOMP_PROFILE_MODE=compat` — reverts to broad syscall allowlist.
3. Set `SECURITY_CRITIC_ALLOW_MEDIUM_RISK=true` — relaxes critic gate for incident mitigation.
4. Revert Dockerfile: `git checkout sandbox/Dockerfile` — restores single-stage build with root execution.

## Completion Definition

1. All required frontend/backend checks pass (`bun run lint`, `bun run type-check`, `ruff check`, `ruff format --check`, `pytest tests/`).
2. Hardening report documents measured before/after posture with `docker inspect` evidence.
3. No orphan sandbox leaks in teardown stress tests.
4. No unresolved P0 security or lifecycle regressions.
5. Chrome `--no-sandbox` documented as architecturally correct (not a gap).
6. Non-root container execution verified (`whoami` returns `ubuntu`).
7. Reference environment parity verified — all packages from the specification are present in runtime image (`libreoffice`, `java`, `mysql`, `graphviz`, `code-server`, `tini`, `poppler-utils`, etc.).
8. Dev-only tools verified absent from runtime (`black`, `flake8`, `eslint`, `jest`, `yarn`, `NOPASSWD` sudoers).
9. `tini` init verified as PID 1 (`docker exec <container> ps -p 1 -o comm=` returns `tini`).
