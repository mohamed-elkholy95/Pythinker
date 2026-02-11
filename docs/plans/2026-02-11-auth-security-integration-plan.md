# Auth and Security Integration Plan

Date: February 11, 2026  
Scope: Pythinker backend, frontend, and deployment/runtime security controls  
Status: Ready for implementation

## 1. Goals

1. Eliminate token replay and revocation bypass gaps.
2. Harden credential storage and password recovery flows.
3. Migrate browser auth away from `localStorage` for long-lived secrets.
4. Add transport and request-layer protections (headers, CSRF, tighter auth rate limits).
5. Add measurable security telemetry and safe rollout/rollback controls.

## 2. Current-State Findings (Code-Backed)

1. Revoked-token checks are not consistently enforced on protected API auth path.
File references: `backend/app/interfaces/dependencies.py:213`, `backend/app/application/services/auth_service.py:352`, `backend/app/application/services/token_service.py:96`
2. Refresh token flow does not rotate tokens and can be replayed.
File references: `backend/app/interfaces/api/auth_routes.py:166`, `backend/app/application/services/auth_service.py:330`
3. Access and refresh tokens are persisted in browser `localStorage`.
File references: `frontend/src/api/auth.ts:284`, `frontend/src/api/auth.ts:300`
4. Password hashing relies on a global configured salt model, not per-user modern hash format.
File reference: `backend/app/application/services/auth_service.py:31`
5. Password-reset code endpoint leaks user existence (`NotFoundError` for unknown email).
File reference: `backend/app/interfaces/api/auth_routes.py:205`
6. Auth rate-limit bucket list excludes password reset and verification endpoints.
File reference: `backend/app/main.py:131`
7. CORS exists, but explicit secure HTTP response headers middleware is not implemented.
File references: `backend/app/main.py:639`, `backend/app/main.py:620`

## 3. Target Security Architecture

1. JWT access tokens are short-lived and validated with strict type checking plus revocation checks.
2. Refresh tokens are one-time-use (rotation), session-bound, and replay-detecting.
3. Browser refresh token stored in `HttpOnly + Secure + SameSite` cookie.
4. Access token is memory-only for SPA mode, or cookie-based with CSRF mitigation where enabled.
5. Password hashing migrates to Argon2id (PBKDF2 kept only as legacy-verify path until migration finishes).
6. Reset/login responses avoid user enumeration.
7. Security headers, tighter endpoint-specific rate limits, and telemetry-backed rollout.

## 4. Workstreams

1. Backend auth core and token lifecycle hardening.
2. Frontend auth storage and refresh behavior migration.
3. Runtime hardening and config controls.
4. Verification and release controls.

## 5. Phase Plan

## Phase 0: Baseline and Guardrails

Duration: 1-2 days  
Risk: Low  
Output: Measured baseline and rollout flags

1. Document baseline auth metrics and current behavior.
2. Add feature flags with default-off behavior.
3. Define rollout SLOs and rollback thresholds.

Implementation targets:
1. `backend/app/core/config.py`
2. `docs/reports/` and `docs/plans/`

Acceptance criteria:
1. Baseline dashboard captures login failures, refresh calls, 401 rates, and rate-limit events.
2. All new auth controls are flag-gated.

## Phase 1: Token Correctness and Revocation Enforcement

Duration: 3-4 days  
Risk: High  
Output: Protected endpoints always enforce revocation and token type

1. Add strict token-verification methods:
1. `verify_access_token_async()`
2. `verify_refresh_token_async()`
3. `verify_resource_token_async()`
2. Update dependency auth path to call async revocation-aware access-token verification.
3. Add `jti`, `sid`, `iss`, `aud`, and `nbf` claims for access and refresh tokens.
4. Enforce token `type` checks everywhere.
5. Ensure logout and logout-all invalidate by session and user with deterministic Redis keys.

Implementation targets:
1. `backend/app/application/services/token_service.py`
2. `backend/app/application/services/auth_service.py`
3. `backend/app/interfaces/dependencies.py`
4. `backend/app/interfaces/api/auth_routes.py`

Acceptance criteria:
1. Blacklisted/revoked token cannot access protected routes.
2. Refresh token cannot be used on access-protected routes and vice versa.
3. Issuer/audience mismatch returns unauthorized.

## Phase 2: Refresh Rotation and Replay Detection

Duration: 3-4 days  
Risk: High  
Output: One-time refresh semantics with replay kill-switch

1. Implement refresh-token rotation:
1. Every successful refresh invalidates the old refresh token.
2. New refresh token is issued with new `jti` and same `sid`.
2. Store token family/session state in Redis:
1. `auth:refresh:{jti}` metadata
2. `auth:session:{sid}:status`
3. `auth:user:{user_id}:sessions`
3. Detect refresh token reuse:
1. Mark session compromised.
2. Revoke all session tokens.
3. Return forced re-auth response.
4. Add replay telemetry counter and alert.

Implementation targets:
1. `backend/app/application/services/token_service.py`
2. `backend/app/application/services/auth_service.py`
3. `backend/app/interfaces/api/auth_routes.py`

Acceptance criteria:
1. Reusing old refresh token always fails.
2. Reuse event revokes session consistently.
3. Rotation works under concurrency without race-based bypass.

## Phase 3: Password and Recovery Hardening

Duration: 3-5 days  
Risk: Medium  
Output: Modern hash model and non-enumerating reset flow

1. Introduce hash-versioned storage format:
1. Preferred: Argon2id via `passlib`/argon2 implementation.
2. Legacy: existing PBKDF2 verification path.
3. On successful legacy verify, transparently rehash to Argon2id.
2. Optional pepper support from environment/KMS.
3. Unify password policy validation between schema and service.
4. Make reset-code request response generic:
1. Always return success-style response.
2. Do not reveal user existence.
5. Rate-limit reset and code verification attempts per IP and per email.

Implementation targets:
1. `backend/app/application/services/auth_service.py`
2. `backend/app/interfaces/schemas/auth.py`
3. `backend/app/interfaces/api/auth_routes.py`
4. `backend/app/application/services/email_service.py`
5. `backend/app/main.py`

Acceptance criteria:
1. Existing users can still log in.
2. New passwords stored with Argon2id format.
3. Reset flow does not reveal account existence.

## Phase 4: Browser Auth Storage Migration

Duration: 4-6 days  
Risk: High  
Output: Refresh token removed from `localStorage`

1. Introduce cookie auth mode:
1. Refresh token in `HttpOnly`, `Secure`, `SameSite=Lax/Strict` cookie.
2. Cookie path constrained to auth routes.
2. Keep access token memory-only in SPA.
3. Add CSRF protection for state-changing endpoints when cookie mode is enabled:
1. Double-submit CSRF token header.
2. Backend validation dependency.
4. Update login, refresh, logout response contracts:
1. Set/clear cookies in backend.
2. Frontend no longer reads/writes refresh token storage.
5. Dual-mode compatibility window:
1. Header token mode and cookie mode coexist behind flag.
2. Canary users on cookie mode first.

Implementation targets:
1. `backend/app/interfaces/api/auth_routes.py`
2. `backend/app/interfaces/dependencies.py`
3. `backend/app/core/config.py`
4. `frontend/src/api/auth.ts`
5. `frontend/src/api/client.ts`
6. `frontend/src/composables/useAuth.ts`

Acceptance criteria:
1. Browser refresh token absent from `localStorage`.
2. Auth refresh works after page reload.
3. CSRF check blocks forged cross-site state changes in cookie mode.

## Phase 5: Security Headers and Auth Endpoint Throttling

Duration: 2-3 days  
Risk: Medium  
Output: Hardened HTTP layer and abuse resistance

1. Add security headers middleware:
1. `Content-Security-Policy`
2. `Strict-Transport-Security` (production)
3. `X-Content-Type-Options: nosniff`
4. `X-Frame-Options: DENY`
5. `Referrer-Policy`
6. `Permissions-Policy`
2. Expand auth path strict rate limits to include:
1. `/auth/send-verification-code`
2. `/auth/reset-password`
3. `/auth/change-password`
3. Keep CORS explicit by environment and disallow wildcard with credentials.

Implementation targets:
1. `backend/app/main.py`
2. `backend/app/core/config.py`

Acceptance criteria:
1. Security headers present on API responses.
2. Auth abuse paths trigger 429 reliably.

## Phase 6: Step-Up Auth and Session Governance

Duration: 4-6 days  
Risk: Medium  
Output: Higher assurance for privileged actions

1. Add admin MFA gate:
1. TOTP setup and verification.
2. Step-up required for admin-only routes and sensitive account changes.
2. Add session inventory endpoint:
1. List active sessions/devices.
2. Revoke per-session or all sessions.
3. Enforce re-auth confirmation before password change and security-sensitive actions.

Implementation targets:
1. `backend/app/interfaces/api/auth_routes.py`
2. `backend/app/application/services/auth_service.py`
3. `frontend/src/components/settings/AccountSettings.vue`
4. `frontend/src/composables/useAuth.ts`

Acceptance criteria:
1. Admin actions require successful MFA.
2. User can revoke a single session and observe immediate invalidation.

## Phase 7: Verification, Rollout, and Cleanup

Duration: 3-5 days  
Risk: Medium  
Output: Production-safe rollout and deprecation completion

1. Execute full test matrix and load tests.
2. Canary deployment:
1. Internal users.
2. Small external cohort.
3. Full rollout.
3. Remove legacy localStorage refresh logic after stability window.
4. Remove deprecated token code paths once metrics are stable.

Implementation targets:
1. `backend/tests/`
2. `frontend/tests/`
3. release/deploy configs

Acceptance criteria:
1. No auth regression in core flows.
2. Security telemetry stable and within SLO.
3. Legacy token-storage code removed.

## 6. Data and State Design

Redis keys (proposed):
1. `auth:refresh:{jti}` -> `{user_id, sid, exp, status, rotated_to}`
2. `auth:session:{sid}` -> `{user_id, revoked_before, compromised}`
3. `auth:user:{user_id}:sessions` -> set of `sid`
4. `auth:blacklist:{jti}` -> TTL aligned with token expiration
5. `auth:failed_attempts:{email_or_hash}` and `auth:lockout:{email_or_hash}`

Design notes:
1. Prefer `jti`-based blacklisting over hashing full raw tokens.
2. Avoid plain-email Redis keys in production; use keyed hash if required by policy.

## 7. API Contract Changes

1. `POST /auth/login`
1. Current: body contains `access_token` and `refresh_token`.
2. Transitional: keep response, also set refresh cookie when flag is enabled.
3. Final web mode: access token in body (short-lived), refresh via cookie only.
2. `POST /auth/refresh`
1. Current: accepts refresh token in body.
2. Transitional: accept body token or cookie.
3. Final web mode: cookie-only with CSRF header.
3. `POST /auth/logout`
1. Must revoke current session and clear auth cookie.
4. `POST /auth/logout-all` (new)
1. Revoke all sessions for current user.
5. `GET /auth/sessions` and `DELETE /auth/sessions/{sid}` (new)
1. Session inventory and targeted revoke.

## 8. Config Additions

Add to `backend/app/core/config.py`:
1. `auth_cookie_enabled: bool = False`
2. `auth_cookie_name_refresh: str = "refresh_token"`
3. `auth_cookie_secure: bool = True`
4. `auth_cookie_samesite: str = "lax"`
5. `auth_cookie_domain: str | None = None`
6. `auth_cookie_path: str = "/api/v1/auth"`
7. `auth_csrf_enabled: bool = False`
8. `jwt_issuer: str = "pythinker"`
9. `jwt_audience: str = "pythinker-web"`
10. `jwt_clock_skew_seconds: int = 30`
11. `jwt_refresh_rotation_enabled: bool = False`
12. `password_hash_scheme: str = "argon2id"`
13. `password_pepper: str | None = None`
14. `auth_admin_mfa_enabled: bool = False`

## 9. Test Integration Plan

Backend tests to add/update:
1. `backend/tests/test_auth_token_rotation.py`
2. `backend/tests/test_auth_revocation_enforcement.py`
3. `backend/tests/test_auth_cookie_mode.py`
4. `backend/tests/test_auth_csrf.py`
5. `backend/tests/test_auth_reset_enumeration.py`
6. `backend/tests/test_auth_rate_limit_reset_endpoints.py`
7. `backend/tests/test_password_hash_migration.py`

Frontend tests to add/update:
1. `frontend/tests/composables/useAuth.spec.ts`
2. `frontend/tests/api/client-auth-refresh.spec.ts`
3. `frontend/tests/pages/LoginPage.spec.ts`

Validation command set:
1. `cd frontend && bun run lint && bun run type-check`
2. `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

## 10. Rollout and Rollback

Rollout order:
1. Deploy backend with flags off and dual-mode compatibility.
2. Enable revocation enforcement and refresh rotation in staging.
3. Enable cookie mode for canary users.
4. Enable CSRF enforcement for cookie mode.
5. Expand canary to full traffic.
6. Remove localStorage refresh path.

Rollback strategy:
1. Disable `jwt_refresh_rotation_enabled` if refresh failures spike.
2. Disable `auth_cookie_enabled` to revert to header token mode.
3. Keep old token verification support for one release cycle.
4. Re-enable temporary compatibility endpoints if client mismatch occurs.

Rollback triggers:
1. Login failure rate increase > 2x baseline.
2. 401 rate increase > 1.5x baseline for authenticated traffic.
3. Refresh failure rate > 3% sustained over 15 minutes.

## 11. Operational Metrics and Alerts

Metrics:
1. `auth_login_attempt_total{result}`
2. `auth_login_lockout_total`
3. `auth_refresh_total{result}`
4. `auth_refresh_reuse_detected_total`
5. `auth_token_revoked_request_total`
6. `auth_csrf_block_total`
7. `auth_rate_limit_block_total{endpoint}`

Alert rules:
1. Refresh replay detection above baseline threshold.
2. Sudden spikes in unauthorized responses after rollout.
3. Lockout spikes by IP or account segment.

## 12. Execution Sequence (Recommended)

1. Phase 0 and Phase 1
2. Phase 2
3. Phase 3
4. Phase 5
5. Phase 4
6. Phase 6
7. Phase 7

Rationale:
1. Token correctness and replay prevention first.
2. Browser storage migration after backend dual-mode foundation.
3. Step-up auth after core session lifecycle is stable.

## 13. Definition of Done

1. Revoked and replayed tokens are blocked in all protected flows.
2. Browser refresh token is not persisted in `localStorage`.
3. Password reset and login flows do not reveal account existence.
4. Security headers and auth endpoint limits are active in production.
5. End-to-end tests for login, refresh, logout, reset, and rotation all pass.
6. Canary and full rollout complete with no sustained SLO violations.

## 14. Context7 Security References Used

1. FastAPI security tutorial: `https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/`
2. OWASP Authentication Cheat Sheet: `https://github.com/owasp/cheatsheetseries/blob/master/cheatsheets/Authentication_Cheat_Sheet.md`
3. OWASP Password Storage Cheat Sheet: `https://github.com/owasp/cheatsheetseries/blob/master/cheatsheets/Password_Storage_Cheat_Sheet.md`
4. OWASP JWT Cheat Sheet (token storage and mitigations): `https://github.com/owasp/cheatsheetseries/blob/master/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.md`
5. OWASP Secure Code Review Checklist (auth/session): `https://github.com/owasp/cheatsheetseries/blob/master/cheatsheets/Secure_Code_Review_Cheat_Sheet.md`
