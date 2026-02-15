# Pythinker Deep Audit Report (Playbook-Aligned)

Date: 2026-02-15
Scope: `backend/`, `frontend/`, `sandbox/`, compose/runtime configs
Reference baseline: `Playbook.md`

## Audit Method
- Reviewed `Playbook.md` architecture/runtime expectations.
- Ran automated quality gates:
  - `cd backend && conda run -n pythinker ruff check .`
  - `cd backend && conda run -n pythinker pytest tests/`
  - `cd frontend && bun run lint`
  - `cd frontend && bun run type-check`
- Performed targeted code-path inspection for:
  - Sandbox warmup/readiness flow
  - Session/SSE/WebSocket routes
  - Adaptive model routing path
  - Core settings/config correctness

## Executive Summary
- `Playbook.md` describes a stable FastAPI+SSE+sandbox runtime, but current backend has **blocking reliability regressions** in sandbox readiness and **failing backend quality gates**.
- Highest-impact production/dev-runtime issue: sandbox warmup incorrectly requires a mutually-exclusive supervisor service to be `RUNNING`, causing repeated warmup loops and delayed/broken session startup.
- CI/validation confidence is reduced: backend test collection fails early, and backend lint gate is currently red.

---

## Findings (Ordered by Severity)

## 1) Critical: Sandbox readiness logic blocks on an intentionally disabled supervisor process
- Severity: Critical
- Impact:
  - Session initialization can stall for ~80s+ and fail unpredictably.
  - Users observe long waits/initialization loops and unstable startup behavior.
- Evidence:
  - Readiness logic requires all non-exception services to be `RUNNING`.
  - `chrome_cdp_only` is intentionally skipped in dual mode and reaches `FATAL`, but is still treated as a required running service.
  - Recent runtime logs showed repeated: `Waiting for services... Non-running: chrome_cdp_only(FATAL)`.
- Code references:
  - `backend/app/infrastructure/external/sandbox/docker_sandbox.py:451`
  - `backend/app/infrastructure/external/sandbox/docker_sandbox.py:466`
  - `backend/app/infrastructure/external/sandbox/docker_sandbox.py:472`
  - `sandbox/supervisord.conf:75`
  - `sandbox/supervisord.conf:76`
  - `sandbox/supervisord.conf:77`
  - `sandbox/supervisord.conf:94`
  - `sandbox/supervisord.conf:240`
- Why this violates Playbook baseline:
  - Playbook expects reliable sandbox runtime startup for SSE/WebSocket-driven agent sessions.

## 2) High: Backend test suite fails at collection (no meaningful regression coverage)
- Severity: High
- Impact:
  - `pytest tests/` cannot proceed beyond collection, so the project loses automated confidence across ~3k tests.
- Evidence:
  - Import error: `cannot import name 'ModelTier' from ... complexity_assessor`.
- Code references:
  - `backend/tests/domain/services/agents/test_adaptive_model.py:11`
  - `backend/tests/domain/services/agents/test_adaptive_model.py:14`
  - `backend/app/domain/services/agents/complexity_assessor.py:26`
- Why this violates Playbook baseline:
  - Playbook explicitly lists backend test suite as a baseline quality check.

## 3) High: Adaptive model selection feature-flag behavior is inconsistent with documented contract
- Severity: High
- Impact:
  - Even when adaptive selection is disabled, execution path still receives a concrete model override instead of `None`.
  - This can unintentionally alter runtime model routing and cost/latency behavior.
- Evidence:
  - `_select_model_for_step()` docstring says it returns `None` when disabled.
  - It always returns `config.model_name`; router returns balanced model when disabled.
- Code references:
  - `backend/app/domain/services/agents/execution.py:176`
  - `backend/app/domain/services/agents/execution.py:189`
  - `backend/app/domain/services/agents/execution.py:205`
  - `backend/app/domain/services/agents/execution.py:440`
  - `backend/app/domain/services/agents/model_router.py:241`
  - `backend/app/domain/services/agents/model_router.py:242`

## 4) Medium: MinIO credential settings are duplicated; required fields are silently downgraded to optional
- Severity: Medium
- Impact:
  - Configuration intent is ambiguous and unsafe: required credentials are redefined as optional `None` later in the same settings class.
  - Can lead to runtime storage failures that are hard to diagnose.
- Evidence:
  - `minio_access_key`/`minio_secret_key` first declared required, then redeclared optional.
  - Runtime introspection confirms effective field is optional (`required=False`, `default=None`).
- Code references:
  - `backend/app/core/config.py:111`
  - `backend/app/core/config.py:114`
  - `backend/app/core/config.py:115`
  - `backend/app/core/config.py:138`
  - `backend/app/core/config.py:140`
  - `backend/app/core/config.py:141`

## 5) Medium: BaseAgent tool-efficiency metric calls use `self._metrics` without initialization
- Severity: Medium
- Impact:
  - Tool-efficiency Prometheus increments are not reliable.
  - Errors are swallowed in broad `try/except`, making this a silent observability failure.
- Evidence:
  - `self._metrics.increment(...)` is called, but `BaseAgent.__init__` does not initialize `self._metrics`.
- Code references:
  - `backend/app/domain/services/agents/base.py:659`
  - `backend/app/domain/services/agents/base.py:756`
  - `backend/app/domain/services/agents/base.py:134`

## 6) Medium: Signed WebSocket URLs are not user-bound; access control is purely possession-based until expiry
- Severity: Medium
- Impact:
  - Anyone holding a valid signed URL can access takeover streams for that session until token expiry.
  - This may be intended for shareability, but it is a security tradeoff and currently undocumented as such.
- Evidence:
  - Signed payload uses only URL + expiry; no user/session ownership claim.
  - WebSocket screencast/input routes fetch session without user binding.
- Code references:
  - `backend/app/application/services/token_service.py:309`
  - `backend/app/application/services/token_service.py:371`
  - `backend/app/interfaces/api/session_routes.py:1230`
  - `backend/app/interfaces/api/session_routes.py:1302`

## 7) Low-Medium: Podman adapter has unresolved type and error-swallowing fallback path
- Severity: Low-Medium
- Impact:
  - Breaks lint gate; can hide root-cause errors when runtime detection fails.
- Evidence:
  - Undefined forward reference `DockerSandbox` in annotation.
  - `except Exception: pass` when probing Podman.
- Code references:
  - `backend/app/infrastructure/external/sandbox/podman_sandbox.py:216`
  - `backend/app/infrastructure/external/sandbox/podman_sandbox.py:243`

## 8) Low: Gateway module is placeholder/incomplete and would be unsafe if accidentally deployed
- Severity: Low
- Impact:
  - Contains auth TODO stubs and placeholder routing responses.
  - Not currently wired into compose runtime, but risky if enabled without hardening.
- Code references:
  - `backend/app/gateway/main.py:52`
  - `backend/app/gateway/main.py:64`
  - `backend/app/gateway/main.py:91`
  - `backend/app/gateway/main.py:104`
  - `backend/app/gateway/main.py:116`

## 9) Low: Insecure default MinIO root credential fallbacks remain in core compose files
- Severity: Low (development), High if deployed unchanged outside dev
- Impact:
  - Emits runtime warnings and weakens default posture when env overrides are missing.
- Code references:
  - `docker-compose.yml:216`
  - `docker-compose.yml:217`
  - `docker-compose-development.yml:242`
  - `docker-compose-development.yml:243`

---

## Automated Check Results

## Backend
- `ruff check .`: **failed**
  - Current outstanding errors: 21
  - Includes both style debt and correctness signals (e.g., undefined type refs, risky exception handling)
- `pytest tests/`: **failed at collection**
  - `ImportError` in adaptive model tests prevents full test execution

## Frontend
- `bun run lint`: passed
- `bun run type-check`: passed

---

## Playbook Alignment Gaps
- Playbook claims validated stack/runtime readiness, but observed runtime behavior shows sandbox supervisor/readiness contract mismatch.
- Playbook quality baseline includes backend lint/tests, but backend currently fails both.
- Security model around signed takeover URLs is functional but possession-based; this should be explicitly documented as a deliberate tradeoff.

---

## Recommended Remediation Order
1. Fix sandbox readiness gating vs mutually-exclusive supervisor programs (`Critical`).
2. Repair adaptive-model test/contract drift so backend tests run end-to-end (`High`).
3. Reconcile adaptive flag semantics in execution/model router path (`High`).
4. Remove duplicate MinIO settings declarations and enforce one authoritative schema (`Medium`).
5. Initialize or inject `BaseAgent` metrics consistently (`Medium`).
6. Decide and document signed URL security model (bind to user/session claim or keep possession-based intentionally) (`Medium`).
7. Clear remaining backend lint debt and Podman adapter issues (`Low-Medium`).
