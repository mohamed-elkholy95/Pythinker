# Docker Hardening Baseline

**Date:** 2026-02-13  
**Context:** Pythinker agent robustness and Docker sandbox hardening  
**Reference:** `docs/plans/2026-02-13-agent-robustness-docker-sandbox-hardening-plan.md`

---

## Runtime Configuration Inventory (Step 1)

Grep inventory run 2026-02-13:

```bash
rg -n "no-new-privileges|cap_drop|cap_add|seccomp|read_only|tmpfs|user:|privileged|--no-sandbox|--disable-setuid-sandbox|shm_size|pids" docker-compose*.yml sandbox/Dockerfile -S
```

### Findings

| File | security_opt | cap_drop | cap_add | seccomp | tmpfs | pids | --no-sandbox |
|------|--------------|----------|---------|---------|-------|------|--------------|
| docker-compose.yml | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| docker-compose.dokploy.yml | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| docker-compose-development.yml | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |

**docker-compose-development.yml** has tmpfs, pids (via deploy.resources.limits), and Chrome args, but **no** `security_opt`, `cap_drop`, or `cap_add`. Development runs with full container privileges.

---

## Live Container Security Settings (Step 2)

```bash
docker inspect pythinker-sandbox-1 | jq '.[0].HostConfig | {Privileged, ReadonlyRootfs, SecurityOpt, CapDrop, CapAdd, PidsLimit, Memory, NanoCpus}'
```

### Observed (Development Sandbox, 2026-02-13)

```json
{
  "Privileged": false,
  "ReadonlyRootfs": false,
  "SecurityOpt": null,
  "CapDrop": null,
  "CapAdd": null,
  "PidsLimit": 300,
  "Memory": 4294967296,
  "NanoCpus": 1500000000
}
```

**Interpretation:** `pythinker-sandbox-1` is the development compose sandbox. `SecurityOpt`, `CapDrop`, and `CapAdd` are `null` — no security controls applied. Resource limits (memory, cpus, pids) are enforced.

---

## Existing Hardening (Production / Dokploy Compose)

Production `docker-compose.yml` and `docker-compose.dokploy.yml` enforce:

| Control | Value |
|---------|-------|
| security_opt | `no-new-privileges:true`, `seccomp:./sandbox/seccomp-sandbox.json` |
| cap_drop | `ALL` |
| cap_add | `CHOWN`, `SETGID`, `SETUID`, `NET_BIND_SERVICE`, `SYS_CHROOT` |
| tmpfs | `/run:size=50M`, `/tmp:size=300M`, `/home/ubuntu/.cache:size=150M,...` |
| ulimits | nofile 65536, nproc 4096/8192 |
| shm_size | 2gb (production/dokploy), 3gb (dev) |
| deploy.resources | memory 3G, cpus 1.5, pids 300; reservations memory 768M |

---

## Gaps vs. Target Baseline

| Gap | Location | Target |
|-----|----------|--------|
| No security_opt | docker-compose-development.yml | Add no-new-privileges, seccomp |
| No cap_drop/cap_add | docker-compose-development.yml | Add cap_drop: ALL, cap_add allowlist |
| Single-stage Dockerfile | sandbox/Dockerfile | Multi-stage, non-root runtime (Task 4) |
| Root execution | sandbox/Dockerfile | `USER ubuntu`, tini init (Task 4) |
| NOPASSWD:ALL | sandbox/Dockerfile | Remove from runtime (Task 4) |
| Dev tools in runtime | sandbox/Dockerfile | Move to builder stage only (Task 4) |
| Scattered policy | config, docker_sandbox | Centralized policy contract (Task 2) |
| read_only | Not applied | Deferred for sandbox; revisit after Task 4 |

---

## Chrome `--no-sandbox` Documentation

Chrome is launched with:

```
--no-sandbox --disable-setuid-sandbox --disable-crashpad --user-data-dir=/tmp/chrome
```

**Rationale:** When the container enforces `cap_drop: ALL`, custom seccomp, and `no-new-privileges`, Chrome's inner sandbox is redundant. Chrome's sandbox uses `clone()`, `setuid`, and PID namespaces that can conflict with container restrictions. Disabling Chrome's sandbox delegates isolation to the container, which is the documented Playwright/Docker pattern. This is **intentionally correct**, not a security gap.

---

## Before/After Summary (For Task 10)

| Metric | Before (2026-02-13) | After (Post-Plan) |
|--------|----------------------|-------------------|
| Dev compose security | None | Same as production |
| Sandbox user | root | ubuntu (non-root) |
| Init process | supervisord (PID 1) | tini → supervisord |
| Policy contract | Scattered | Centralized |
| Security critic | Advisory? | Mandatory gate |
| Seccomp profile | Single broad | compat + hardened modes |
