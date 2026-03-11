# Live View Replay Design Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the existing live-view and replay UI so the Pythinker's Computer panel, browser chrome, and timeline controls feel like a cohesive, higher-fidelity design system without changing backend behavior.

**Architecture:** Frontend-only, component-scoped refresh. Keep the current live/replay logic, enrich the visual shell around it, and preserve existing props/data flow. Use TDD by defining the new structure and states in component tests before patching styles and markup.

**Tech Stack:** Vue 3, TypeScript, Vitest, scoped CSS, existing semantic design tokens

---

### Task 1: Lock the redesigned shell structure in tests

**Files:**
- Modify: `frontend/tests/components/ToolPanelContent.spec.ts`
- Modify: `frontend/tests/components/LiveViewer.spec.ts`

**Step 1: Write the failing test**

Add assertions that the live-view shell exposes:
- a hero-style frame surface class for the outer live panel
- a refined activity/status rail with explicit live-view metadata hooks
- a content frame class for the replay/live viewport wrapper

Add assertions that `LiveViewer` exposes a stable root class for live, editor, terminal, and browser states.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts frontend/tests/components/LiveViewer.spec.ts`

Expected: FAIL because the new shell classes/data attributes do not exist yet.

**Step 3: Write minimal implementation**

Update the component templates to add the structural hooks needed by the redesigned shell without changing behavior.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts frontend/tests/components/LiveViewer.spec.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/components/ToolPanelContent.spec.ts frontend/tests/components/LiveViewer.spec.ts frontend/src/components/ToolPanelContent.vue frontend/src/components/LiveViewer.vue
git commit -m "feat: establish live view design shell hooks"
```

### Task 2: Redesign the Pythinker’s Computer shell and browser chrome

**Files:**
- Modify: `frontend/src/components/ToolPanelContent.vue`
- Modify: `frontend/src/components/workspace/BrowserChrome.vue`

**Step 1: Write the failing test**

Extend `frontend/tests/components/ToolPanelContent.spec.ts` to assert:
- the panel header renders the new live badge/chips for live vs replay state
- the browser chrome receives a more explicit framed container hook
- the takeover affordance remains rendered and interactive

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts`

Expected: FAIL because the new visual hooks and labels are missing.

**Step 3: Write minimal implementation**

Refresh the panel header, status bar, and content shell using semantic token-based gradients, inset strokes, stronger depth, and more intentional spacing. Refresh browser chrome into a “control deck” style without changing any emitted events.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/components/ToolPanelContent.spec.ts frontend/src/components/ToolPanelContent.vue frontend/src/components/workspace/BrowserChrome.vue
git commit -m "feat: redesign live view shell and browser chrome"
```

### Task 3: Redesign the replay timeline controls

**Files:**
- Modify: `frontend/src/components/timeline/TimelineControls.vue`
- Test: `frontend/tests/components/ToolPanelContent.spec.ts`

**Step 1: Write the failing test**

Add assertions for:
- replay/live mode badge rendering
- grouped transport controls shell
- upgraded scrubber frame class and hover metadata surface

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts`

Expected: FAIL because the timeline markup does not yet expose the redesigned structure.

**Step 3: Write minimal implementation**

Upgrade the timeline controls into a stronger control bar with a framed scrubber, grouped transport buttons, a clearer mode indicator, and improved hover tooltip styling.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/components/ToolPanelContent.spec.ts frontend/src/components/timeline/TimelineControls.vue
git commit -m "feat: redesign replay timeline controls"
```

### Task 4: Refine terminal/editor live surfaces

**Files:**
- Modify: `frontend/src/components/toolViews/TerminalContentView.vue`
- Modify: `frontend/src/components/toolViews/EditorContentView.vue`

**Step 1: Write the failing test**

Add or extend component tests to assert stable shell classes for terminal/editor surfaces and their live state decorations.

**Step 2: Run test to verify it fails**

Run: `cd frontend && bun run vitest frontend/tests/components/LiveViewer.spec.ts`

Expected: FAIL because the richer surface hooks do not exist yet.

**Step 3: Write minimal implementation**

Introduce a more deliberate surface treatment for terminal/editor views so they visually belong to the same system as the browser/replay shell while keeping content rendering untouched.

**Step 4: Run test to verify it passes**

Run: `cd frontend && bun run vitest frontend/tests/components/LiveViewer.spec.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/tests/components/LiveViewer.spec.ts frontend/src/components/toolViews/TerminalContentView.vue frontend/src/components/toolViews/EditorContentView.vue
git commit -m "feat: align terminal and editor live surfaces"
```

### Task 5: Verify the redesigned surface

**Files:**
- Verify: `frontend/src/components/ToolPanelContent.vue`
- Verify: `frontend/src/components/workspace/BrowserChrome.vue`
- Verify: `frontend/src/components/timeline/TimelineControls.vue`
- Verify: `frontend/src/components/toolViews/TerminalContentView.vue`
- Verify: `frontend/src/components/toolViews/EditorContentView.vue`
- Verify: `frontend/tests/components/ToolPanelContent.spec.ts`
- Verify: `frontend/tests/components/LiveViewer.spec.ts`

**Step 1: Run focused tests**

Run:

```bash
cd frontend && bun run vitest frontend/tests/components/ToolPanelContent.spec.ts frontend/tests/components/LiveViewer.spec.ts
```

Expected: PASS

**Step 2: Run frontend verification**

Run:

```bash
cd frontend && bun run lint && bun run type-check
```

Expected: PASS

**Step 3: Manual review**

Check the live-view panel in both active and replay states:
- browser tool active
- shell tool active
- file tool active
- replay/timeline stepping

Confirm the redesign is visually coherent on desktop and narrow widths.
