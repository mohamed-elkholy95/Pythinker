# Chat Page Hierarchy And Sanitization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the chat-page execution redesign so parent steps dominate the hierarchy, child activity renders inside one inset grouped container, and leaked internal markers such as `[Previously called info_search_web]` never appear in live, replay, or shared transcripts.

**Architecture:** Build on the current branch, which already suppresses blank assistant placeholders and collapses repeated skill headers. Finish the work by centralizing execution-text sanitization, making child activity labels sanitize-or-drop before render, moving step child content into one inset rail container, and adding collapsed parent previews plus replay/share parity through shared transcript preparation.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, Vite, ESLint

**Spec:** `docs/superpowers/specs/2026-04-04-chat-page-hierarchy-and-sanitization-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/utils/messageSanitizer.ts` | Modify | Low-level execution-text cleanup for leaked metadata markers and sanitize-or-drop helpers |
| `frontend/src/utils/__tests__/messageSanitizer.spec.ts` | Modify | Regression coverage for `[Previously called ...]` and related leaked markers |
| `frontend/src/utils/executionActivity.ts` | Create | Shared child-activity label derivation and collapsed-preview summarization |
| `frontend/src/utils/__tests__/executionActivity.spec.ts` | Create | TDD for child labels, dropped empty activity rows, and collapsed summaries |
| `frontend/src/utils/sessionHistory.ts` | Modify | Replay/session-history sanitation before synthetic transcript recovery |
| `frontend/src/utils/__tests__/sessionHistory.spec.ts` | Modify | Replay parity tests for sanitized recovered assistant messages |
| `frontend/src/components/ToolUse.vue` | Modify | Sanitize-or-drop inline child activity text and prefer clean user-facing labels |
| `frontend/tests/components/ToolUse.spec.ts` | Modify | Component tests for sanitized inline child activity behavior |
| `frontend/src/components/ChatMessage.vue` | Modify | Parent step card hierarchy, inset child activity rail, grouped skill container, collapsed previews |
| `frontend/tests/components/ChatMessage.spec.ts` | Modify | Component regressions for grouped hierarchy, child inset rail, and collapsed previews |
| `frontend/src/pages/ChatPage.vue` | Modify | Preserve live transcript grouping with the new preview/sanitization helpers |
| `frontend/src/pages/SharePage.vue` | Modify only if required | Keep shared transcript rendering aligned with sanitized visible output; avoid changes unless tests prove they are needed |
| `frontend/tests/pages/SharePage.recovery.spec.ts` | Modify | Shared transcript regression for sanitized recovered content |

## Chunk 1: Shared sanitization and replay parity

### Task 1: Capture the remaining metadata leak with focused failing tests

**Files:**
- Modify: `frontend/src/utils/__tests__/messageSanitizer.spec.ts`
- Modify: `frontend/src/utils/__tests__/sessionHistory.spec.ts`
- Modify: `frontend/tests/pages/SharePage.recovery.spec.ts`

- [ ] **Step 1: Add a sanitizer regression for bare `[Previously called ...]` markers**

Add a unit test in `frontend/src/utils/__tests__/messageSanitizer.spec.ts` that passes text containing only `[Previously called info_search_web]` and expects the sanitizer to return an empty string.

- [ ] **Step 2: Add a mixed-content sanitizer regression**

Add a unit test in `frontend/src/utils/__tests__/messageSanitizer.spec.ts` that passes `Searching retailers\n[Previously called info_search_web]` and expects only `Searching retailers` to survive.

- [ ] **Step 3: Add a replay recovery regression**

Extend `frontend/src/utils/__tests__/sessionHistory.spec.ts` so `resolveSessionHistory()` recovers a synthetic assistant message from `latest_message` after stripping both leaked tool-call wrappers and bare `[Previously called ...]` markers.

- [ ] **Step 4: Add a shared-page regression**

Extend `frontend/tests/pages/SharePage.recovery.spec.ts` so a recovered shared session whose `latest_message` contains `[Previously called info_search_web]` still mounts cleanly and only surfaces sanitized text to the mocked transcript path.

- [ ] **Step 5: Run the focused tests and confirm they fail for the intended reason**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run src/utils/__tests__/messageSanitizer.spec.ts src/utils/__tests__/sessionHistory.spec.ts tests/pages/SharePage.recovery.spec.ts
```

Expected:
- at least one failure asserting that `[Previously called ...]` still leaks today
- no unrelated import or mount failures

- [ ] **Step 6: Commit the failing-test checkpoint**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/src/utils/__tests__/messageSanitizer.spec.ts frontend/src/utils/__tests__/sessionHistory.spec.ts frontend/tests/pages/SharePage.recovery.spec.ts
git commit -m "test(frontend): capture execution metadata leak regressions"
```

### Task 2: Centralize sanitize-or-drop behavior for replay and shared transcripts

**Files:**
- Modify: `frontend/src/utils/messageSanitizer.ts`
- Modify: `frontend/src/utils/sessionHistory.ts`
- Modify: `frontend/src/pages/SharePage.vue` only if the tests prove a page-level gap after shared helpers are fixed

- [ ] **Step 1: Add one shared helper for visible execution text**

In `frontend/src/utils/messageSanitizer.ts`, add a helper dedicated to user-visible execution text, for example `sanitizeVisibleExecutionText(text)`, that:
- strips leaked tool wrappers
- strips bare `[Previously called ...]` markers
- normalizes whitespace
- returns an empty string when nothing user-meaningful remains

- [ ] **Step 2: Keep the low-level sanitizer responsibilities separate**

Do not overload existing helpers with unrelated UI rules. The new shared helper may call the lower-level cleanup routines, but the low-level routines should remain readable and independently testable.

- [ ] **Step 3: Switch session-history recovery to the shared helper**

Update `frontend/src/utils/sessionHistory.ts` so synthetic assistant recovery uses the new visible-text sanitizer instead of only `stripLeakedToolCallMarkup()`.

- [ ] **Step 4: Touch `SharePage.vue` only if required**

If the updated tests show `SharePage.vue` already inherits the sanitized output through `resolveSessionHistory()` and `ChatMessage`, leave the page untouched. If not, apply the smallest page-level change required and document why.

- [ ] **Step 5: Re-run the focused tests**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run src/utils/__tests__/messageSanitizer.spec.ts src/utils/__tests__/sessionHistory.spec.ts tests/pages/SharePage.recovery.spec.ts
```

Expected:
- all tests in this batch pass

- [ ] **Step 6: Commit the sanitization foundation**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/src/utils/messageSanitizer.ts frontend/src/utils/sessionHistory.ts frontend/src/utils/__tests__/messageSanitizer.spec.ts frontend/src/utils/__tests__/sessionHistory.spec.ts frontend/tests/pages/SharePage.recovery.spec.ts frontend/src/pages/SharePage.vue
git commit -m "feat(frontend): sanitize visible execution text across replay and share flows"
```

## Chunk 2: Child activity labels and grouped parent hierarchy

### Task 3: Write failing tests for nested child activity rendering

**Files:**
- Create: `frontend/src/utils/__tests__/executionActivity.spec.ts`
- Modify: `frontend/tests/components/ToolUse.spec.ts`
- Modify: `frontend/tests/components/ChatMessage.spec.ts`

- [ ] **Step 1: Add TDD coverage for child-activity label derivation**

Create `frontend/src/utils/__tests__/executionActivity.spec.ts` with failing tests for:
- enforcing the exact label source order: `display_command` -> normalized tool label -> safe arg summary -> drop
- deriving a clean child label from `display_command`
- dropping a label when sanitized text becomes empty
- summarizing grouped child activity for collapsed parent previews

- [ ] **Step 2: Add a ToolUse regression for bare internal inline text**

Extend `frontend/tests/components/ToolUse.spec.ts` with a failing test proving inline message tools do not render `[Previously called info_search_web]` as visible text.

- [ ] **Step 3: Add a ChatMessage regression for the inset child-activity container**

Extend `frontend/tests/components/ChatMessage.spec.ts` with a failing test that mounts a step containing child tool activity and expects:
- one parent step header
- one nested child activity container
- no peer-level duplicate step chrome for child rows

- [ ] **Step 4: Add a grouped-skill regression tied to the new container**

Extend `frontend/tests/components/ChatMessage.spec.ts` so repeated skill loads are expected inside the same grouped child container rather than as detached rows.

- [ ] **Step 5: Run the red test batch**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run src/utils/__tests__/executionActivity.spec.ts tests/components/ToolUse.spec.ts tests/components/ChatMessage.spec.ts
```

Expected:
- failures point to missing child-label sanitization and missing grouped inset container behavior

- [ ] **Step 6: Commit the failing-test checkpoint**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/src/utils/__tests__/executionActivity.spec.ts frontend/tests/components/ToolUse.spec.ts frontend/tests/components/ChatMessage.spec.ts
git commit -m "test(frontend): capture grouped activity hierarchy regressions"
```

### Task 4: Implement one shared child-activity model and the inset rail container

**Files:**
- Create: `frontend/src/utils/executionActivity.ts`
- Modify: `frontend/src/components/ToolUse.vue`
- Modify: `frontend/src/components/ChatMessage.vue`
- Modify: `frontend/src/pages/ChatPage.vue`

- [ ] **Step 1: Add a shared execution-activity utility**

Create `frontend/src/utils/executionActivity.ts` with focused helpers such as:
- deriving a clean visible child label using the exact priority order `display_command` -> normalized tool label from existing `toolDisplay` helpers -> safe arg summary -> drop
- deciding when a child activity row should be dropped after sanitization
- generating compact collapsed-preview summaries from grouped child activity

Reuse the existing normalization path in `frontend/src/utils/toolDisplay.ts` where possible. Keep `executionActivity.ts` focused on chat-timeline-specific label selection and preview summaries rather than duplicating generic display normalization.

- [ ] **Step 2: Make ToolUse sanitize-or-drop inline child rows**

Update `frontend/src/components/ToolUse.vue` so inline message tools:
- sanitize `tool.args.text`
- render nothing when the sanitized text is empty
- run both inline text and visible chip labels through the same sanitize-or-drop path
- prefer the shared child-label helper over raw text when possible so leaked markers cannot survive in `display_command`-driven labels

- [ ] **Step 3: Convert ChatMessage step children into one inset rail container**

Update `frontend/src/components/ChatMessage.vue` so:
- each parent step owns one nested child-activity container
- the container is visually inset from the parent header
- the container uses one subtle left rail
- grouped skill continuations live inside that container
- child rows no longer look like peer timeline steps

- [ ] **Step 4: Preserve the current live transcript wiring**

Keep `frontend/src/pages/ChatPage.vue` responsible for live message grouping. Only change it where needed to feed the new preview/child helpers without regressing the current placeholder-assistant and repeated-skill-header behavior already on this branch.

- [ ] **Step 5: Re-run the hierarchy batch**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run src/utils/__tests__/executionActivity.spec.ts tests/components/ToolUse.spec.ts tests/components/ChatMessage.spec.ts
```

Expected:
- all tests in this batch pass

- [ ] **Step 6: Commit the hierarchy implementation**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/src/utils/executionActivity.ts frontend/src/components/ToolUse.vue frontend/src/components/ChatMessage.vue frontend/src/pages/ChatPage.vue frontend/src/utils/__tests__/executionActivity.spec.ts frontend/tests/components/ToolUse.spec.ts frontend/tests/components/ChatMessage.spec.ts
git commit -m "feat(frontend): group child execution activity under parent steps"
```

## Chunk 3: Parent state handling and collapsed previews

### Task 5: Capture the remaining parent-step state and preview gaps

**Files:**
- Modify: `frontend/tests/components/ChatMessage.spec.ts`
- Modify: `frontend/src/utils/__tests__/executionActivity.spec.ts`

- [ ] **Step 1: Add a `started` state regression**

Extend `frontend/tests/components/ChatMessage.spec.ts` with a test proving `started` steps use the same active visual treatment and default expansion behavior as `running`.

- [ ] **Step 2: Add a `skipped` state regression**

Extend `frontend/tests/components/ChatMessage.spec.ts` with a test proving `skipped` steps stay de-emphasized like completed steps without reusing failed styling.

- [ ] **Step 3: Add a collapsed-preview regression**

Extend `frontend/src/utils/__tests__/executionActivity.spec.ts` with a direct regression for collapsed preview generation using a concrete fixture, for example two sanitized skill loads plus one search, and expect a specific summary shape such as `2 skills loaded, 1 search run`. Add a second case proving that sanitized-empty child items are omitted from the preview entirely.

- [ ] **Step 4: Add a parent-level collapsed preview regression**

Extend `frontend/tests/components/ChatMessage.spec.ts` with a test proving a collapsed parent step renders the concrete preview text returned by the shared preview helper instead of echoing raw child text or leaked metadata.

- [ ] **Step 5: Add failed and blocked parent regressions**

Extend `frontend/tests/components/ChatMessage.spec.ts` with tests proving `failed` and `blocked` parents preserve visible child context inside the inset activity container instead of collapsing that context away.

- [ ] **Step 6: Run the focused ChatMessage batch and confirm it fails on the intended assertions**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run tests/components/ChatMessage.spec.ts src/utils/__tests__/executionActivity.spec.ts
```

Expected:
- failures identify missing state/preview behavior, not unrelated mount errors

- [ ] **Step 7: Commit the failing-test checkpoint**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/tests/components/ChatMessage.spec.ts frontend/src/utils/__tests__/executionActivity.spec.ts
git commit -m "test(frontend): capture parent step preview and state regressions"
```

### Task 6: Implement state-specific parent behavior and summary previews

**Files:**
- Modify: `frontend/src/components/ChatMessage.vue`
- Modify: `frontend/src/utils/executionActivity.ts`

- [ ] **Step 1: Add explicit parent-state handling**

Update `frontend/src/components/ChatMessage.vue` so `pending`, `started`, `running`, `completed`, `failed`, `blocked`, and `skipped` all map to the approved hierarchy behavior. Treat `started` as active like `running`.

- [ ] **Step 2: Add collapsed parent previews**

Use the shared `executionActivity` helper to generate short preview text for collapsed parent steps based on child activity counts and types instead of exposing raw child text. Preserve the concrete preview contract from the tests rather than inventing per-component summaries.

- [ ] **Step 3: Ensure failed/blocked parents preserve child context**

Keep failed and blocked parents readable for diagnosis while still using the same child inset container and sanitized child labels.

- [ ] **Step 4: Re-run the focused ChatMessage batch**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run tests/components/ChatMessage.spec.ts src/utils/__tests__/executionActivity.spec.ts
```

Expected:
- all tests in this batch pass

- [ ] **Step 5: Commit the preview/state implementation**

```bash
cd /Users/panda/Projects/active/Pythinker
git add frontend/src/components/ChatMessage.vue frontend/src/utils/executionActivity.ts frontend/tests/components/ChatMessage.spec.ts frontend/src/utils/__tests__/executionActivity.spec.ts
git commit -m "feat(frontend): add parent state hierarchy and collapsed activity previews"
```

## Chunk 4: Final verification and manual QA

### Task 7: Run the targeted frontend verification suite

- [ ] **Step 1: Run the targeted Vitest batch**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run vitest run src/utils/__tests__/messageSanitizer.spec.ts src/utils/__tests__/sessionHistory.spec.ts src/utils/__tests__/executionActivity.spec.ts tests/components/ToolUse.spec.ts tests/components/ChatMessage.spec.ts tests/pages/SharePage.recovery.spec.ts
```

Expected:
- all listed tests pass

- [ ] **Step 2: Run lint check**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run lint:check
```

Expected:
- no new errors
- existing unrelated warnings may remain only if they already existed before this plan

- [ ] **Step 3: Run type-check**

Run:

```bash
cd /Users/panda/Projects/active/Pythinker/frontend && bun run type-check
```

Expected:
- pass with no new type errors

### Task 8: Do a manual transcript smoke pass

- [ ] **Step 1: Verify live skill grouping**

Start a live task that loads multiple skills in sequence. Confirm:
- one visible work-group header
- nested skill rows inside one inset rail container
- no detached standalone skill pills

- [ ] **Step 2: Verify the `[Previously called ...]` regression is gone**

Open a session or shared transcript that previously showed `[Previously called info_search_web]`. Confirm the visible chat transcript no longer shows that marker anywhere.

- [ ] **Step 3: Verify fallback thinking behavior**

Trigger a state with no visible running step but active thinking. Confirm the floating thinking indicator appears without a duplicate `Pythinker` brand row.

- [ ] **Step 4: Verify collapsed previews**

Collapse a completed parent step with child activity. Confirm the step shows a compact summary rather than raw child strings.

## Success Criteria

- Parent steps are visually dominant over execution child activity.
- Child activity lives inside one inset grouped container with a subtle left rail.
- Repeated skill loads stay under one visible work-group header.
- Bare internal markers such as `[Previously called info_search_web]` never appear in live, replay, or shared transcripts.
- Collapsed parent steps summarize child activity cleanly.
- Targeted frontend tests, lint, and type-check all pass without introducing new failures.
