# Seccomp Compatibility Matrix

**Date:** 2026-02-13  
**Context:** Task 5 — Seccomp tightening with compatibility gate

---

## Profile Layout

| Profile | Path | Purpose |
|---------|------|---------|
| Default (compose) | `sandbox/seccomp-sandbox.json` | Primary profile used by compose files |
| Compat | `sandbox/seccomp-sandbox.compat.json` | Fallback; identical copy for explicit selection |
| Hardened | `sandbox/seccomp-sandbox.hardened.json` | Tightened profile (Phase C); currently identical to compat |

---

## Configuration

- `SANDBOX_SECCOMP_PROFILE_MODE=compat|hardened` — default `compat`
- `SANDBOX_SECCOMP_PROFILE` — override with explicit path (takes precedence)
- Dynamic sandbox creation uses policy service resolution; compose uses `seccomp:./sandbox/seccomp-sandbox.json`

---

## Syscall Audit Status

**Phase A:** Empirical strace/audit not yet run. The compat profile contains ~230 allowed syscalls with `defaultAction: SCMP_ACT_ERRNO`. Any syscall not in the allowlist is blocked.

**Known dangerous syscalls:** `reboot`, `kexec_load`, `init_module`, `delete_module` are not in the allowlist and remain blocked by default. `mount` is currently allowed (in the first syscall block); consider removing for hardened profile in Phase C.

**clone/clone3:** `clone` is allowed with restricted flags (CLONE_NEWUSER masked out). `clone3` returns ENOSYS (38) to prevent namespace escapes.

---

## Compatibility Tests

`backend/tests/integration/test_sandbox_seccomp_runtime.py` verifies:

1. Shell tool: `ls`, `cat`, `python3`, `node` (basic commands)
2. Browser: Chrome + Playwright startup
3. File ops: read, write, mkdir, chmod
4. Blocked: `mount`, `reboot`, `kexec_load` remain blocked

Tests require a running sandbox and skip if unavailable.
