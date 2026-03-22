---
name: pythinker-codebase-onboarding
description: Analyze the Pythinker repo at session start and produce a short working map of architecture, entry points, validation commands, and harness surfaces before implementation begins.
---

# Pythinker Codebase Onboarding

Use this skill when starting a fresh Codex session in Pythinker or whenever repo understanding is weak.

## Goals

- Build a short working map of the repo before editing
- Identify the relevant backend, frontend, or harness surfaces
- Confirm the current validation commands and environment assumptions

## Read First

1. `AGENTS.md`
2. `instructions.md`
3. `README.md`
4. `backend/pyproject.toml`
5. `opencode.json`
6. `.opencode/agents/build.md`
7. `.cursor/rules/core.mdc`

## Reconnaissance Workflow

1. Identify whether the task is primarily:
   - backend
   - frontend
   - cross-cutting
   - internal harness
2. Map the likely entry points:
   - backend: `backend/app/`
   - frontend: `frontend/src/`
   - Codex harness: `.codex/`, `skills/`, `AGENTS.md`, `instructions.md`
   - OpenCode adapter: `.opencode/`
   - Cursor adapter: `.cursor/rules/`
3. Confirm validation commands from `AGENTS.md`, not memory.
4. Check for existing design docs or plans under `docs/superpowers/` before proposing new structure.

## What To Produce

Produce a short session-start summary with:

- task area
- key files or directories to inspect next
- required validation commands
- likely architectural constraints
- open questions or risks

## Guardrails

- Do not read the whole repo.
- Do not guess current commands or architecture rules.
- Prefer a 1-2 minute map over a long narrative.
