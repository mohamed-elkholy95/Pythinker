# Codex Hooks

These scripts are the low-noise phase-1 governance hooks for Pythinker.

## Runtime Flags

- `PYTHINKER_HOOK_PROFILE=minimal|standard|strict`
- `PYTHINKER_DISABLED_HOOKS=hook1,hook2`

Use `run-with-flags.js` to gate hooks by profile rather than wiring profile logic into each script.

## Hooks

- `session-start.js`: writes a small session snapshot to `.codex/session/`
- `session-end.js`: writes a small end-of-session summary to `.codex/session/`
- `quality-gate.js`: prints the likely verification commands for the current change set
- `compact-reminder.js`: suggests compaction after enough hook invocations
- `mcp-health.js`: reports whether repo MCP config files are present
- `doc-write-warning.js`: warns when writing docs outside expected repo locations

## Design Rules

- Hooks should be low-noise.
- Hooks should never rewrite repo guidance automatically.
- Raw session artifacts stay under `.codex/session/`.
- Reviewed patterns belong in `docs/superpowers/observations/`.
