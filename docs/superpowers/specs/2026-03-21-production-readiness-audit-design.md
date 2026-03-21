# Production Readiness Audit — Design Specification

**Date:** 2026-03-21
**Branch:** `feat/e2e-reliability-refactor`
**Goal:** Comprehensive production readiness evaluation across all Pythinker subsystems before deployment.

---

## Scope

Balanced coverage across 5 parallel evaluation streams:

1. Agent Reasoning Quality (API-level)
2. Frontend E2E (Chrome DevTools MCP)
3. Docker Container Log Analysis
4. Security Audit
5. Integration Seam Validation

## Approach

**Parallel Blitz with Convergence Report** — launch 5 focused agents simultaneously, converge into a single prioritized report.

---

## Stream 1: Agent Reasoning Quality

### Test Matrix

| # | Category | Prompt | Validates |
|---|----------|--------|-----------|
| 1 | Simple Q&A | "What is the capital of France?" | Fast-path routing, correct answer, no unnecessary planning |
| 2 | Calculation | "What is 347 × 29?" | Accuracy, tool selection |
| 3 | Multi-step reasoning | "Compare Python and Rust for web scraping — pros/cons with examples" | Plan quality, step coherence, factual accuracy |
| 4 | Follow-up coherence | "What about JavaScript?" (after #3) | Context retention, no topic drift |
| 5 | Tool activation | "Search for the latest news about AI regulation in the EU" | Search tool invoked, results cited |
| 6 | Browser task | "Navigate to example.com and tell me what's on the page" | Browser tool activation, CDP screencast |
| 7 | Ambiguity | "Fix it" (no context) | Graceful handling, clarification request |
| 8 | Long output | "Write a detailed Python REST API with auth, CRUD, and tests" | Truncation detection, completeness |
| 9 | Hallucination probe | "What did OpenAI announce on March 15, 2026?" | Acknowledges uncertainty, no fabrication |
| 10 | Full cycle | "Create a simple calculator web app" | Plan→execute→verify completeness |

### Scoring Criteria (per response)

- **Factual accuracy**: 0–5 scale
- **Hallucination detection**: fabricated facts, fake URLs, invented APIs
- **Response completeness**: truncation check (mid-sentence, unclosed code blocks)
- **Tool selection**: appropriate tool for the task
- **Follow-up coherence**: context retained across turns
- **Latency**: time-to-first-event, total response time

---

## Stream 2: Frontend E2E (Chrome DevTools)

### Test Scenarios

| # | Scenario | DevTools Actions | Validates |
|---|----------|-----------------|-----------|
| 1 | Page load | `navigate_page` → `take_screenshot` → `performance_analyze_insight` | Load time, rendering, no console errors |
| 2 | Session creation | `click` new chat → `fill` message → submit | Session created, SSE starts, thinking indicator |
| 3 | SSE streaming | `list_network_requests` during chat | SSE connection, event flow, heartbeats |
| 4 | Tool execution UI | Send task → `take_screenshot` at intervals | Tool panel, progress indicators, sandbox viewer |
| 5 | State transitions | Observe thinking → executing → completing → done | Indicator states, Stop button, suggestions |
| 6 | Error handling | Empty/malformed input | Graceful error display, no broken state |
| 7 | Accessibility | Suggestion buttons, keyboard nav | ARIA attributes, focus management |
| 8 | Console errors | `list_console_messages` throughout | Zero unhandled exceptions, no Vue warnings |
| 9 | Network health | `list_network_requests` | No 4xx/5xx, SSE reconnection |
| 10 | Performance | `lighthouse_audit` | Core Web Vitals, performance score |

---

## Stream 3: Docker Container Log Analysis

### Targets

| Container | Error Patterns |
|-----------|---------------|
| Backend | Unhandled exceptions, deprecation warnings, slow queries, LLM timeouts, tool errors |
| Sandbox | Chrome crashes, OOM kills, CDP failures, supervisord restarts |
| Frontend | Build warnings, HMR errors, asset failures |
| MongoDB | Slow queries, connection pool exhaustion |
| Redis | Memory pressure, eviction, connection refused |
| Qdrant | Index errors, search timeouts |
| Gateway | urllib3 warnings, channel errors |

### Collection Method

- `docker logs --tail 500` per container
- Filter for ERROR, WARNING, CRITICAL, Exception, Traceback
- Count and categorize by severity

---

## Stream 4: Security Audit

### Checks

| # | Check | Method | Target |
|---|-------|--------|--------|
| 1 | OWASP headers | HTTP response inspection | X-Content-Type-Options, X-Frame-Options, CSP, HSTS |
| 2 | Sandbox isolation | Code review (seccomp + capabilities) | No privilege escalation vectors |
| 3 | API auth | Unauthenticated endpoint testing | JWT validation, missing auth on sensitive routes |
| 4 | Input validation | Injection payloads via API | XSS, command injection in chat |
| 5 | Secrets exposure | Log/response inspection | No API keys in responses or logs |
| 6 | Dependencies | requirements.txt + package.json review | Known CVEs |

---

## Stream 5: Integration Seam Validation

### Tests

| # | Seam | Method | Expected |
|---|------|--------|----------|
| 1 | SSE event schema | Parse live stream events | All types match documented schema |
| 2 | Resume cursor | Disconnect/reconnect with `Last-Event-ID` | Correct resume position |
| 3 | Health endpoints | `GET /api/v1/health`, sandbox `/health` | All services healthy |
| 4 | Heartbeat | Monitor idle SSE for 60s | Events every 30s |
| 5 | Sandbox context | Inspect startup sequence | Context ready before first tool call |

---

## Deliverable: Convergence Report

1. **Executive Summary** — Overall readiness score (Red/Yellow/Green)
2. **P0 Issues** — Must fix before production
3. **P1 Issues** — Should fix, degraded experience
4. **P2 Issues** — Nice to fix, minor improvements
5. **Agent Accuracy Scorecard** — Per-prompt results with hallucination flags
6. **Frontend Performance Metrics** — Lighthouse, Core Web Vitals
7. **Container Health Summary** — Error counts, resource usage
8. **Security Findings** — OWASP categorization
9. **Recommended Enhancements** — Prioritized action items

---

## Success Criteria

- All 10 agent prompts evaluated with accuracy scores
- Frontend Lighthouse performance score captured
- All container logs reviewed (last 500 lines each)
- Security headers validated
- All integration seams tested
- Zero P0 issues, or P0 issues documented with remediation plan
