# Hardening Verification Report

**Date:** 2026-02-13  
**Context:** Task 10 — End-to-end hardening verification

---

## Summary

Tasks 1–10 of the Agent Robustness + Docker Sandbox Hardening plan have been implemented.

---

## What Is Hardened and Enforced

| Layer | Controls | Evidence |
|-------|----------|----------|
| Container runtime | `security_opt: no-new-privileges`, `cap_drop: ALL`, `seccomp` profile | All compose files |
| Sandbox image | Multi-stage build, `USER ubuntu`, tini init | `sandbox/Dockerfile` |
| Seccomp | compat/hardened profile split, `SANDBOX_SECCOMP_PROFILE_MODE` | `sandbox/seccomp-sandbox.*.json` |
| Security critic | Mandatory gate for code_executor and shell | Blocks CRITICAL/HIGH; MEDIUM via override |
| Agent lifecycle | Idempotent teardown, warmup cancellation | `agent_domain_service.py`, `agent_service.py` |

---

## Compatibility Mode

- **Seccomp:** `compat` profile used by default; `hardened` identical for Phase A (will tighten in Phase C).
- **Chrome `--no-sandbox`:** Documented as correct—container-level isolation (seccomp + cap_drop + no-new-privileges) provides equivalent sandboxing; Chrome’s inner sandbox conflicts with container isolation.

---

## Rollback Commands

```bash
# Revert to compat compose controls
SANDBOX_SECURITY_PROFILE=compat

# Revert seccomp to broad allowlist
SANDBOX_SECCOMP_PROFILE_MODE=compat

# Relax security critic for MEDIUM risk (incident mitigation)
SECURITY_CRITIC_ALLOW_MEDIUM_RISK=true
```

---

## Verification Checklist

1. [x] Non-root execution: `docker run --rm pythinker-sandbox:hardened whoami` → `ubuntu`
2. [x] Tini init: `docker run --rm pythinker-sandbox:hardened tini --version`
3. [x] Security controls in compose: `security_opt`, `cap_drop`, `seccomp`
4. [x] Security critic blocks dangerous code/shell
5. [x] Prometheus metrics: `pythinker_security_gate_blocks_total`, `security_gate_overrides_total`

---

## Reference Environment Parity

Runtime packages from the specification: `tini`, `poppler-utils`, `graphviz`, `mysql-client`, `lsof`, `psmisc`. Dev tools (`black`, `flake8`, `eslint`, `jest`, `yarn`) are not in the runtime image.
