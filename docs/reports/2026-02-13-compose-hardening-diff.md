# Compose Hardening Diff

**Date:** 2026-02-13  
**Context:** Task 3 — Harden Compose Runtime Defaults

---

## Summary

Development compose (`docker-compose-development.yml`) previously had no security controls. This was aligned with production and Dokploy compose files.

---

## Changes Applied

### docker-compose-development.yml — Sandbox Service

**Added:**
```yaml
# Security hardening: align dev with production baseline (2026-02-13)
# Chrome --no-sandbox is correct: container provides cap_drop+seccomp+no-new-privileges isolation
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

**Before:** Sandbox ran with full container privileges (no security_opt, no cap_drop/cap_add).

**After:** Same baseline as production and Dokploy.

---

### docker-compose.yml — No Changes

Already hardened with `security_opt`, `cap_drop`, `cap_add`, `tmpfs`, `ulimits`, resource limits.

### docker-compose.dokploy.yml — No Changes

Already hardened with equivalent controls for both `sandbox` and `sandbox2`.

---

## Chrome `--no-sandbox` Rationale

Chrome is launched with `--no-sandbox` and `--disable-setuid-sandbox`. This is **architecturally correct** when:

1. The container enforces `cap_drop: ALL`, custom seccomp, and `no-new-privileges`.
2. Chrome's inner sandbox relies on syscalls/namespaces that conflict with container restrictions.
3. Delegating isolation to the container follows the documented Playwright/Docker pattern.

---

## Verification

- `backend/tests/core/test_compose_hardening.py` — 12 tests assert all compose files enforce the baseline.
- `backend/tests/integration/test_sandbox_http_pooling.py` — HTTP pooling integration.
- `backend/tests/core/test_sandbox_lifecycle_mode.py` — Lifecycle mode config.
