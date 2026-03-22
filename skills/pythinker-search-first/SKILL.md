---
name: pythinker-search-first
description: Enforce reuse-before-create in Pythinker by searching the repo for existing components, composables, services, utilities, docs, and harness assets before proposing new files or abstractions.
---

# Pythinker Search First

Use this skill before creating a new file, helper, service, hook, composable, or harness utility.

## Required Search Order

1. Search the repo with `rg`
2. Check tests for the same behavior
3. Check docs and plans for prior design decisions
4. Only then propose creating something new

## Search Targets

### Backend

- `backend/app/domain/`
- `backend/app/application/`
- `backend/app/infrastructure/`
- `backend/app/interfaces/`
- `backend/tests/`

### Frontend

- `frontend/src/components/`
- `frontend/src/composables/`
- `frontend/src/api/`
- `frontend/src/pages/`
- `frontend/src/stores/`

### Harness

- `skills/`
- `.codex/`
- `.opencode/`
- `.cursor/rules/`
- `docs/superpowers/`

## Decision Rule

- If an existing module can be extended safely, extend it.
- If multiple near-matches exist, explain why none are suitable before creating a new one.
- If the repo already has a pattern for the same concern, follow it unless there is a concrete problem with that pattern.

## Output Requirement

Before proposing a new file or abstraction, state:

- what you searched
- what matched
- why reuse or extension is or is not sufficient
