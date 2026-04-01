# Codex Repo Layer

This directory contains the repo-local Codex harness surface for Pythinker.

## Ownership

- `AGENTS.md`: repo law and current repo constraints
- `instructions.md`: engineering behavior and communication rules
- `skills/`: workflow guidance for recurring task types
- `.codex/`: Codex-local hooks, session artifacts, and harness glue
- `.opencode/` and `.cursor/`: downstream adapters that should follow the Codex-first contract

## Scope

Use `.codex/` for:

- hook entrypoints and wrappers
- Codex session artifacts
- local harness README and utilities
- Codex-specific harness guidance that mirrors repo-law

## Working Standard

- Default to `DRY` and `KISS` when adding or changing harness logic.
- Prefer small local duplication over premature abstraction when that keeps the code easier to read.
- Extract shared code only when the repeated logic is stable, clearly identical, and simpler once centralized.
- If a helper makes control flow harder to follow, keep the code inline and local.
- Avoid thin "helper" layers that only rename existing code without reducing complexity.

Do not move repo law or shared engineering rules into this directory.

## Session Artifacts

- `.codex/session/` is for ephemeral local artifacts generated during Codex sessions
- reviewed patterns belong in `docs/superpowers/observations/`, not in ephemeral session files

## Phase-1 Hooks

Planned phase-1 governance hooks:

- `session-start`
- `session-end`
- `quality-gate`
- `compact-reminder`
- `mcp-health`
- `doc-write-warning`

These hooks should stay low-noise and review-friendly.
