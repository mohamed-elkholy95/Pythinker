# URL Failure Guard — 3-Tier Auto-Correction for LLM URL Hallucination

**Date:** 2026-03-02
**Status:** Approved
**Author:** Claude Code (design), User (requirements)

## Problem

When the LLM (GLM-5 or others) constructs invalid URLs during agent execution:

1. `browser.py` line 451 raises `RuntimeError` on Scrapling 404 instead of returning structured `ToolResult(success=False)`
2. The error propagates as an exception through `invoke_tool()` retry logic — the LLM never sees a clear "404, try different URL" message
3. The LLM re-attempts the same URL because it has no memory of the failure
4. Repeated failures trigger `StuckDetector` → session cancellation instead of graceful recovery

**Root cause observed:** Session `3fdec66859ff45b3` was cancelled after GLM-5 fabricated `https://vuejs.org/guide/best-practices/` (which returns 404). The `wide_research` results contained valid URLs from other domains, but the LLM bypassed them and invented a URL from training knowledge.

## Design

### New Domain Service: `UrlFailureGuard`

**File:** `backend/app/domain/services/agents/url_failure_guard.py`

A session-scoped URL failure tracker with 3-tier escalation that:
- Tracks failed URLs across all steps in a session
- Collects known-good URLs from search results as alternatives
- Provides pre-execution checks and post-failure recording
- Injects correction messages into the LLM conversation context

### Data Models

```python
@dataclass
class UrlFailureRecord:
    url: str                # Normalized URL
    error: str              # "HTTP 404 Not Found"
    attempts: int           # 1, 2, 3...
    first_failed: datetime
    last_failed: datetime
    source_tool: str        # "browser_get_content", "search", etc.

@dataclass
class GuardDecision:
    action: str             # "allow", "warn", "block"
    tier: int               # 1, 2, 3
    message: str | None     # Injection message for LLM context
    alternative_urls: list[str]  # Known-good URLs from search results
```

### 3-Tier Escalation

| Tier | Trigger | Action | LLM sees |
|------|---------|--------|----------|
| **1** | 1st failure of a URL | Return `ToolResult(success=False)` with clear error | "URL returned 404 Not Found. This URL does not exist. Try a different URL from your search results." |
| **2** | 2nd attempt of same URL | Inject warning into LLM context BEFORE execution | "IMPORTANT: You already tried {url} and it returned {error}. Do NOT retry it. Use these URLs instead: [alternatives]" |
| **3** | 3rd attempt of same URL | Hard-block tool call, return synthetic failure | "BLOCKED: {url} has failed {n} times ({error}). Tool call was not executed. Available URLs: [alternatives]. Pick one of these." |

### Public API

```python
class UrlFailureGuard:
    def __init__(self, max_failures_per_url: int = 3) -> None: ...
    def check_url(self, url: str) -> GuardDecision: ...
    def record_failure(self, url: str, error: str, tool: str) -> None: ...
    def record_search_results(self, urls: list[str]) -> None: ...
    def get_failed_urls_summary(self) -> str | None: ...
    def get_metrics(self) -> dict[str, int]: ...
```

### Integration Points

#### 1. `browser.py` line 451 — Fix the RuntimeError bug

```python
# BEFORE (bug):
raise RuntimeError(_result.error or "Scrapling returned no usable content")

# AFTER:
return ToolResult(
    success=False,
    message=f"URL fetch failed: {_result.error or 'No usable content'}. "
            "Try a different URL from your search results.",
)
```

#### 2. `base.py` invoke_tool loop — Pre-check and post-record

Before tool execution:
- Extract URL from tool arguments (check `url`, `query`, `target_url` fields)
- Call `guard.check_url(url)`
- Tier 1 (allow): proceed normally
- Tier 2 (warn): inject warning message, then proceed
- Tier 3 (block): skip execution, return synthetic `ToolResult(success=False)`

After failed tool execution:
- If tool result has `success=False` and args contained a URL, call `guard.record_failure()`

#### 3. `search.py` / `base.py` — Feed search results to guard

When `info_search_web` or `wide_research` returns results, extract all result URLs and call `guard.record_search_results(urls)`. This gives the guard known-valid URLs to suggest as alternatives.

#### 4. `plan_act.py` — Create guard with session scope

Instantiate `UrlFailureGuard()` during flow initialization, pass to `BaseAgent` via constructor or setter. The guard persists across all steps in the session.

#### 5. `config_features.py` — Feature flag

```python
feature_url_failure_guard_enabled: bool = True
```

### Prometheus Metrics

```python
# Counter: total guard actions by tier
pythinker_url_failure_guard_actions_total{tier="1|2|3", action="allow|warn|block"}

# Counter: unique URLs that reached each tier
pythinker_url_failure_guard_escalations_total{tier="2|3"}

# Gauge: current number of failed URLs tracked in session
pythinker_url_failure_guard_tracked_urls
```

### URL Normalization

URLs are normalized before comparison to catch near-duplicates:
- Strip trailing slashes
- Lowercase scheme and host
- Sort query parameters
- Remove fragments (#anchors)

### Flow Diagram

```
LLM calls browser_get_content("https://vuejs.org/guide/best-practices/")
  │
  ▼
guard.check_url() → Tier 1 (first attempt, allow)
  │
  ▼
browser.py → Scrapling → 404
  │
  ▼
return ToolResult(success=False, "URL fetch failed: HTTP 404 Not Found...")
  │
  ▼
guard.record_failure("https://vuejs.org/guide/best-practices/", "404", "browser")
  │
  ▼
LLM sees: "URL fetch failed: HTTP 404. Try a different URL from your search results."
  │
  ▼ (LLM retries same URL)
  │
guard.check_url() → Tier 2 (2nd attempt, warn)
  │
  ▼
Inject into LLM context: "⚠ IMPORTANT: https://vuejs.org/guide/best-practices/ already
  failed (404). Do NOT retry. Use these valid URLs instead:
  - https://vuejs.org/guide/introduction.html
  - https://coreui.io/vue/docs/..."
  │
  ▼ (allow execution — gives LLM one more chance)
  │
  ▼ (LLM STILL retries same URL)
  │
guard.check_url() → Tier 3 (3rd attempt, BLOCK)
  │
  ▼
Skip tool execution. Return synthetic:
  "BLOCKED: This URL failed 2 times. Available URLs: [list]. Pick one."
  │
  ▼
LLM forced to use a different URL → success
```

### Testing Plan

1. **Unit tests** (`test_url_failure_guard.py`):
   - Tier escalation (1→2→3 on same URL)
   - URL normalization (trailing slash, case, query params)
   - Alternative URL suggestion from recorded search results
   - Metrics correctness
   - Different URLs don't interfere with each other

2. **Integration tests**:
   - Mock Scrapling 404 → verify `ToolResult(success=False)` returned (not RuntimeError)
   - Simulate 3 attempts to same URL → verify tier escalation messages
   - Verify search result URLs are collected and suggested

3. **Regression**: All existing tests must pass unchanged

### Files Changed

| File | Change |
|------|--------|
| `url_failure_guard.py` (NEW) | Core domain service |
| `test_url_failure_guard.py` (NEW) | Unit tests |
| `browser.py` | Replace `raise RuntimeError` with `return ToolResult(success=False)` |
| `base.py` | Add guard pre-check/post-record in `invoke_tool()` |
| `plan_act.py` | Create guard, pass to executor |
| `config_features.py` | Add `feature_url_failure_guard_enabled` flag |
| `search.py` | Feed search result URLs to guard |
