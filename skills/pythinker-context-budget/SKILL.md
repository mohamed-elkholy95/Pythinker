---
name: pythinker-context-budget
description: Keep long Pythinker Codex sessions stable by compacting at phase boundaries, persisting key state to repo files, and reloading the right artifacts after compaction.
---

# Pythinker Context Budget

Use this skill during long Codex sessions or whenever the work is crossing from one phase to another.

## Compact At These Boundaries

- after repo exploration, before implementation
- after a design is approved, before execution
- after a major chunk is verified
- after a debugging dead-end is abandoned

## Do Not Compact

- mid-implementation on a tightly coupled change
- while unresolved verification failures are still being investigated
- before writing down the current state in files or a short summary

## Persist Before Compacting

Write down:

- active plan path
- active spec path
- key files being modified
- remaining risks or open questions
- verification commands still needed

Preferred homes:

- `docs/superpowers/specs/`
- `docs/superpowers/plans/`
- `.codex/session/`

## Reload After Compacting

Reload only what is needed:

1. `AGENTS.md`
2. `instructions.md`
3. the active plan/spec
4. the files currently being changed

Do not bulk-read unrelated repo files after compaction.
