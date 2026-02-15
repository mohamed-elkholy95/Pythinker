# Browser CDP Timeout & Screenshot Recovery - Implementation Summary

**Date:** 2026-02-15
**Status:** ✅ COMPLETE - All P0 and P1 fixes implemented

## Problem Summary

Heavy ad-laden pages from previous sessions caused CDP `Page.captureScreenshot` to hang, triggering cascading failures:
- 4-6s timeout → 503 from all screenshot tiers → circuit breaker opens → never recovers
- Root cause: `block_resources=False` default + no page cleanup on reuse = Chrome main thread saturation
- Observed impact: 119s navigation times, 100% CDP failure rate, circuit breaker stuck OPEN

## Implementation Status

### ✅ P0 — Critical Fixes (Stop the Bleeding)

#### P0.1: Enable Resource Blocking by Default
**Files Modified:**
- `backend/app/infrastructure/external/sandbox/docker_sandbox.py:1288`
- `backend/app/domain/services/agent_domain_service.py:296,307,323,1371`

**Changes:**
- Changed `get_browser()` default from `block_resources=False` to `block_resources=True`
- Updated all 4 call sites to explicitly pass `block_resources=True` for clarity

**Impact:** Prevents ad/tracker requests from saturating Chrome by default

---

#### P0.2: Navigate to about:blank Before Page Reuse
**Files Modified:**
- `backend/app/infrastructure/external/browser/playwright_browser.py:1310-1328`

**Changes:**
- Before reusing existing page, navigate to `about:blank` with 5s timeout
- If navigation fails, close page and create fresh one
- Prevents reusing pages with heavy ad content from previous sessions

**Impact:** Clears Chrome's main thread before any new work, preventing timeout cascade

---

#### P0.3: Always-On Ad/Tracker URL Blocking
**Files Modified:**
- `backend/app/infrastructure/external/browser/playwright_browser.py:781-808`

**Changes:**
- Separated ad/tracker blocking from resource type blocking
- Ad/tracker URLs now ALWAYS blocked at context level (independent of `block_resources` flag)
- Resource types (images, fonts, stylesheets) only blocked when `block_resources=True`

**Impact:** Prevents ad network URLs from ever loading, regardless of settings

---

#### P0.4: Expand Blocked URL Patterns
**Files Modified:**
- `backend/app/infrastructure/external/browser/playwright_browser.py:76-109`

**Changes:**
Added 15 major ad exchange domains observed in failing sessions:
- pubmatic.com, casalemedia.com, openx.net
- rubiconproject.com, criteo.com, taboola.com
- outbrain.com, amazon-adsystem.com, adsrvr.org
- bidswitch.net, sharethrough.com, spotxchange.com
- indexexchange.com, moatads.com, doubleverify.com
- aps.amazon

**Impact:** Comprehensive blocking of ad networks that cause thread saturation

---

### ✅ P1 — Improvements (Better Recovery)

#### P1.1: CDP Health Check with Complexity Awareness
**Files Modified:**
- `backend/app/infrastructure/external/browser/playwright_browser.py:373-433`

**Changes:**
- Enhanced `_quick_health_check()` to check page complexity
- If page is heavy (high iframe/element count), proactively navigate to `about:blank`
- Uses existing `_get_page_complexity()` method

**Impact:** Catches heavy pages early before they cause CDP timeouts

---

#### P1.2: Sandbox CDP Timeout + Reconnect-on-Timeout
**Files Modified:**
- `sandbox/app/services/cdp_screencast.py:35,357-390`

**Changes:**
- Increased `_CAPTURE_COMMAND_TIMEOUT` from 4.0s to 6.0s
- Detect timeout (result is `None`) and force reconnect via `_cleanup_stale_connection()`
- Prevents subsequent requests from using dead connection

**Impact:** More time for heavy pages + automatic recovery from timeouts

---

#### P1.3: Skip CDP After Consecutive Failures
**Files Modified:**
- `sandbox/app/api/v1/vnc.py:147-233`

**Changes:**
- Added failure tracking: `_cdp_consecutive_failures`, `_cdp_skip_until`
- Skip CDP tier after 3 consecutive failures
- 30-second cooldown before retrying CDP
- Resets counter on successful capture

**Impact:** Stops wasting 4-6s per request when CDP is known-failing

---

#### P1.4: Circuit Breaker Recovery Tuning
**Files Modified:**
- `backend/app/application/services/screenshot_service.py:42-46,70-79`

**Changes:**
- Reduced max failures: 5 → 3 (enter OPEN state sooner)
- Increased recovery timeout: 60s → 120s (more time for Chrome to stabilize)
- Reduced required successes: 2 → 1 (faster recovery from HALF_OPEN)

**Impact:** Less user-facing pain, better recovery dynamics

---

#### P1.5: Browser Cleanup on New Session Start
**Files Modified:**
- `backend/app/domain/services/agent_domain_service.py:293-309`

**Changes:**
- After getting browser for new session, navigate to `about:blank`
- Only when `should_clear_browser=True`
- Best-effort cleanup (non-fatal if fails)

**Impact:** Ensures clean slate for new sessions, even if previous session left heavy page

---

## Key Architecture Changes

### 1. Separation of Concerns: Ad Blocking vs Resource Blocking

**Before:**
- Single `block_resources` flag controlled both ad URLs and resource types
- Default was `False`, allowing ads to load

**After:**
- Ad/tracker URLs: **ALWAYS blocked** at context level
- Resource types: Only blocked when `block_resources=True`
- Default is now `True`, providing protection by default

**Why:** Ad network iframes cause more Chrome thread saturation than images/fonts. Always blocking them prevents root cause of timeouts.

---

### 2. Proactive Page Cleanup

**Before:**
- Pages reused across sessions without cleanup
- Heavy pages from previous sessions persisted

**After:**
- Navigate to `about:blank` before reuse (P0.2)
- Navigate to `about:blank` on new session start (P1.5)
- Navigate to `about:blank` when heavy page detected (P1.1)

**Why:** Chrome's main thread stays saturated if heavy content remains loaded. Clearing to blank frees resources.

---

### 3. Multi-Tier Failure Tracking

**Before:**
- Screenshot service circuit breaker was the only failure protection
- CDP tier retried every request even when known-failing

**After:**
- CDP tier has its own failure tracking (P1.3)
- Skips tier during cooldown period
- Circuit breaker tuned for better recovery (P1.4)

**Why:** Prevents wasting time on known-bad paths, allows faster fallback to working tiers.

---

## Testing & Validation

### Linting
```bash
# Backend
cd backend && uvx ruff check app/infrastructure/external/browser/playwright_browser.py \
  app/infrastructure/external/sandbox/docker_sandbox.py \
  app/domain/services/agent_domain_service.py \
  app/application/services/screenshot_service.py
# ✅ All checks passed!

# Sandbox
cd sandbox && uvx ruff check app/services/cdp_screencast.py app/api/v1/vnc.py
# ✅ All checks passed!
```

### Expected Improvements

1. **Session Start Time:** Heavy page navigation should drop from 119s to <10s
2. **CDP Success Rate:** Should improve from 0% to >90% on normal pages
3. **Circuit Breaker Recovery:** Should recover within 120s instead of staying stuck OPEN
4. **Screenshot Latency:** CDP tier skip during cooldown reduces wasted time

### Integration Testing Recommended

1. Start new session with ad-heavy URL (e.g., news site)
2. Verify screenshots work within 5s
3. Simulate CDP failure (kill Chrome DevTools)
4. Verify circuit breaker enters OPEN state after 3 failures
5. Verify recovery to CLOSED state after 120s

---

## Files Modified (9 total)

| File | Changes | Lines |
|------|---------|-------|
| `backend/app/infrastructure/external/browser/playwright_browser.py` | P0.2, P0.3, P0.4, P1.1 | 76-109, 781-808, 1310-1328, 373-433 |
| `backend/app/infrastructure/external/sandbox/docker_sandbox.py` | P0.1 | 1288 |
| `backend/app/domain/services/agent_domain_service.py` | P0.1, P1.5 | 296-309, 310-318, 326-334, 1371-1375 |
| `backend/app/application/services/screenshot_service.py` | P1.4 | 42-46, 70-79 |
| `sandbox/app/services/cdp_screencast.py` | P1.2 | 35, 357-390 |
| `sandbox/app/api/v1/vnc.py` | P1.3 | 147-233 |

---

## Rollback Plan

If issues arise, revert in reverse order:
1. P1.x changes (improvements) can be reverted independently
2. P0.4 (URL patterns) can be reduced if blocking too much
3. P0.3 (always-on blocking) can be made conditional again
4. P0.2 (page cleanup) can be disabled
5. P0.1 (default True) can be reverted to False

Each change is independent and can be rolled back via git revert.

---

## Next Steps (P2 - Polish, Future Work)

1. **P2.1:** Pre-compiled regex for URL patterns (performance)
2. **P2.2:** Frontend circuit breaker status indicator
3. **P2.3:** Adaptive CDP timeout (6s first attempt, 3s subsequent)
4. **P2.4:** Iframe count check before screenshot
5. **P2.5:** Feature flags for gradual rollout

These are polish items and can be implemented after P0/P1 are proven stable in production.

---

## Metrics to Monitor

- `pythinker_browser_navigate_duration_seconds` (should drop from 119s to <10s)
- `pythinker_screenshot_capture_total{backend="cdp",status="success"}` (should increase)
- `pythinker_screenshot_circuit_state` (should transition OPEN → HALF_OPEN → CLOSED)
- `pythinker_screenshot_capture_duration_seconds` (should reduce due to CDP skip logic)

---

**Implementation Complete:** All P0 and P1 items ✅
**Linting:** All files pass ✅
**Ready for:** Testing and deployment
