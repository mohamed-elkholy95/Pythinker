# Session Reliability Fixes — Design Spec

**Date:** 2026-04-08
**Scope:** 4 targeted fixes from live session monitoring (agent `ddfc494ed287423b`)
**Approach:** Minimal, surgical, KISS/DRY compliant

---

## Fix 1: Add Plotly to Sandbox Runtime

**Problem:** `No module named 'plotly'` — chart generation fails, falls back to legacy SVG.
Plotly is in `requirements.addons.txt` but not in `requirements.runtime.txt`.

**Change:** Add `plotly>=6.0` and `kaleido>=1.0.0` to `sandbox/requirements.runtime.txt`.

**Files:** `sandbox/requirements.runtime.txt` (+2 lines)

**Why not Dockerfile.plotly?** That requires a separate build strategy. Adding to runtime makes charts always available with zero config. The packages add ~30MB — acceptable for the standard image.

**Why not ENABLE_SANDBOX_ADDONS=1?** That installs all addons (code-server, etc.) — violates KISS.

**Verification:** `docker compose build sandbox && docker compose up -d sandbox` then check
`/opt/base-python-venv/bin/python3 -c "import plotly; import kaleido; print('ok')"` inside sandbox.

---

## Fix 2: Separate Browser Extract Timeout

**Problem:** `browser_agent_extract` uses the same 300s timeout as full browser agent tasks. Extract operations are simpler (15 max steps vs 25) and should fail faster.

**Change:** Add `browser_agent_extract_timeout: int = 120` to `config_sandbox.py`. Use it in `browser_agent.py`'s `browser_agent_extract()` method when computing the timeout.

**Files:**
- `backend/app/core/config_sandbox.py` — add field (+1 line)
- `backend/app/domain/services/tools/browser_agent.py` — pass extract timeout to `_run_agent_task()` (+3 lines)

**Design:** `browser_agent_extract()` currently calls `_run_agent_task(task, url, max_steps=15)`. The `_run_agent_task` method reads `self._settings.browser_agent_timeout`. We add an optional `timeout_override` parameter to `_run_agent_task()` and pass `browser_agent_extract_timeout` from config when calling from `browser_agent_extract()`.

**Verification:** Run a browser extract task; confirm timeout warning appears at ~120s instead of 300s.

---

## Fix 3: Increase Instructor max_retries for Structured Output

**Problem:** MiniMax M2.7 returns markdown/prose instead of JSON. Instructor's `max_retries=1` means only 2 internal attempts. The JSON recovery layer catches some failures, but chart analysis specifically failed on attempt 1 and succeeded on attempt 2 after 21.6s wasted.

**Change:** Increase instructor `max_retries` from 1 to 2 in `openai_llm.py` `ask_structured()`.

**Files:** `backend/app/infrastructure/external/llm/openai_llm.py` — change `max_retries=1` to `max_retries=2` (+0 lines, 1 value change)

**Why not more?** Each retry costs a full LLM call. 3 internal attempts (max_retries=2) with 4 outer attempts = 12 max calls. Sufficient for MiniMax's intermittent prose responses without excessive cost.

**Verification:** Check logs for `attempt=` counts on structured output calls; confirm chart analysis succeeds on first or second internal attempt.

---

## Fix 4: Allow One Retry on Step Action Audit Failure

**Problem:** Step action audit runs AFTER the retry loop exits (`plan_act.py` line 3849). When a step passes execution but fails audit (e.g., "research" keyword expected but only file tools used), the step is marked FAILED with no retry opportunity.

**Change:** Move the audit check inside the retry loop so that an audit failure triggers one additional attempt. Guard with a counter to prevent infinite audit-retry loops.

**Design:**
```
for attempt in range(max_attempts):
    ... execute step ...
    if step.success:
        audit_failed = self._apply_step_action_audit(step, tools_used)
        if audit_failed and not audit_retried:
            audit_retried = True
            step.success = False  # Reset for retry
            step.status = ExecutionStatus.PENDING
            logger.info("Step %s failed action audit, retrying once", step.id)
            continue  # Re-enter retry loop
        break  # Exit loop (success or already retried)
```

**Files:** `backend/app/domain/services/flows/plan_act.py` — restructure lines ~3849-3869 into the retry loop (~15 lines moved + 5 lines guard logic)

**Why only 1 retry?** If the agent ignores required actions twice, a third attempt won't help. One retry gives the LLM a chance with the audit error injected as context.

**Verification:** Targeted test in `tests/domain/services/flows/test_step_action_audit.py` — mock a step that fails audit, confirm it retries once.

---

## Out of Scope (Working Correctly)

| Issue | Why No Fix |
|-------|-----------|
| Hallucination flags | Detection working as designed, correctly appending disclaimers |
| Context cap hit (100K) | Graceful graduated truncation already in place |
| 175s TTFT summarization | Within expected range for large-context MiniMax; timeout specifically raised to 150s |
| Delivery integrity warnings | Informational, auto-repair exists for artifact references |
| Fixed message sequence | Defensive behavior running every LLM call, prevents API errors |
