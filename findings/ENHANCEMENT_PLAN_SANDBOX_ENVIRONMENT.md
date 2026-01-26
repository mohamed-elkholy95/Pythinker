# Enhancement Plan: Sandbox Environment Hardening and Inventory

## 1. Overview

This plan outlines targeted improvements to the sandbox environment using the baseline captured in `findings/SANDBOX_ENVIRONMENT_REPORT.md` (January 26, 2026). The focus is on reproducibility, security hardening, dependency governance, and operational observability.

---

## 2. Current State Summary (From Report)

- **OS**: Ubuntu 22.04.5 LTS (Jammy) on x86_64.
- **Runtime**: Python 3.11.0rc1 and Node.js v22.13.0.
- **Tooling**: Git, GitHub CLI, Chromium, code-server, ffmpeg, standard CLI utilities.
- **Packages**: Broad Python and Node package inventory for data, web, and document workflows.
- **Manus utilities**: Render/convert/transcribe/upload/export tooling.

---

## 3. Gap and Risk Analysis

1. **Reproducibility Gaps**
   - No pinned package manifests in the report (pip/apt/pnpm).
   - No SBOM or image digest tracking; difficult to attest or roll back.

2. **Security Posture Gaps**
   - Sensitive environment variables can leak via logs, reports, or process listings.
   - Sandbox runtime likely runs privileged tooling (browser automation, VNC) without a hardening profile.
   - No explicit mention of container security controls (seccomp/AppArmor, dropped capabilities, read-only FS).

3. **Operational Observability Gaps**
   - No persistent, structured inventory or health diagnostics beyond manual commands.
   - No standard logging or metrics export for service readiness, disk pressure, or process health.

4. **Runtime Stability Gaps**
   - Python version is a release candidate; may increase compatibility and security risk.
   - Package sprawl risks dependency conflicts and image bloat.

---

## 4. Proposed Enhancements

### 4.1. Inventory and Provenance

- **Add automatic inventory generation** during image build and runtime.
- **Produce SBOM** (CycloneDX or SPDX) for OS + Python + Node dependencies.
- **Track image digests** and build metadata (timestamp, git SHA, build pipeline).

### 4.2. Dependency Governance

- **Pin base image** (explicit digest) and core runtime versions.
- **Lock Python deps** via `requirements.txt` + `pip-compile` or Poetry lock.
- **Lock Node deps** via `pnpm-lock.yaml` for global toolchain and script installs.
- **Upgrade Python** to stable 3.11.x or 3.12.x and validate package compatibility.

### 4.3. Security Hardening

- **Restrict environment exposure** with allowlist-based env passthrough and redaction in reports.
- **Reduce container privileges**: drop Linux capabilities, use non-root user where possible.
- **Enable security profiles**: AppArmor/SELinux + seccomp profile tailored for Chrome and tooling.
- **Filesystem controls**: read-only root where feasible, writable temp mounts with quotas.

### 4.4. Observability and Health

- **Health endpoints** that report service readiness (API, VNC, Chrome, ws proxy).
- **Structured logs** with sanitized environment info and inventory hashes.
- **Metrics hooks** for CPU/memory/disk saturation and Chrome process restarts.

### 4.5. Operational Guardrails

- **TTL enforcement** with grace periods and warning logs before termination.
- **Resource limits** (cgroups) per sandbox to avoid noisy neighbor issues.
- **Network egress policy** for optional allowlist/denylist enforcement.

---

## 5. Implementation Steps

1. **Inventory Script**
   - Add `sandbox/scripts/collect_inventory.sh` to output OS, CPU, disk, memory, package lists, and versions.
   - Add Python/Node inventory export (`pip freeze`, `pnpm list -g`) with redaction.

2. **SBOM Generation**
   - Add SBOM build step in `sandbox/Dockerfile` or CI pipeline.
   - Store SBOM artifacts under `sandbox/artifacts/` with build metadata.

3. **Runtime Hardening**
   - Update `sandbox/Dockerfile` to create a non-root user and drop privileges.
   - Update `sandbox/supervisord.conf` to run services with least privilege.

4. **Dependency Locking**
   - Adopt `requirements.txt` lock with hashes or add `requirements.lock`.
   - Pin Node and global tools in a dedicated install script with explicit versions.

5. **Observability Additions**
   - Add a `/health` route in `sandbox/app/main.py` with per-service checks.
   - Emit structured JSON logs for inventory hashes and version metadata.

6. **Sandbox Policy Controls**
   - Extend environment config to support allowlisted env vars and redaction.
   - Add a secure defaults section in `sandbox/README.md`.

---

## 6. Testing Criteria

- **Inventory**: Inventory script produces a stable, redacted report on every build.
- **SBOM**: Generated SBOM matches installed packages and is stored per image build.
- **Security**: Non-root processes verified; capabilities and seccomp profile active.
- **Stability**: Chrome + API services are healthy after 100+ restart cycles.
- **Performance**: Image size reduced or stable after lockfile introduction.

---

## 7. Deliverables

- `findings/SANDBOX_ENVIRONMENT_REPORT.md` (baseline report).
- `findings/ENHANCEMENT_PLAN_SANDBOX_ENVIRONMENT.md` (this plan).
- `sandbox/scripts/collect_inventory.sh` and supporting documentation (planned).
- Updated `sandbox/README.md` with security posture and inventory workflow (planned).

---

*Document Version: 1.0.0*
*Last Updated: January 26, 2026*
*Author: Pythinker Enhancement Team*
