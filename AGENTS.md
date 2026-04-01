# AGENTS.md

Working rules for automated agents in this repo.

## Read First

- Read `instructions.md` before making changes.
- Verify behavior against the codebase when docs and code disagree.
- Treat this file as current-repo guidance, not aspirational architecture.

## Instruction Ownership

- `AGENTS.md` is repo law: stable constraints, architecture boundaries, current validation commands, and environment notes.
- `instructions.md` defines engineering behavior and communication rules.
- `skills/` contains workflow guidance for recurring task types.
- `.codex/` is the Codex-local adapter layer for hooks, session artifacts, and harness glue.
- `.opencode/` and `.cursor/` are downstream adapters and should follow the same repo-law and workflow model.

## Enforced Today

- Reuse existing components, utilities, and services before creating new ones.
- Prefer simple, robust solutions over clever abstractions.
- Apply `DRY` and `KISS` by default when debugging or implementing code.
- When balancing reuse and simplicity, prefer a small local duplicate over a premature abstraction.
- Extract shared code only when the repeated logic is stable, clearly identical, and easier to maintain once centralized.
- If a helper makes the control flow harder to follow, keep the code inline and local.
- Avoid "helper" layers that only rename existing code without reducing complexity.
- Before adding new debugging code, reuse existing logs, metrics, traces, and verification hooks when they can answer the question.
- Keep new debugging instrumentation narrowly scoped, factual, and removable. Remove temporary debug code before closing the task unless the user asks to keep it.
- Consider frontend and backend impact together for cross-cutting changes.
- Keep dependency direction moving inward: `interfaces` and `infrastructure` may depend on `application` and `domain`; `application` may depend on `domain`; `domain` should not depend on outer layers. The repo has existing violations, but do not add new ones.
- Keep business logic out of routes and components when practical. The repo has large orchestration files already; prefer incremental extraction over broad refactors.
- Use full Python type hints and TypeScript types where practical. Do not introduce new `any` casually.
- Pydantic v2 `@field_validator` methods must also be `@classmethod`. This is guarded by `backend/tests/test_pydantic_validators.py`.
- Status reports must be strictly factual. Distinguish `Completed`, `In Progress`, and `Not Started`.
- When writing code or docs, do not use placeholders or summary-only substitutions.

## Canonical Clean Code Standard

Always follow these 20 rules when writing, reviewing, or refactoring code and instructions in this repo.

1. **Simplicity first**: choose the simplest solution that fully solves the problem. Remove unnecessary abstraction, indirection, and branching.
2. **Reuse before create**: extend existing components, services, utilities, and patterns before adding new ones. Do not duplicate logic, constants, or workflows.
3. **One clear responsibility per unit**: keep functions, classes, modules, and components focused. Split code when a unit is carrying unrelated behavior.
4. **Protect layer boundaries**: keep dependency flow moving inward and keep business logic out of routes, handlers, and UI components when practical.
5. **Optimize for readability**: code should be easy for the next engineer to understand without mental backtracking. Prefer obvious control flow over clever shortcuts.
6. **Use precise names**: choose explicit names for variables, types, functions, classes, and files. Avoid vague names such as `data`, `temp`, `misc`, or `helper` unless the scope is truly generic.
7. **Keep changes small and local**: prefer narrowly scoped, reviewable edits. Do not mix unrelated cleanup into task-driven changes.
8. **Prefer shallow control flow**: use guard clauses, early returns, and focused helpers to avoid deep nesting and parallel branches.
9. **Keep public interfaces small and explicit**: expose only what callers need and make internal helpers clearly internal.
10. **Use types as part of the design**: write full Python type hints and strict TypeScript types where practical. Treat `Any` and `any` as escape hatches, not defaults.
11. **Validate input at boundaries**: validate, normalize, and constrain external input at the edge of the system before it reaches business logic.
12. **Keep secrets and config out of code**: never hardcode secrets or environment-specific configuration. Use environment-based configuration and approved secret handling.
13. **Log useful facts, not noise**: prefer existing structured logs, metrics, and traces. Never log secrets or sensitive payloads. Keep logs factual and actionable.
14. **Handle errors deliberately**: fail loudly enough to diagnose the problem, return actionable errors, and do not silently swallow exceptions.
15. **Prove behavior with targeted verification**: add or update the smallest tests and checks that prove the changed behavior. Do not rely on manual confidence alone.
16. **Comment the why, not the obvious**: keep comments and docstrings concise and useful. Explain intent, invariants, edge cases, or non-obvious tradeoffs.
17. **Follow official language and framework conventions**: respect formatter, linter, and framework guidance instead of inventing local style rules per file.
18. **Prefer repo-standard primitives**: use existing project conventions such as `HTTPClientPool`, `APIKeyPool`, Pydantic v2 validators, Vue Composition API, and other established repo patterns before introducing alternatives.
19. **Remove temporary scaffolding before closing the task**: delete temporary debug code, duplicate paths, dead branches, and disposable instrumentation unless the user explicitly asks to keep them.
20. **Keep docs and agent guidance in sync with reality**: when rules, workflows, or validation commands change, update the relevant instruction surfaces so downstream agents do not drift.

These rules are synthesized for this repo from current primary guidance, including:

- Python `PEP 20`: https://peps.python.org/pep-0020/
- Python `PEP 8`: https://peps.python.org/pep-0008/
- Google Engineering Practices: https://google.github.io/eng-practices/review/
- TypeScript `strict`: https://www.typescriptlang.org/tsconfig/strict.html
- TypeScript `noImplicitAny`: https://www.typescriptlang.org/tsconfig/noImplicitAny.html
- Vue Style Guide: https://vuejs.org/style-guide/
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Twelve-Factor App Config: https://12factor.net/config
- Twelve-Factor App Logs: https://12factor.net/logs

## Preferred Direction

- Prefer SOLID-style boundaries and dependency inversion when it improves clarity.
- Prefer domain/application services for reusable business rules.
- Prefer Vue Composition API with `<script setup>` in app code.
- Prefer smaller files and focused units, but follow existing patterns unless the task justifies a split.
- Prefer self-hosted, open-source, zero-cost integrations when they satisfy the requirement.
- Prefer research-backed implementation for library, API, architecture, and debugging work.

## Current Tooling Reality

- Frontend TypeScript runs with `strict: true`, but explicit `any` is still allowed by ESLint today. Treat `any` as an escape hatch, not as a normal pattern.
- Backend type checking is partial. Pyright configuration exists, but it is not part of the required pre-commit checks and is not uniformly strict across configs.
- Current required validation commands are:
  - Frontend: `cd frontend && bun run lint:check && bun run type-check`
  - Backend: `cd backend && ruff check . && ruff format --check . && pytest -p no:cov -o addopts= tests/path/to/affected_test.py [tests/more_targeted_files.py ...]`
- Backend validation must stay targeted to the files and behaviors affected by the change. Do not run `pytest tests/` or other full backend suites unless the user explicitly requests it.
- For a single backend test without coverage: `cd backend && pytest -p no:cov -o addopts= tests/test_file.py`

## Environment Notes

- Prefer `conda activate pythinker` when that environment exists.
- In shells without Conda, use the repo-local backend virtualenv if present: `backend/.venv`.
- For Docker operations and container logs, use Docker CLI by default. Use Docker MCP only when CLI is unavailable or MCP-specific behavior is required.
- For library and API documentation, use Context7 first. If Context7 is thin or stale for the question, verify with official primary sources.
- This repo is development-only. Optimize for correctness and iteration speed, not production hardening for external users.

## Platform-Specific Capabilities

- Agent lists, MCP servers, and skill inventories vary by harness. Verify what is actually available in the current runtime before relying on it.
- Do not assume repo-local paths such as `.opencode/skills/` exist without checking. They are not present in this repo today.
