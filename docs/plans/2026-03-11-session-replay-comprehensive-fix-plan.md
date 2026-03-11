# Session Replay Comprehensive Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make session replay durable and faithful by fixing the `fast_search` event schema bug, preserving replay screenshots while live preview is active, reducing history loss from noisy persisted events, and correcting frontend replay defaults for chat and shared replay views.

**Architecture:** The fix is split across backend event/screenshot persistence and frontend replay consumption. Backend changes make replay artifacts durable and lower-noise. Frontend changes stop defaulting completed sessions to the terminal report state and improve shared replay handling for persisted session events.

**Tech Stack:** Python, Pydantic v2, FastAPI, Vue 3, Vitest, Pytest

---

### Task 1: Add Backend Regression Tests For `fast_search` Event Schema

**Files:**
- Create: `backend/tests/domain/services/flows/test_fast_search_flow.py`
- Modify: `backend/app/domain/services/flows/fast_search.py`

**Step 1: Write the failing test**

Add a unit test that runs `FastSearchFlow.run()` with stubbed LLM and search engine and asserts:
- the emitted calling and called events are valid `ToolEvent` instances
- `tool_name == "info_search_web"`
- `function_args == {"query": ...}`
- the called event keeps a structured `ToolResult`

**Step 2: Run test to verify it fails**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/flows/test_fast_search_flow.py -q
```

Expected: failure from invalid `ToolEvent` construction using old field names.

**Step 3: Write minimal implementation**

Update `FastSearchFlow` so it emits `ToolEvent(tool_name=..., function_args=..., function_result=...)` and keeps the real search `ToolResult`.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

---

### Task 2: Add Backend Regression Tests For Screenshot Replay Persistence

**Files:**
- Modify: `backend/tests/application/services/test_screenshot_service_metrics.py`
- Modify: `backend/app/application/services/screenshot_service.py`

**Step 1: Write failing tests**

Add tests that assert:
- periodic capture still persists while screencast is active
- duplicate periodic captures still write screenshot metadata instead of returning `None`

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/application/services/test_screenshot_service_metrics.py -q
```

Expected: failure because periodic screencast capture is skipped and duplicate periodic frames are dropped.

**Step 3: Write minimal implementation**

Change `ScreenshotCaptureService.capture()` so:
- periodic screenshots are no longer suppressed when screencast is active
- duplicate periodic frames reuse the original storage key but still persist metadata for replay timeline continuity

**Step 4: Re-run tests**

Run the same pytest command and confirm green.

---

### Task 3: Reduce Lossy Session History Persistence

**Files:**
- Modify: `backend/tests/domain/services/test_agent_task_runner_progress_filter.py`
- Modify: `backend/app/domain/services/agent_task_runner.py`

**Step 1: Write failing tests**

Add tests for a new session-history persistence gate asserting:
- `StreamEvent` is not persisted to session history
- `ToolStreamEvent` is not persisted to session history
- meaningful events like `ReportEvent`, `PlanEvent`, and `ToolEvent` are still persisted

**Step 2: Run tests to verify they fail**

Run:

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_task_runner_progress_filter.py -q
```

Expected: failure because all events are currently persisted by `_put_and_add_event()`.

**Step 3: Write minimal implementation**

Introduce a small persistence filter in `AgentTaskRunner` so high-volume streaming-only events stay live-only while replay-relevant events remain durable.

**Step 4: Re-run tests**

Run the same pytest command and confirm green.

---

### Task 4: Add Frontend Regression Tests For Completed Replay Defaults

**Files:**
- Create: `frontend/tests/composables/useScreenshotReplay.spec.ts`
- Modify: `frontend/tests/components/ToolPanelContent.spec.ts`
- Modify: `frontend/src/composables/useScreenshotReplay.ts`
- Modify: `frontend/src/components/ToolPanel.vue`
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Modify: `frontend/src/pages/ChatPage.vue`

**Step 1: Write failing tests**

Add tests that assert:
- screenshot replay can load from the first frame for completed sessions
- completed replay does not immediately cover the replay frame with the persisted final report when the user is at an earlier replay frame

**Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend && bun run vitest run tests/composables/useScreenshotReplay.spec.ts tests/components/ToolPanelContent.spec.ts
```

Expected: failure because replay starts from the last frame and the final report still takes priority in replay mode.

**Step 3: Write minimal implementation**

Implement:
- `useScreenshotReplay.loadScreenshots({ startAt })`
- completed-session load from the first replay frame
- ToolPanel props for current replay index
- ToolPanelContent logic that only shows the persisted final report when the replay is actually at the latest frame

**Step 4: Re-run tests**

Run the same Vitest command and confirm green.

---

### Task 5: Add Frontend Regression Tests For Shared Replay Coverage

**Files:**
- Create: `frontend/tests/pages/SharePage.spec.ts`
- Modify: `frontend/src/pages/SharePage.vue`

**Step 1: Write failing tests**

Add tests that assert:
- shared replay keeps `report` events visible
- shared replay filters high-volume `stream` events out of timeline playback
- shared replay can surface progress messages instead of collapsing directly to the terminal state

**Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend && bun run vitest run tests/pages/SharePage.spec.ts
```

Expected: failure because `SharePage` ignores `report` and uses the raw event stream for replay.

**Step 3: Write minimal implementation**

Update `SharePage` so replay/restore use a filtered event list, support `report` events, and display meaningful progress messages for replay instead of silently ignoring them.

**Step 4: Re-run tests**

Run the same Vitest command and confirm green.

---

### Task 6: Run Focused Verification

**Files:**
- No code changes required unless verification reveals regressions

**Step 1: Run backend targeted suite**

```bash
conda activate pythinker && cd backend && pytest -p no:cov -o addopts= \
  tests/domain/services/flows/test_fast_search_flow.py \
  tests/application/services/test_screenshot_service_metrics.py \
  tests/domain/services/test_agent_task_runner_progress_filter.py -q
```

**Step 2: Run frontend targeted suite**

```bash
cd frontend && bun run vitest run \
  tests/composables/useScreenshotReplay.spec.ts \
  tests/components/ToolPanelContent.spec.ts \
  tests/pages/SharePage.spec.ts \
  tests/composables/useStreamingPresentationState.spec.ts
```

**Step 3: Run repo-required broader checks touched by this work**

```bash
cd frontend && bun run lint && bun run type-check
```

```bash
conda activate pythinker && cd backend && ruff check .
```

**Step 4: Manually validate the reproduced flows**

Re-run:
- one `fast_search` session to confirm it completes
- one completed session replay to confirm it starts from early frames and progresses
- one shared replay to confirm `report` and progress states appear

