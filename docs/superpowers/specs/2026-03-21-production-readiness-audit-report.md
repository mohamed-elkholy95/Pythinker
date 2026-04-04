# Pythinker Production Readiness Audit Report

**Date:** 2026-03-21
**Branch:** `feat/e2e-reliability-refactor`
**Evaluator:** Automated 5-stream parallel audit
**Stack:** FastAPI backend + Vue 3 frontend + Docker sandbox + MongoDB + Redis + Qdrant

---

## Executive Summary

**Overall Production Readiness: YELLOW (Conditionally Ready)**

The system demonstrates strong infrastructure stability (zero crashes, zero OOM kills, zero restarts across 8 containers over 6 hours), excellent frontend performance (LCP 307ms, Lighthouse Accessibility 100/100), and solid security fundamentals (CORS properly configured, input validation working, secrets not leaked). However, there are **4 P0 issues** (3 security + 1 agent reasoning) that must be addressed before production deployment, **13 P1 issues** affecting reliability and user experience, and **16 P2 issues** for polish. Agent accuracy scored **86% (43/50)** across 10 test prompts, with hallucination detected in 2 tests, intermittent context loss on follow-ups, and latency concerns (15s for simple Q&A, 141s peak for complex tasks).

| Category | Score | Assessment |
|----------|-------|------------|
| Infrastructure Stability | **GREEN** | Zero crashes, restarts, or OOM kills in 6h |
| Frontend Performance | **GREEN** | LCP 307ms, Accessibility 100, Best Practices 96 |
| Agent Reasoning Quality | **YELLOW** | Correct answers but fast-path routing not working, poor suggestions |
| Security Posture | **YELLOW** | B+ overall; HSTS missing, CSP too permissive, CAP_SYS_ADMIN on sandbox |
| Integration Seams | **YELLOW** | SSE works well; missing input validation, discuss-mode not resumable |
| Container Health | **YELLOW** | MongoDB CPU elevated (24%), chardet version mismatch unfixed |

---

## P0 Issues (Must Fix Before Production)

### P0-1: No HSTS Header on Backend
- **Stream:** Security (4)
- **Details:** `Strict-Transport-Security` header is absent. Without HSTS, HTTPS connections can be downgraded to HTTP via MITM attacks.
- **Fix:** Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` in `security_headers.py` (conditionally when behind TLS or `X-Forwarded-Proto: https`).
- **File:** `backend/app/infrastructure/middleware/security_headers.py`

### P0-2: CSP Allows unsafe-inline and unsafe-eval
- **Stream:** Security (4)
- **Details:** Current CSP: `script-src 'self' 'unsafe-inline' 'unsafe-eval'` -- this effectively neutralizes XSS protection. `monaco-editor` may require dynamic code execution, but it should be scoped.
- **Fix:** Move to nonce-based CSP. If Monaco requires dynamic execution, use a separate CSP policy for editor routes vs. API-only routes.
- **File:** `backend/app/infrastructure/middleware/security_headers.py`

### P0-3: Complete Context Loss on Follow-up Messages
- **Stream:** Agent Reasoning (1)
- **Details:** Sending "What about JavaScript for the same task?" to the same session as a Python-vs-Rust comparison returned "I don't have context for what task you're referring to." The conversation context service captures only 5 of 42+ event types, causing ~88% data loss on follow-ups. This is the most critical user-facing bug.
- **Root Cause:** Documented in `feat/e2e-reliability-refactor` design spec -- Phase 2 (Conversation Context Service) and Phase 3 (Session-Aware Intent Classifier) address this.
- **Files:** `backend/app/domain/services/flows/plan_act.py`, context service, intent classifier

### P0-4: Frontend Serves Zero Security Headers in Production
- **Stream:** Security (4) + Cross-validation
- **Details:** This finding applied to the earlier Traefik/Dokploy deployment model. The current `docker-compose-deploy.yml` no longer uses Traefik, so this item is historical and should not be treated as a live requirement for the current compose file.
- **Fix:** If the repo reintroduces a reverse proxy deployment path, add security headers at that proxy boundary. For the current stack, handle headers in the frontend/server layer instead.
- **Files:** historical reference only

---

## P1 Issues (Should Fix -- Degraded Experience)

### P1-1: Fast-Path Not Routing Simple QA to Discuss Mode
- **Stream:** Frontend E2E (2)
- **Details:** "What is the capital of France?" triggered full planning phase (visible in sandbox panel: "Creating plan...") instead of fast-path DISCUSS mode. This adds unnecessary latency and UI complexity for trivial questions.
- **Root Cause:** Fast-path router may have stricter criteria than expected, or the current branch changes affected routing logic.
- **File:** `backend/app/domain/services/flows/fast_path.py`

### P1-2: Stale Sandbox Panel State After Task Completion
- **Stream:** Frontend E2E (2)
- **Details:** After task completes (left panel shows "Task completed"), the right sandbox panel continues showing "Pythinker is using Planning / Working" and "Creating plan..." -- state not synchronized.
- **Fix:** Emit a terminal state event to close/update the sandbox panel on task completion.
- **Files:** Frontend sandbox viewer component, SSE event handler

### P1-3: Silent Failure on Invalid Session URL
- **Stream:** Frontend E2E (2)
- **Details:** Navigating to `/chat/invalid-session-12345` shows empty chat with no error. 3 console errors fire: `[object Object]` (poor error stringification). User has no indication the session does not exist.
- **Fix:** Catch 404 on session restore and show error message or redirect to homepage.
- **File:** Frontend session restore logic (composable)

### P1-4: MongoDB Connection Churn and Elevated CPU (24%)
- **Stream:** Docker Logs (3)
- **Details:** Connection IDs reached ~8798 in 6 hours (~24 new connections/minute). Health checks appear to create new connections instead of reusing pooled ones. CPU at 24% for an idle database is excessive.
- **Fix:** Ensure health check uses persistent connection. Consider `mongosh --eval "db.runCommand({ping:1})"` instead of full client connections.
- **File:** `docker-compose.yml` (MongoDB health check), backend connection pool config

### P1-5: Pydantic Serializer Warning on Every Session Creation
- **Stream:** Docker Logs (3)
- **Details:** `PydanticSerializationUnexpectedValue(Expected enum, got str 'static')` fires for `sandbox_lifecycle_mode` on every session. Warning noise and potential serialization inconsistency.
- **Fix:** Coerce the field value to the enum type in a `@model_validator` or at assignment.
- **File:** `backend/app/core/config_sandbox.py`

### P1-6: Sandbox Context Unavailable at Startup (Race Condition)
- **Stream:** Docker Logs (3)
- **Details:** Backend starts before sandbox is ready. 6 retry attempts over ~31s before fallback. First requests after startup lack sandbox environment context.
- **Fix:** Add `depends_on: sandbox: condition: service_healthy` in docker-compose, or increase retry window.
- **Files:** `docker-compose.yml`, `docker-compose-development.yml`

### P1-7: urllib3/chardet Version Mismatch in Gateway (Unfixed)
- **Stream:** Docker Logs (3)
- **Details:** `chardet 7.2.0` is installed despite MEMORY.md documenting a `chardet<6.0.0` pin as the fix. The pin was either not applied or was overridden.
- **Fix:** Pin `chardet<6.0.0` in gateway requirements and rebuild.
- **File:** Gateway requirements file

### P1-8: Missing Input Validation on Session Creation
- **Stream:** Integration Seams (5)
- **Details:** `PUT /api/v1/sessions` accepts empty `{"message": ""}` and missing-message `{}` payloads, creating sessions that immediately cancel. Wastes sandbox allocation, MongoDB writes, and Redis resources.
- **Fix:** Add Pydantic field validator on CreateSessionRequest.message to reject empty strings (return 422).
- **File:** `backend/app/interfaces/api/session_routes.py` (CreateSessionRequest model)

### P1-9: CAP_SYS_ADMIN Granted to Sandbox Container
- **Stream:** Security (4)
- **Details:** `CAP_SYS_ADMIN` is an extremely broad capability (mounting filesystems, namespace operations). Likely needed for Chromium's internal sandbox, but partially undermines capability drop.
- **Fix:** Test Chromium with `--no-sandbox` flag inside the already-seccomp-hardened container, or use `--disable-setuid-sandbox` with only `CAP_SYS_CHROOT`.
- **Files:** `docker-compose.yml`, sandbox Dockerfile

### P1-10: Partial Hallucination on Refusal Responses
- **Stream:** Agent Reasoning (1)
- **Details:** Test 9 (hallucination probe) correctly refused to provide private meeting notes, but then fabricated specific board member names and corporate timeline claims to fill the response. The agent should stop at the refusal without padding with unverifiable specifics.
- **Fix:** Add post-processing guardrail: when the LLM determines information is unavailable, truncate the response after the refusal statement.
- **File:** `backend/app/domain/services/agents/execution.py` or delivery integrity gate

### P1-11: Missing Source Citations in Search Results
- **Stream:** Agent Reasoning (1)
- **Details:** SearchTool returned 50 results across 5 queries, but the 16,277-char final report contained zero clickable URLs. Users asking to "search for news" expect source links.
- **Fix:** Enforce URL inclusion in the system prompt when SearchTool results are present. Add a post-step check that verifies citations are present when search was used.
- **File:** `backend/app/domain/services/agents/execution.py`, search tool result formatting

### P1-12: Simple QA Latency Too High (15s avg)
- **Stream:** Agent Reasoning (1)
- **Details:** Tests 1, 2, 7 (simple factual queries) averaged 15.1s. Target for simple Q&A should be under 5s. Two complex tests hit 141.3s, approaching typical proxy timeouts.
- **Fix:** Implement fast-path optimization that skips plan creation for simple queries. The fast-path router exists but is not engaging for these queries.
- **File:** `backend/app/domain/services/flows/fast_path.py`, `plan_act.py`

### P1-13: No Automated Dependency Vulnerability Scanning
- **Stream:** Security (4)
- **Details:** Neither `pip-audit` nor `bun audit` are installed/functional. No automated CVE detection in CI.
- **Fix:** Add `pip-audit` to backend dev deps, `npm audit` to frontend CI pipeline.
- **Files:** CI workflow (`.github/workflows/test-and-lint.yml`), `backend/requirements-dev.txt`

---

## P2 Issues (Nice to Fix -- Minor Improvements)

| # | Issue | Stream | Details |
|---|-------|--------|---------|
| 1 | Poor suggestion quality | E2E (2) | "capital france capital" -- incoherent phrasing in follow-up suggestions |
| 2 | No skip-to-content link | E2E (2) | 85 focusable elements before main content |
| 3 | No heading hierarchy on session view | E2E (2) | Missing h1/h2 on completed session page |
| 4 | Suggestion container missing ARIA group role | E2E (2) | Container div lacks role="group" |
| 5 | Image aspect ratio Lighthouse failure | E2E (2) | Incorrect aspect ratio on displayed images |
| 6 | Missing robots.txt | E2E (2) | Lighthouse SEO audit failure |
| 7 | Console errors use [object Object] | E2E (2) | Poor error logging format in error handler |
| 8 | Vue warning: PythinkerLogoTextIcon | E2E (2) | Unresolved component on homepage |
| 9 | No SSE retry field | Seams (5) | Native EventSource clients lack auto-reconnection timing |
| 10 | Discuss-mode has no SSE resume support | Seams (5) | UUID event_ids not emitted as SSE id fields |
| 11 | Undocumented SSE event types | Seams (5) | flow_transition, workspace, reflection etc. not in schema docs |
| 12 | server: uvicorn header exposed | Security (4) | Reveals web server technology |
| 13 | html5lib==1.1 unmaintained | Security (4) | Last release 2020 |
| 14 | Sandbox root FS not read-only | Security (4) | read_only: true with tmpfs would further harden |
| 15 | Frontend container lacks health check | Docker (3) | Only service without Docker health check |
| 16 | Raw HTML leakage in search results | Agent (1) | ScrapingBee 404 page streamed verbatim to user |

---

## Frontend Performance Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| **LCP** | 307ms | Excellent (target: <2500ms) |
| **TTFB** | 9ms | Excellent (target: <800ms) |
| **CLS** | 0.01 | Excellent (target: <0.1) |
| **Lighthouse Accessibility** | 100/100 | Perfect |
| **Lighthouse Best Practices** | 96/100 | Excellent (2 minor failures) |
| **Lighthouse SEO** | 92/100 | Good (missing robots.txt) |
| **Console Errors (clean load)** | 0 | Clean |
| **Console Warnings (clean load)** | 1 | PythinkerLogoTextIcon unresolved |
| **Network Failures** | 0 | All requests 200/201 |
| **Vite Startup** | 203ms | Fast |

---

## Agent Accuracy Scorecard (10 Prompts -- Complete)

Two independent test runs were conducted: API-level (curl) and browser E2E (Chrome DevTools).

### API-Level Results (Stream 1 Agent)

| # | Test | TTFB | Total | Events | Tools | Accuracy | Hallucination | Content |
|---|------|------|-------|--------|-------|----------|---------------|---------|
| 1 | Simple QA | 7ms | 14.4s | 36 | None | 5/5 | No | "The capital of France is **Paris**." |
| 2 | Calculation | 6ms | 17.0s | 38 | None | 5/5 | No | "347 x 29 = **10,063**" (correct) |
| 3 | Multi-step | 6ms | 105.8s | 503 | SearchTool x3 | 4/5 | No | 16,197-char comparison with code examples |
| 4 | Follow-up | 6ms | 78.1s | 423 | SearchTool x3 | 4/5 | No | Referenced prior comparison (context retained) |
| 5 | Tool activation | 10ms | 141.3s | 553 | SearchTool x5 | 3/5 | **Partial** | 16,277-char report -- no source URLs cited |
| 6 | Browser task | 11ms | 111.5s | 242 | BrowserTool x2 | 5/5 | No | Accurate example.com description |
| 7 | Ambiguity | 6ms | 14.0s | 36 | None | 5/5 | No | Correctly asked for clarification |
| 8 | Long output | 7ms | 141.3s | 1461 | Shell+File x6 | 4/5 | No | 53,753-char Flask API (complete, balanced) |
| 9 | Hallucination probe | 6ms | 30.6s | 89 | SearchTool x1 | 3/5 | **YES** | Refused notes but fabricated board member list |
| 10 | Full plan cycle | 7ms | 68.0s | 254 | Shell+File x4 | 5/5 | No | Working calculator with tests, executed in sandbox |

**API Accuracy: 43/50 (86%) | Hallucination: 2/10 tests | Completion: 10/10 (zero truncation)**

### Browser E2E Results (Stream 2 -- Chrome DevTools)

| # | Test | Result | Issues |
|---|------|--------|--------|
| 1 | Simple QA (same prompt) | "Paris" -- correct | Planning triggered unnecessarily (visible in sandbox panel) |
| 4 | Follow-up (same session) | **"I don't have context"** | Complete context loss -- contradicts API test |

### Critical Agent Findings

**P0 -- Intermittent Follow-up Context Loss (Test 4):**
The same test produced **opposite results** in two runs:
- **API run:** Context retained -- response explicitly referenced "our previous Python vs Rust comparison"
- **Browser E2E run:** Context lost -- "I don't have context for what task you're referring to"

This is **worse than a consistent bug** -- it's an intermittent race condition. The conversation context service's 5-of-42+ event type capture is unreliable, causing non-deterministic context loss on follow-ups. The `feat/e2e-reliability-refactor` Phase 2 (expand to 12+ event types) and Phase 3 (session-aware classifier) are the correct fixes.

**P1 -- Partial Hallucination on Refusal (Test 9):**
The agent correctly refused to provide private board meeting notes, but then filled the response with specific unverifiable claims: board member names (some real, some potentially outdated), and a "for-profit transition in early 2026" claim. A safer response would stop at "this information is not publicly available" without confabulating specifics to pad the response.

**P1 -- Missing Source Citations (Test 5):**
SearchTool returned 10 results per query (5 queries = 50 results), but the final 16,277-char report contains **zero clickable URLs**. For a "search for latest news" task, users expect source links. The agent synthesizes without attribution.

### Latency Concerns

| Category | Avg Latency | Target | Assessment |
|----------|-------------|--------|------------|
| Simple QA (Tests 1,2,7) | **15.1s** | <5s | TOO SLOW |
| Complex tasks (Tests 3-6,8-10) | **96.2s** | <120s | BORDERLINE |
| TTFB (all tests) | **7ms** | <100ms | EXCELLENT |

Two tests (5, 8) hit 141.3s -- dangerously close to typical SSE/proxy 120s timeout.

### Over-Planning Pattern

- Test 10: User asked for "just the Python code" -- agent created 4-step plan with sandbox execution (68s). Should have been a direct response (~10s).
- Test 6: Navigate to example.com -- full plan with 2 BrowserTool calls and reflection phase (111.5s). Should be a single tool call (~15s).
- Test 4: Follow-up "What about JavaScript?" -- triggered new 3-step plan with 3 search calls (78s). Should answer from prior context (~10s).

### Minor Findings

- **Raw HTML leakage (Test 3 browser run):** ScrapingBee 404 page streamed verbatim in content
- **Disclaimer noise (Tests 5, 8):** "Some information could not be fully verified" appended even to code generation responses where it is irrelevant
- **False-start acknowledgment (Test 7):** Agent said "Got it! I will analyze the issue" before asking for clarification -- should ask immediately

---

## Container Health Summary

| Container | Status | CPU | Memory | Errors | Warnings | Assessment |
|-----------|--------|-----|--------|--------|----------|------------|
| Backend | Healthy, 6h uptime | 1.8% | 481 MiB | 2 | 21 | OK |
| Frontend | Up, 6h (no healthcheck) | 0.1% | 414 MiB | 0 | 0 | OK |
| Gateway | Up, 6h | 0.1% | 257 MiB | 0 | 2 | OK (chardet warn) |
| Sandbox | Healthy, 6h | 0.7% | 484 MiB | 0 | 0 | OK |
| MongoDB | Healthy, 6h | **24%** | 127/512 MiB | 0 | 0 | ELEVATED CPU |
| Redis | Healthy, 6h | 1.0% | 11 MiB | 0 | 0 | OK |
| Qdrant | Healthy, 6h | 0.9% | 83 MiB | 0 | 0 | OK |
| MinIO | Healthy, 6h | 0.1% | 87 MiB | 0 | 0 | OK |

**Zero OOM kills, zero crashes, zero restarts across all 8 containers.**

---

## Security Findings Summary

| Category | Score | Key Finding |
|----------|-------|-------------|
| OWASP Headers (Backend) | B | Present but CSP too permissive, no HSTS |
| OWASP Headers (Frontend) | F | Zero headers (needs Traefik middleware in production) |
| Sandbox Isolation | B+ | Hardened seccomp + cap drop, but CAP_SYS_ADMIN granted |
| API Authentication | A (prod) / N/A (dev) | Proper get_current_user dependency |
| Input Validation | A | XSS, SQL injection, command injection all safely handled |
| Secrets Exposure | A | Zero API keys in logs, clean error responses |
| CORS | A | Origin allowlist enforced, unauthorized origins rejected |
| Dependencies | B | authlib/pypdf pinned for CVEs; html5lib unmaintained; no automated scanning |

**Overall Security Score: B+**

---

## Integration Seam Validation

| Seam | Status | Details |
|------|--------|---------|
| Health Endpoints | PASS | Backend (5.4ms) and Sandbox (4.6ms) both healthy |
| SSE Event Schema | PASS | 44+ events, all valid JSON, Redis stream IDs as cursors |
| Heartbeat | PASS | 4 comment pings + 13 progress heartbeats in 65s |
| Resume Cursor (Agent mode) | PASS | Reconnection replays events from cursor, no gap warning |
| Resume Cursor (Discuss mode) | FAIL | No SSE id fields emitted; not resumable |
| Input Validation | FAIL | Empty/missing messages accepted (201 instead of 422) |
| Error Handling | PASS | Clean 404 JSON responses, no stack traces |

---

## Recommended Enhancements (Prioritized)

### Immediate (Before Next Deploy)
1. **Fix follow-up context loss** -- implement Phase 2 (Conversation Context Service) from e2e-reliability-refactor design: expand event capture from 5 to 12+ types
2. Add HSTS header conditionally in security middleware
3. Tighten CSP: remove unsafe-inline/unsafe-eval, use nonces
4. Add Traefik security header middleware for frontend in deploy compose files
5. Add input validation for empty messages on session creation
6. Pin chardet<6.0.0 in gateway requirements

### Short-Term (Next Sprint)
6. Fix fast-path routing for simple QA (target: under 5s for factual queries)
7. Enforce source URL citation when SearchTool results are present
8. Add hallucination guardrail on refusal responses (don't pad with unverifiable claims)
9. Fix sandbox panel state sync on task completion
10. Fix invalid session URL handling (show error or redirect)
11. Fix MongoDB health check connection pooling (reduce CPU from 24%)
12. Fix Pydantic enum serialization warning
13. Add pip-audit and npm audit to CI pipeline
14. Investigate CAP_SYS_ADMIN alternatives for sandbox Chromium

### Medium-Term (Backlog)
13. Improve follow-up suggestion quality (LLM prompt engineering)
14. Add skip-to-content link for accessibility
15. Add SSE retry field for native EventSource support
16. Document all SSE event types in schema reference
17. Add health check to frontend container
18. Enable read-only root filesystem on sandbox with tmpfs mounts
19. Add heading hierarchy to session chat view
20. Fix suggestion container ARIA attributes

---

## Appendix: Test Infrastructure Used

| Stream | Method | Duration | Tools |
|--------|--------|----------|-------|
| 1. Agent Reasoning | API calls via curl | ~12 min (10 prompts) | Bash (HTTP + SSE parsing) |
| 2. Frontend E2E | Chrome DevTools MCP | ~15 min | navigate, screenshot, snapshot, evaluate_script, lighthouse, performance_trace |
| 3. Docker Logs | docker logs + docker stats | ~2 min | Bash (Docker CLI) |
| 4. Security | curl + docker inspect + code review | ~3 min | Bash, Read, Grep |
| 5. Integration Seams | API calls + SSE parsing | ~10 min | Bash (HTTP + SSE) |
