# Enhancement Plan: Sandbox Implementation Alignment (Sandbox_env Baseline)

## 1. Overview

This plan reviews the current sandbox implementation and outlines enhancements to align it with the baseline captured in `Sandbox_env/` (January 26, 2026). The focus is on runtime parity, security hardening, reproducibility, and operational observability.

---

## 2. Current State Summary (Sandbox_env + Repo)

**Baseline from `Sandbox_env/`:**
- **OS**: Ubuntu 22.04 (x86_64).
- **Python**: 3.11.0rc1.
- **Node.js**: v22.13.0 (NVM).
- **Core tools**: Git 2.34.1, GH CLI 2.81.0, Chromium 128, ffmpeg, code-server 4.104.3.
- **Global npm/pnpm**: `@anthropic-ai/mcpb`, `@mermaid-js/mermaid-cli`, `yarn`.
- **Python packages**: fastapi/uvicorn stack, playwright 1.55.0, data + document tooling (pandas, matplotlib, weasyprint, reportlab, boto3, etc.).
- **Env vars**: includes OTEL, code-server, runtime endpoints, and **plaintext secrets** (API keys/passwords).

**Current repo sandbox implementation:**
- `sandbox/Dockerfile` uses **Python 3.10.12** and **Node 20.x** (no NVM/pnpm, no code-server/gh in image).
- `sandbox/app/services/shell.py` and `sandbox/app/services/file.py` do not use `SecurityManager` for path/command validation.
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py` creates containers without the hardening settings present in `docker-compose.yml` (seccomp, cap drop, tmpfs, ulimits, shm size, resource limits).
- `sandbox/supervisord.conf` runs Chromium with `--no-sandbox` and as root.
- Websocket/VNC port mismatch: websockify uses **5901**, compose exposes **6080**.

---

## 3. Gap and Risk Analysis

1. **Runtime Drift**
   - Python/Node versions differ from baseline (3.10 vs 3.11; 20.x vs 22.13).
   - Missing NVM/pnpm global tooling and code-server.
   - Python package set in the base venv diverges from `Sandbox_env/pip_packages.txt`.

2. **Security Risks**
   - `Sandbox_env/env_vars.txt` contains plaintext secrets (API keys, passwords).
   - Shell and file operations allow unrestricted paths/commands and support `sudo` without allowlists.
   - Chromium runs with `--no-sandbox` and `--disable-setuid-sandbox`.
   - Docker SDK container creation lacks seccomp/cap-drop/ulimits/tmpfs/resource limits.
   - Dockerfile uses `AllowUnauthenticated` apt flags.

3. **Operational/Observability Gaps**
   - No automated inventory generation matching `Sandbox_env/` layout.
   - No SBOMs or drift detection.
   - Health checks do not validate Chrome/VNC/websockify readiness.

4. **Compatibility Gaps**
   - Port mismatch for websocket access (5901 vs 6080).
   - Missing baseline tooling (code-server, pnpm globals).

---

## 4. Proposed Enhancements

### 4.1 Runtime Parity & Package Governance
- Align **Python 3.11.x** (stable) and **Node 22.13.x** (via NVM).
- Install **pnpm**, **yarn**, `@anthropic-ai/mcpb`, `@mermaid-js/mermaid-cli`.
- Add **code-server** and **gh** to the image to match baseline capabilities.
- Expand base venv packages to match `Sandbox_env/pip_packages.txt` and introduce lockfiles (pip-compile/uv/poetry).
- Pin apt packages and repos (snapshot or explicit versions).

### 4.2 Security Hardening
- Wire `SecurityManager` into shell + file services:
  - Path allowlist enforcement (`/workspace`, `/tmp`, `/home/ubuntu`).
  - Command sanitization/denylist for dangerous patterns.
  - Gate `sudo` behind an admin-only flag or disable by default.
- Enforce env var allowlist and redact secrets from inventory/logs.
- Remove unauthenticated apt flags; use signed repos and verified keys.
- Run Chromium under `ubuntu` and re-enable sandboxing if possible (user namespaces + seccomp profile).

### 4.3 Container Hardening Consistency
- Mirror docker-compose hardening in Docker SDK creation:
  - `security_opt`, `cap_drop`, `tmpfs`, `ulimits`, `shm_size`, resource limits.
- Standardize websocket port (choose 5901 or 6080) across `supervisord.conf`, `docker-compose.yml`, and `DockerSandbox.vnc_url`.

### 4.4 Observability & Inventory
- Add `sandbox/scripts/collect_inventory.sh` that outputs:
  - `apt_packages.txt`, `pip_packages.txt`, `npm_packages.txt`, `env_vars.txt` (redacted), `system_info.txt`.
- Generate SBOMs (CycloneDX) for OS + pip + npm.
- Extend `/health` to report Chrome/VNC/websockify readiness.

### 4.5 Feature Parity Extensions (Optional)
- Evaluate introducing baseline “manus”-style utilities as optional plugins.
- Add a lightweight CLI registry for extra runtime tools.

---

## 5. Implementation Steps

1. **Inventory + Redaction**
   - Implement `sandbox/scripts/collect_inventory.sh` and a redaction filter for secrets.

2. **Dockerfile Alignment**
   - Update to Python 3.11.x + Node 22.13.x (NVM), pnpm/yarn, code-server, gh.
   - Remove `AllowUnauthenticated` and pin apt sources.
   - Extend base venv to match Sandbox_env package list; add lockfile workflow.

3. **Security Integration**
   - Apply `SecurityManager` in `shell.py` and `file.py` (path + command validation).
   - Add env allowlist + sanitize logs.

4. **Chrome & Supervisor**
   - Run Chromium as `ubuntu`; evaluate re-enabling sandbox.
   - Align websocket port exposure and update docs.

5. **Docker SDK Hardening**
   - Match docker-compose security options in `DockerSandbox._create_task`.

6. **Observability**
   - Add service health probes for Chrome/VNC/websockify.
   - Produce SBOM artifacts on build.

7. **Docs + Tests**
   - Update `sandbox/README.md` with new security posture and inventory workflow.
   - Add tests for path/command restrictions and inventory redaction.

---

## 6. Testing Criteria

- **Version parity**: `python3 --version`, `node --version`, `pnpm list -g` match baseline targets.
- **Security**: unsafe paths/commands are rejected; `sudo` blocked by default.
- **Ports**: websocket endpoint reachable and consistent with `vnc_url`.
- **Hardening**: SDK-created containers apply seccomp/cap-drop/ulimits/tmpfs.
- **Inventory**: generated reports match `Sandbox_env/` format and redact secrets.
- **Health**: `/health` reflects Chrome/VNC/websockify readiness.

---

## 7. Deliverables

- `findings/ENHANCEMENT_PLAN_SANDBOX_IMPLEMENTATION.md` (this document).
- `sandbox/scripts/collect_inventory.sh` + docs (planned).
- Updated `sandbox/Dockerfile`, `sandbox/supervisord.conf`, `docker-compose.yml`.
- Updated `backend/app/infrastructure/external/sandbox/docker_sandbox.py`.
- Updated `sandbox/app/services/shell.py` and `sandbox/app/services/file.py`.
- CI SBOM + inventory checks.

---

*Document Version: 1.0.0*
*Last Updated: January 26, 2026*
*Author: Pythinker Enhancement Team*
