# Telegram Session Reliability Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the Telegram session runtime crash and harden gateway/agent reliability paths that produced repeated anomalies in the live monitoring report.

**Architecture:** Apply targeted defensive fixes in backend domain/infrastructure services with minimal behavior surface change: normalize datetime arithmetic inputs, make watchdog processing-aware, preserve search budget for follow-up verification, degrade safely on HTTP error pages, and harden anti-loop/truncation control logic.

**Tech Stack:** Python 3.12, asyncio, Pydantic v2, Playwright, pytest.

---

### Task 1: Datetime Crash Fix (`offset-naive` vs `offset-aware`)

**Files:**
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Test: `backend/tests/domain/services/test_agent_domain_service_chat_teardown.py`

**Steps:**
1. Add timezone-normalization helper for datetimes in `AgentDomainService`.
2. Use helper in RUNNING/no-task stale-age arithmetic path.
3. Add regression test with naive `session.updated_at` ensuring no crash and expected event output.

### Task 2: Poll Watchdog False-Positive Reduction

**Files:**
- Modify: `backend/app/infrastructure/external/channels/nanobot_gateway.py`
- Test: `backend/tests/infrastructure/external/channels/test_nanobot_gateway.py`

**Steps:**
1. Track inbound in-flight processing timestamp.
2. Update watchdog timeout handling to distinguish idle poll inactivity from active long-running message processing.
3. Add tests proving no warning during normal in-flight processing and warning after excessive in-flight stall.

### Task 3: Search Budget Durability + Quota Degradation

**Files:**
- Modify: `backend/app/domain/services/tools/search.py`
- Test: `backend/tests/domain/services/tools/test_search_budget.py`

**Steps:**
1. Reserve a small per-task API call budget for follow-up verification by constraining `wide_research` query trimming.
2. Add quota-error detection helper and browser fallback path for quota-exhausted API search failures.
3. Add tests covering reserved-budget behavior and quota-triggered fallback logic.

### Task 4: Browser 4xx/5xx Handling for Reliability

**Files:**
- Modify: `backend/app/domain/services/tools/browser.py`
- Test: `backend/tests/domain/services/tools/test_browser_url_dedup.py`

**Steps:**
1. Treat HTTP `status >= 400` from navigation as failed retrieval with actionable message.
2. Preserve extracted diagnostics in `data` while returning `success=False`.
3. Add regression test verifying `browser_navigate` marks 404 pages as failed.

### Task 5: Stronger Repetitive-Tool Loop Hard Stop

**Files:**
- Modify: `backend/app/domain/services/agents/tool_efficiency_monitor.py`
- Test: `backend/tests/domain/services/agents/test_tool_efficiency_monitor.py`

**Steps:**
1. Escalate repetitive browser-read tool loops (`browser_navigate` / `browser_get_content`) to immediate hard-stop at repetition threshold.
2. Keep existing generic behavior unchanged for non-browser tools.
3. Add unit test validating immediate hard-stop on browser loop threshold.

### Task 6: Truncation Recovery Hardening

**Files:**
- Modify: `backend/app/domain/services/agents/base.py`
- Test: `backend/tests/domain/services/agents/test_truncation_recovery_fixes.py`

**Steps:**
1. On partial/malformed tool-call truncation, enforce retry with reduced token ceiling for next attempt.
2. Escalate consecutive truncations to stronger guidance and tool suppression sooner in-loop.
3. Add regression test asserting reduced-token retry behavior is triggered after truncation.

### Task 7: Verification

**Files:**
- N/A (commands)

**Steps:**
1. Run targeted pytest files for modified areas.
2. Run backend checks required by repo policy: `ruff check .`, `ruff format --check .`, `pytest tests/` (or report if full suite is too costly).
3. Summarize results with exact pass/fail evidence.
