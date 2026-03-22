# Codex-First Harness Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Scope:** Internal developer AI harness surfaces for this repo (`AGENTS.md`, `instructions.md`, `skills/`, `.codex/`, `.opencode/`, `.cursor/`)

---

## 1. Problem Statement

Pythinker already has multiple agent-facing instruction surfaces:

- [AGENTS.md](/Users/panda/Desktop/Projects/Pythinker/AGENTS.md)
- [instructions.md](/Users/panda/Desktop/Projects/Pythinker/instructions.md)
- [skills/pythinker-ai-dev/SKILL.md](/Users/panda/Desktop/Projects/Pythinker/skills/pythinker-ai-dev/SKILL.md)
- [opencode.json](/Users/panda/Desktop/Projects/Pythinker/opencode.json)
- [.opencode/agents/build.md](/Users/panda/Desktop/Projects/Pythinker/.opencode/agents/build.md)
- [.cursor/rules/core.mdc](/Users/panda/Desktop/Projects/Pythinker/.cursor/rules/core.mdc)
- [.cursor/rules/python-backend.mdc](/Users/panda/Desktop/Projects/Pythinker/.cursor/rules/python-backend.mdc)
- [.cursor/rules/vue-frontend.mdc](/Users/panda/Desktop/Projects/Pythinker/.cursor/rules/vue-frontend.mdc)

The repo does **not** have an explicit Codex-specific local harness layer. That creates three current problems:

1. **Instruction ownership is blurred.**
   Repo law, workflow behavior, and harness-specific adapters are mixed across files with overlapping content.
2. **Codex has no repo-local operating surface beyond `AGENTS.md`.**
   Cursor and OpenCode have dedicated adapter layers; Codex does not.
3. **The existing local skill surface is too broad.**
   `skills/pythinker-ai-dev/` is valuable, but it is a single large execution skill rather than a small governed workflow stack.

The result is avoidable drift, repeated instructions, weaker session-start repo understanding, and unnecessary context cost during long Codex sessions.

---

## 2. Design Goals

1. Make `Codex` the primary repo-local AI harness surface.
2. Keep one clear instruction ownership model:
   - repo law
   - workflow behavior
   - harness adapters
3. Cherry-pick only the high-value ECC patterns that fit this repo.
4. Reduce duplicated instruction text across Codex, OpenCode, and Cursor surfaces.
5. Add quality gates, compaction discipline, and observation without introducing noisy automation.
6. Keep all new guidance Pythinker-specific and grounded in existing repo structure.

## 3. Non-Goals

- Do not install the full Everything Claude Code plugin or catalog.
- Do not introduce a marketplace-style skills/agents/commands surface into this repo.
- Do not add self-modifying or auto-promoting skill evolution in phase 1.
- Do not replace existing OpenCode or Cursor surfaces with a generator framework in this work.
- Do not change end-user product agent behavior in this design; this is internal developer harness work only.

---

## 4. Key Decision: Cherry-Pick ECC Patterns, Do Not Install ECC

The external repo is most useful here as a **pattern library**, not as an install target.

### Import

- `codebase-onboarding`
- `search-first`
- `strategic-compact`
- `skill-stocktake`
- lightweight verification/eval discipline
- hook profile flags
- reviewable observation/session-summary patterns

### Do Not Import

- full plugin manifests/installers
- large multi-language skill catalogs
- generic agents for unrelated ecosystems
- autonomous learning loops that mutate behavior without review
- heavyweight command/plugin machinery that duplicates existing repo assets

### Rationale

Pythinker already has substantial repo-specific instruction assets and AI-system design work. The missing value is not “more prompts.” The missing value is:

- sharper instruction layering
- smaller workflow skills
- Codex-local harness glue
- repeatable quality gates
- low-noise observation of recurring failures

---

## 5. Instruction Ownership Model

### 5.1 Repo Law: `AGENTS.md`

`AGENTS.md` remains the highest-signal repo contract for automated agents.

It should contain only:

- stable architectural boundaries
- current required validation commands
- repo-specific rules that must not drift
- environment and source-priority notes

It should **not** grow into a workflow encyclopedia.

### 5.2 Engineering Behavior: `instructions.md`

`instructions.md` remains the shared engineering behavior contract:

- assumption surfacing
- confusion management
- scope discipline
- output standards
- change reporting expectations

It is still authoritative, but it should avoid re-stating skill-level workflows that belong elsewhere.

### 5.3 Workflow Behavior: `skills/`

Workflow behavior moves into a small governed repo-local skill set under `skills/`.

These skills are the main source of Codex behavioral improvements.

### 5.4 Harness Glue: `.codex/`

Add a new repo-local `.codex/` surface to make Codex-specific harness behavior explicit.

`.codex/` is responsible for:

- Codex-local README/index
- hook wrappers and hook scripts
- session artifacts and observations
- thin command references

It is **not** the place for shared repo law.

### 5.5 Downstream Adapters: `.opencode/` and `.cursor/`

OpenCode and Cursor remain downstream adapters.

They should mirror Codex-first repo decisions instead of inventing competing rule sets. Existing assets stay in place, but future edits should be driven by the Codex-first contract rather than duplicated from scratch.

---

## 6. Codex-First File Layout

### 6.1 Shared Workflow Skills

```text
skills/
  pythinker-codebase-onboarding/
    SKILL.md
  pythinker-search-first/
    SKILL.md
  pythinker-plan-execute/
    SKILL.md
  pythinker-review/
    SKILL.md
  pythinker-verification/
    SKILL.md
  pythinker-context-budget/
    SKILL.md
```

The existing `skills/pythinker-ai-dev/` remains available during migration, then shrinks or delegates to the smaller workflow skills once the split is complete.

### 6.2 Codex Harness Layer

```text
.codex/
  README.md
  .gitignore
  hooks/
    run-with-flags.js
    session-start.js
    session-end.js
    quality-gate.js
    compact-reminder.js
    mcp-health.js
    doc-write-warning.js
  session/
    .gitkeep
```

### 6.3 Observation and Review Surface

```text
docs/superpowers/
  observations/
    README.md
```

Raw observation artifacts stay ephemeral under `.codex/session/`; reviewed patterns are summarized in `docs/superpowers/observations/`.

---

## 7. Minimal Skill Stack

### 7.1 `pythinker-codebase-onboarding`

Purpose:

- first-session repo reconnaissance
- architecture map
- key entrypoints
- validation commands
- where to look first

Inputs:

- `AGENTS.md`
- `instructions.md`
- `README.md`
- `backend/pyproject.toml`
- `opencode.json`
- `.opencode/`
- `.cursor/rules/`

### 7.2 `pythinker-search-first`

Purpose:

- enforce reuse-before-create
- force repo search before proposing new files/services/components
- align with current repo rule to reuse existing modules and utilities

### 7.3 `pythinker-plan-execute`

Purpose:

- Pythinker-specific planning discipline
- file/layer mapping before implementation
- explicit status reporting
- DDD-aware decomposition

### 7.4 `pythinker-review`

Purpose:

- bug/regression/security-first review
- repo-aware review checklist for backend/frontend/sandbox changes

### 7.5 `pythinker-verification`

Purpose:

- required command selection
- single-test no-coverage recipes
- evidence-before-completion behavior

### 7.6 `pythinker-context-budget`

Purpose:

- compact at phase boundaries, not arbitrarily
- preserve critical state in files, not conversation only
- reload the right repo artifacts after compaction

### 7.7 Skill Design Constraints

Every repo-local skill must be:

- short and Pythinker-specific
- auditable for overlap
- explicit about trigger/use cases
- grounded in actual repo paths and commands
- free of broad generic tutorials

---

## 8. Hooks and Commands

### 8.1 Hook Profile Model

Adopt a small profile-based control surface:

- `PYTHINKER_HOOK_PROFILE=minimal|standard|strict`
- `PYTHINKER_DISABLED_HOOKS=hook1,hook2`

This reproduces the useful ECC runtime control pattern without adopting its entire plugin system.

### 8.2 Phase-1 Hooks

- `session-start`
- `session-end`
- `quality-gate`
- `compact-reminder`
- `mcp-health`
- `doc-write-warning`

### 8.3 Phase-1 Commands

- `/plan`
- `/review`
- `/verify`
- `/harness-audit`
- `/skill-stocktake`
- `/session-summary`

These commands are thin wrappers over repo behavior and documentation. They should not become a second orchestration framework.

---

## 9. Observation System

Observation is useful only if it stays disciplined.

### 9.1 Phase-1 Observation Rules

- store raw session observations locally and append-only
- keep them repo-scoped
- do not auto-promote observations into skills
- require explicit human review before any guidance is updated

### 9.2 What to Capture

- repeated user corrections
- repeated validation misses
- repeated path confusion
- repeated architecture-boundary violations
- repeated tool misuse

### 9.3 Storage Model

- raw ephemeral artifacts: `.codex/session/`
- reviewed summaries: `docs/superpowers/observations/`

This gives the harness a memory improvement path without uncontrolled prompt drift.

---

## 10. Rollout Plan

### Phase 1: Codex Baseline

- add `.codex/`
- reduce `AGENTS.md` to repo law only
- split `skills/pythinker-ai-dev/` into the minimal skill stack
- add hook profile wrapper and low-noise hooks

### Phase 2: Governance

- add `harness-audit`
- add `skill-stocktake`
- start reviewed observation summaries
- align `.opencode/` and `.cursor/` to the Codex-first contract

### Phase 3: Optional Convergence

- reduce residual duplication across harness adapters
- decide whether to generate downstream adapter content from shared references
- only pursue this after Codex behavior is stable

---

## 11. Success Criteria

This work is successful when:

1. Codex has an explicit repo-local harness layer.
2. Repo instruction ownership is clear and non-overlapping.
3. Session-start repo understanding improves through onboarding guidance.
4. Planning/review/verification behavior is sharper and more consistent.
5. Long-session drift is reduced through compaction discipline and reviewed observations.
6. OpenCode and Cursor are aligned downstream, not competing sources of truth.

---

## 12. Risks and Mitigations

### Risk: More files create more maintenance burden

Mitigation:

- keep the skill stack small
- add a stocktake/audit process early
- keep `AGENTS.md` and `instructions.md` short

### Risk: Codex-specific assets drift from OpenCode/Cursor

Mitigation:

- make Codex the explicit source of truth
- add a harness audit command in phase 2

### Risk: Observation becomes noisy or untrusted

Mitigation:

- raw logs stay local and append-only
- reviewed summaries only
- no self-modifying prompt behavior in phase 1

---

## 13. Decision Summary

The recommended best-practice path for Pythinker is:

- **Codex-first**
- **cherry-picked ECC patterns**
- **small governed workflow skills**
- **explicit `.codex/` harness layer**
- **manual-review-first observation**
- **OpenCode/Cursor as downstream adapters**

This gives the repo the operational benefits of ECC without the cost, noise, and instruction bloat of a full install.
