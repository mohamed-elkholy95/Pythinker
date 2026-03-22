# Session Monitoring Fixes — Batch 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 9 bugs discovered during live monitoring of sessions `8450c082bf0e461a` and `7b0152d3fcbc4d95`.

**Architecture:** Backend fixes in DDD domain services (output_verifier, guardrails, response_generator, agent_task_runner, planner). Frontend fixes in Vue composables and components (streaming state, MonacoEditor, main.ts, TiptapReportEditor). Each fix is independent and can be committed atomically.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic v2), Vue 3 (TypeScript, Composition API), marked v17, Monaco Editor

---

### Task 1: Fix Report Content Truncation (Critical)

**Files:**
- Modify: `backend/app/domain/services/agent_task_runner.py:735-851` (`_ensure_report_file`)
- Modify: `backend/app/domain/services/agent_task_runner.py:1053-1067` (`_get_pre_trim_report_content`)
- Test: `backend/tests/domain/services/test_agent_task_runner_report_file.py`

**Root Cause:** `_get_pre_trim_report_content()` returns None when `_pre_trim_report_cache` wasn't populated → only 665B summary `report-{id}.md` written to sandbox → that's the only file synced to MinIO.

**Fix:** When `_pre_trim_report_cache` is empty, fall back to `ResponseGenerator.extract_report_from_file_write_memory()` to recover the full report from tool call history. Also: reorder attachments so the full report is FIRST (primary download).

**Step 1:** Write tests for the fallback and attachment ordering.
**Step 2:** In `_get_pre_trim_report_content`, add fallback to `extract_report_from_file_write_memory()`.
**Step 3:** In `_ensure_report_file`, reorder so full-report FileInfo is inserted at position 0.
**Step 4:** Run tests, commit.

---

### Task 2: Fix Caveat Raw Markdown Rendering (Critical)

**Files:**
- Modify: `frontend/src/components/report/TiptapReportEditor.vue:89-94`
- Test: manual verification via browser

**Root Cause:** `TiptapReportEditor.vue` does NOT call `normalizeInlineAlerts()` before `marked.parse()`, unlike `TiptapMessageViewer.vue` which calls it at line 133. GFM alert syntax `> [!NOTE]` or blockquote caveats are not properly processed.

**Fix:** Import and call `normalizeInlineAlerts()` in TiptapReportEditor's computed `htmlContent`. Also collapse excess blank lines like TiptapMessageViewer does.

**Step 1:** Add `normalizeInlineAlerts` import from TiptapMessageViewer (or extract to shared util).
**Step 2:** Insert the call in `htmlContent` computed between `linkifyInlineCitations` and `marked.parse`.
**Step 3:** Verify via browser that caveats render as styled blockquotes.
**Step 4:** Commit.

---

### Task 3: Fix MonacoEditor Uncaught Promise (Medium)

**Files:**
- Modify: `frontend/src/components/ui/MonacoEditor.vue:230-235`

**Fix:** Wrap `editor.dispose()` in try-catch to swallow async Worker cleanup errors.

**Step 1:** Add try-catch around dispose, log warning on error instead of crashing.
**Step 2:** Commit.

---

### Task 4: Fix Streaming State Reset Warnings (Medium)

**Files:**
- Modify: `frontend/src/constants/streamingPresentation.ts:29-35`
- Modify: `frontend/src/composables/useStreamingPresentationState.ts:141-148`

**Root Cause:** `VALID_PHASE_TRANSITIONS` is missing `planning → thinking` when planText clears before tool events arrive. The state machine resets 8 times per session.

**Fix:** The transitions already include `planning → thinking` (line 31). The real issue is that `desiredPhase` rapidly oscillates between phases when inputs change in quick succession. Add a guard: if the desired phase is `idle` but we were in `planning`/`thinking` and active operation signals are still pending, don't transition to idle — stay in current phase.

**Step 1:** In `desiredPhase` computed, add guard: if current phase is `planning` or `thinking` and `activeOperation` is true, don't return `idle`.
**Step 2:** In `resetToSafeState`, only reset if the mismatch persists for >1 frame (debounce).
**Step 3:** Commit.

---

### Task 5: Fix Right Panel Stale After Fast-Path (Medium)

**Files:**
- Modify: `frontend/src/composables/useStreamingPresentationState.ts`

**Root Cause:** For fast-path (knowledge intent), no PlanEvent fires, so the synthetic planning tool status stays frozen. The `desiredPhase` computed should transition to `summary_final` or `idle` when a DoneEvent arrives, but the inputs that drive it (summaryStreamText, finalReportText) may not be set for fast-path flows.

**Fix:** The `desiredPhase` already returns `idle` when no signals are active. The stale state is caused by `planText.length > 0` being true from the initial "Creating plan..." text that was set before fast-path completed. The fix: when `finalReportText` or a done signal arrives, clear `planPresentationText` to allow `idle` transition.

This is handled in ChatPage.vue where DoneEvent clears state — needs to also clear `planPresentationText`.

**Step 1:** Find where DoneEvent is handled in ChatPage.vue and ensure it clears `planPresentationText`.
**Step 2:** Commit.

---

### Task 6: Fix Unhandled Promise Rejection Handler (Medium)

**Files:**
- Modify: `frontend/src/main.ts:88-91`

**Fix:** Improve error logging, filter expected AbortError/Canceled rejections.

**Step 1:** Replace handler with one that logs constructor name + message and filters abort errors.
**Step 2:** Commit.

---

### Task 7: Fix OutputGuardrails False Positive (Low)

**Files:**
- Modify: `backend/app/domain/services/agents/guardrails.py:685-715`
- Test: `backend/tests/domain/services/agents/test_guardrails_relevance.py`

**Root Cause:** Word-overlap heuristic with 0.3 threshold is too strict when output vocabulary differs from query.

**Fix:** Lower threshold to 0.15 AND add the report title words to the output word set (title is always relevant to the query).

**Step 1:** Write test for relevance check with summarized output.
**Step 2:** Lower threshold, add title-augmentation.
**Step 3:** Run tests, commit.

---

### Task 8: Fix Suggested Follow-Ups Awkward Phrasing (Low)

**Files:**
- Modify: `backend/app/domain/services/agents/response_generator.py:1110-1132`

**Root Cause:** Raw keyword tokens injected into templates produce unnatural phrasing like "Can you expand on best practices python".

**Fix:** Restructure templates to use quoted topic format and add a grammar-aware joiner.

**Step 1:** Change templates to use quoted topic: `"Can you expand on '{topic}' with an example?"` and add "the" article when topic starts with an adjective.
**Step 2:** Run existing tests, commit.

---

### Task 9: Fix Complexity Assessment Mismatch (Low)

**Files:**
- Modify: `backend/app/domain/services/agents/planner.py:200-268`
- Test: `backend/tests/domain/services/agents/test_planner_complexity.py`

**Root Cause:** `get_task_complexity()` defaults to "medium" for queries with no keyword matches. Should check `is_research_task_message()` BEFORE the simple-indicator check, and short queries without any indicators should default to "simple" not "medium".

**Fix:** The function already has `is_research_task_message()` at line 253 — but it fires AFTER the simple check. For the vector DB query "Compare the top 3...", "compare" IS in `complex_indicators`, so `complex_count=1`. With `word_count=22` (not >50) and `complex_count=1` (not >=2), it falls through to "medium". Fix: reduce the complex_count threshold to >=1 for research tasks, or use `is_research_task_message()` earlier.

**Step 1:** Move `is_research_task_message()` check to the top of the function (before simple check).
**Step 2:** Also: if `complex_count >= 1 and simple_count == 0`, return "complex" instead of requiring >=2.
**Step 3:** Write test, run tests, commit.
