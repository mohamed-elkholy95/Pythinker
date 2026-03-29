# Long-term Memory

## User Information

- The user wants coding and debugging work to default to best-practice engineering discipline.

## Preferences

- When debugging or implementing code, prefer `DRY` and `KISS`.
- Reuse existing helpers, abstractions, logs, metrics, traces, and verification before adding new code or instrumentation.
- Keep debugging code minimal, scoped to the issue, and removable. Do not leave temporary debugging artifacts behind unless explicitly requested.

## Project Context

- This workspace should enforce the same DRY/KISS rule in repo instructions and agent prompts.

## Important Notes

- When a simple direct change is sufficient, prefer it over new abstractions or duplicated paths.
