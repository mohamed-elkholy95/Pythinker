# Codex-First Harness Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish Codex as the primary repo-local AI harness surface for Pythinker by adding a `.codex/` layer, splitting the broad local skill into smaller workflow skills, and introducing low-noise governance hooks.

**Architecture:** Keep `AGENTS.md` as repo law, keep `instructions.md` as engineering behavior, move workflow guidance into a small `skills/` stack, and add a new `.codex/` adapter layer for hooks, session artifacts, and Codex-local glue. OpenCode and Cursor remain downstream adapters and are aligned after the Codex baseline exists.

**Tech Stack:** Markdown docs, Node.js hook scripts, repo-local Codex assets, existing Pythinker docs and skill files

---

## Chunk 1: Baseline Contract and Codex Bootstrap

### Task 1: Add the repo-local `.codex/` bootstrap surface

**Files:**
- Create: `.codex/README.md`
- Create: `.codex/.gitignore`
- Create: `.codex/session/.gitkeep`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
test -f .codex/README.md && test -f .codex/.gitignore && test -f .codex/session/.gitkeep
```

Expected: command exits non-zero because the `.codex/` bootstrap files do not exist yet.

- [ ] **Step 2: Create the minimal `.codex/` bootstrap files**

Add:

- `.codex/README.md` describing:
  - purpose of `.codex/`
  - relationship to `AGENTS.md`, `instructions.md`, and `skills/`
  - session artifact conventions
- `.codex/.gitignore` for ephemeral session files
- `.codex/session/.gitkeep`

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
test -f .codex/README.md && test -f .codex/.gitignore && test -f .codex/session/.gitkeep
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add .codex/README.md .codex/.gitignore .codex/session/.gitkeep
git commit -m "feat(codex): add repo-local codex bootstrap surface"
```

### Task 2: Clarify repo instruction ownership in `AGENTS.md`

**Files:**
- Modify: `AGENTS.md`
- Reference: `instructions.md`
- Reference: `.codex/README.md`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
rg -n "Codex|\\.codex|repo law|workflow behavior|downstream adapter" AGENTS.md
```

Expected: missing or incomplete ownership guidance for the Codex-first model.

- [ ] **Step 2: Update `AGENTS.md` with the new ownership model**

Add a short section that explicitly states:

- `AGENTS.md` is repo law
- `instructions.md` is engineering behavior
- `skills/` is workflow guidance
- `.codex/` is the Codex-local adapter layer
- `.opencode/` and `.cursor/` are downstream adapters

Keep the file short; do not add command catalogs or workflow tutorials.

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
rg -n "Codex|\\.codex|repo law|workflow guidance|downstream adapters" AGENTS.md
```

Expected: the new ownership lines are present.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): clarify codex-first instruction ownership"
```

---

## Chunk 2: Minimal Skill Stack

### Task 3: Add the `pythinker-codebase-onboarding` skill

**Files:**
- Create: `skills/pythinker-codebase-onboarding/SKILL.md`
- Reference: `AGENTS.md`
- Reference: `instructions.md`
- Reference: `README.md`
- Reference: `backend/pyproject.toml`
- Reference: `opencode.json`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
test -f skills/pythinker-codebase-onboarding/SKILL.md
```

Expected: exit code non-zero because the skill does not exist yet.

- [ ] **Step 2: Write the onboarding skill**

Include:

- trigger/use cases
- reconnaissance workflow
- required files to read first
- how to map backend/frontend/harness surfaces
- where validation commands live

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
test -f skills/pythinker-codebase-onboarding/SKILL.md
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add skills/pythinker-codebase-onboarding/SKILL.md
git commit -m "feat(skills): add pythinker codebase onboarding skill"
```

### Task 4: Add the `pythinker-search-first` skill

**Files:**
- Create: `skills/pythinker-search-first/SKILL.md`
- Reference: `AGENTS.md`
- Reference: `.cursor/rules/core.mdc`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
test -f skills/pythinker-search-first/SKILL.md
```

Expected: exit code non-zero.

- [ ] **Step 2: Write the search-first skill**

Require:

- `rg` search before creating files/components/services
- reuse of existing backend/frontend abstractions first
- repo-aware search targets for backend, frontend, docs, and harness surfaces

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
test -f skills/pythinker-search-first/SKILL.md
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add skills/pythinker-search-first/SKILL.md
git commit -m "feat(skills): add pythinker search-first skill"
```

### Task 5: Add planning, review, verification, and context-budget skills

**Files:**
- Create: `skills/pythinker-plan-execute/SKILL.md`
- Create: `skills/pythinker-review/SKILL.md`
- Create: `skills/pythinker-verification/SKILL.md`
- Create: `skills/pythinker-context-budget/SKILL.md`
- Reference: `skills/pythinker-ai-dev/SKILL.md`
- Reference: `instructions.md`

- [ ] **Step 1: Write the failing verification checks**

Run:

```bash
for f in \
  skills/pythinker-plan-execute/SKILL.md \
  skills/pythinker-review/SKILL.md \
  skills/pythinker-verification/SKILL.md \
  skills/pythinker-context-budget/SKILL.md; do
  test -f "$f"
done
```

Expected: exit code non-zero because one or more skills do not exist.

- [ ] **Step 2: Write the four workflow skills**

Scope:

- `pythinker-plan-execute`
  - DDD-aware decomposition and file mapping
- `pythinker-review`
  - bug/risk/regression-first review
- `pythinker-verification`
  - required command selection and evidence-before-completion
- `pythinker-context-budget`
  - compact timing, state preservation, post-compact reload guidance

- [ ] **Step 3: Re-run the verification checks**

Run:

```bash
for f in \
  skills/pythinker-plan-execute/SKILL.md \
  skills/pythinker-review/SKILL.md \
  skills/pythinker-verification/SKILL.md \
  skills/pythinker-context-budget/SKILL.md; do
  test -f "$f"
done
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add \
  skills/pythinker-plan-execute/SKILL.md \
  skills/pythinker-review/SKILL.md \
  skills/pythinker-verification/SKILL.md \
  skills/pythinker-context-budget/SKILL.md
git commit -m "feat(skills): add codex-first workflow skill stack"
```

### Task 6: Reduce or delegate the broad `pythinker-ai-dev` skill

**Files:**
- Modify: `skills/pythinker-ai-dev/SKILL.md`
- Reference: `skills/pythinker-codebase-onboarding/SKILL.md`
- Reference: `skills/pythinker-search-first/SKILL.md`
- Reference: `skills/pythinker-plan-execute/SKILL.md`
- Reference: `skills/pythinker-review/SKILL.md`
- Reference: `skills/pythinker-verification/SKILL.md`
- Reference: `skills/pythinker-context-budget/SKILL.md`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
rg -n "pythinker-codebase-onboarding|pythinker-search-first|pythinker-plan-execute|pythinker-review|pythinker-verification|pythinker-context-budget" skills/pythinker-ai-dev/SKILL.md
```

Expected: no delegation references yet.

- [ ] **Step 2: Refactor `pythinker-ai-dev` into an index/delegation skill**

Keep:

- high-level purpose
- architecture guardrails that still belong together

Remove or delegate:

- workflow detail now covered by the new skill stack

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
rg -n "pythinker-codebase-onboarding|pythinker-search-first|pythinker-plan-execute|pythinker-review|pythinker-verification|pythinker-context-budget" skills/pythinker-ai-dev/SKILL.md
```

Expected: delegation references are present.

- [ ] **Step 4: Commit**

```bash
git add skills/pythinker-ai-dev/SKILL.md
git commit -m "refactor(skills): narrow pythinker-ai-dev into a codex-first index skill"
```

---

## Chunk 3: Hooks and Session Artifacts

### Task 7: Add a flag-driven hook runner with tests

**Files:**
- Create: `.codex/hooks/run-with-flags.js`
- Create: `.codex/hooks/tests/run-with-flags.test.mjs`

- [ ] **Step 1: Write the failing test**

Add a Node built-in test that verifies:

- hook runs in `minimal`
- hook is skipped when disabled via `PYTHINKER_DISABLED_HOOKS`
- unknown profile falls back predictably

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
node --test .codex/hooks/tests/run-with-flags.test.mjs
```

Expected: FAIL because the runner does not exist yet.

- [ ] **Step 3: Write the minimal runner implementation**

Implement:

- profile parsing
- disabled-hook filtering
- child-process dispatch to a named hook script

- [ ] **Step 4: Re-run the test to verify GREEN**

Run:

```bash
node --test .codex/hooks/tests/run-with-flags.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .codex/hooks/run-with-flags.js .codex/hooks/tests/run-with-flags.test.mjs
git commit -m "feat(codex): add flag-driven hook runner"
```

### Task 8: Add low-noise phase-1 hook scripts

**Files:**
- Create: `.codex/hooks/session-start.js`
- Create: `.codex/hooks/session-end.js`
- Create: `.codex/hooks/quality-gate.js`
- Create: `.codex/hooks/compact-reminder.js`
- Create: `.codex/hooks/mcp-health.js`
- Create: `.codex/hooks/doc-write-warning.js`
- Create: `.codex/hooks/README.md`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
for f in \
  .codex/hooks/session-start.js \
  .codex/hooks/session-end.js \
  .codex/hooks/quality-gate.js \
  .codex/hooks/compact-reminder.js \
  .codex/hooks/mcp-health.js \
  .codex/hooks/doc-write-warning.js \
  .codex/hooks/README.md; do
  test -f "$f"
done
```

Expected: exit code non-zero because the hook files do not exist yet.

- [ ] **Step 2: Add minimal phase-1 hook implementations**

Implementation rules:

- each hook should do one thing only
- no auto-mutation of skills or docs
- write small structured JSON/text artifacts only when needed
- respect `PYTHINKER_HOOK_PROFILE`

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
for f in \
  .codex/hooks/session-start.js \
  .codex/hooks/session-end.js \
  .codex/hooks/quality-gate.js \
  .codex/hooks/compact-reminder.js \
  .codex/hooks/mcp-health.js \
  .codex/hooks/doc-write-warning.js \
  .codex/hooks/README.md; do
  test -f "$f"
done
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add .codex/hooks
git commit -m "feat(codex): add low-noise codex governance hooks"
```

---

## Chunk 4: Observation and Adapter Alignment

### Task 9: Add the reviewed observation surface

**Files:**
- Create: `docs/superpowers/observations/README.md`
- Reference: `.codex/session/`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
test -f docs/superpowers/observations/README.md
```

Expected: exit code non-zero.

- [ ] **Step 2: Add the observation README**

Document:

- raw vs reviewed artifacts
- what to capture
- what not to auto-promote
- review workflow for turning repeated failures into stable skill updates

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
test -f docs/superpowers/observations/README.md
```

Expected: exit code `0`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/observations/README.md
git commit -m "docs(codex): add reviewed observation workflow"
```

### Task 10: Align OpenCode and Cursor surfaces to the Codex-first contract

**Files:**
- Modify: `opencode.json`
- Modify: `.opencode/agents/build.md`
- Modify: `.opencode/agents/plan.md`
- Modify: `.cursor/rules/core.mdc`
- Modify: `.cursor/rules/python-backend.mdc`
- Modify: `.cursor/rules/vue-frontend.mdc`
- Reference: `AGENTS.md`
- Reference: `.codex/README.md`

- [ ] **Step 1: Write the failing verification check**

Run:

```bash
rg -n "\\.codex|Codex-first|repo law|workflow guidance" \
  opencode.json \
  .opencode/agents/build.md \
  .opencode/agents/plan.md \
  .cursor/rules/core.mdc \
  .cursor/rules/python-backend.mdc \
  .cursor/rules/vue-frontend.mdc
```

Expected: little or no evidence of the new Codex-first ownership model.

- [ ] **Step 2: Update the downstream adapter files**

Goal:

- reference the new Codex-first structure
- avoid introducing new competing rules
- keep adapter files concise and repo-specific

- [ ] **Step 3: Re-run the verification check**

Run:

```bash
rg -n "\\.codex|Codex-first|repo law|workflow guidance" \
  opencode.json \
  .opencode/agents/build.md \
  .opencode/agents/plan.md \
  .cursor/rules/core.mdc \
  .cursor/rules/python-backend.mdc \
  .cursor/rules/vue-frontend.mdc
```

Expected: the new ownership references are present.

- [ ] **Step 4: Commit**

```bash
git add \
  opencode.json \
  .opencode/agents/build.md \
  .opencode/agents/plan.md \
  .cursor/rules/core.mdc \
  .cursor/rules/python-backend.mdc \
  .cursor/rules/vue-frontend.mdc
git commit -m "docs(harness): align opencode and cursor with codex-first contract"
```

---

## Chunk 5: Governance Utilities

### Task 11: Add a harness audit utility

**Files:**
- Create: `scripts/ai/harness-audit.py`
- Create: `tests/scripts/test_harness_audit.py`
- Reference: `AGENTS.md`
- Reference: `instructions.md`
- Reference: `.codex/README.md`
- Reference: `skills/`
- Reference: `.opencode/`
- Reference: `.cursor/rules/`

- [ ] **Step 1: Write the failing test**

Test for:

- missing expected ownership sections
- duplicate phrases across surfaces
- missing Codex adapter references

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
cd backend && pytest -p no:cov -o addopts= ../tests/scripts/test_harness_audit.py
```

Expected: FAIL because the audit utility does not exist yet.

- [ ] **Step 3: Write the minimal audit utility**

Implement checks for:

- required files exist
- required ownership phrases exist
- overlapping rule phrases are flagged for review

- [ ] **Step 4: Re-run the test to verify GREEN**

Run:

```bash
cd backend && pytest -p no:cov -o addopts= ../tests/scripts/test_harness_audit.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/harness-audit.py tests/scripts/test_harness_audit.py
git commit -m "feat(harness): add codex-first harness audit utility"
```

### Task 12: Add a skill stocktake utility

**Files:**
- Create: `scripts/ai/skill-stocktake.py`
- Create: `tests/scripts/test_skill_stocktake.py`
- Reference: `skills/`
- Reference: `docs/superpowers/observations/README.md`

- [ ] **Step 1: Write the failing test**

Test for:

- skill discovery under `skills/`
- detection of missing frontmatter fields
- detection of likely overlap by name/description/keyword repetition

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
cd backend && pytest -p no:cov -o addopts= ../tests/scripts/test_skill_stocktake.py
```

Expected: FAIL because the stocktake utility does not exist yet.

- [ ] **Step 3: Write the minimal stocktake utility**

Implement:

- skill inventory
- missing metadata detection
- overlap/staleness warnings

- [ ] **Step 4: Re-run the test to verify GREEN**

Run:

```bash
cd backend && pytest -p no:cov -o addopts= ../tests/scripts/test_skill_stocktake.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/ai/skill-stocktake.py tests/scripts/test_skill_stocktake.py
git commit -m "feat(harness): add skill stocktake utility"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-22-codex-first-harness.md`. Ready to execute?
