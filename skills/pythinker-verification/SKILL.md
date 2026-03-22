---
name: pythinker-verification
description: Verify Pythinker work with repo-specific commands and evidence-before-claims discipline before stating that anything is complete, fixed, or passing.
---

# Pythinker Verification

Use this skill before claiming a task is complete, fixed, or ready for handoff.

## Required Principle

No completion claims without fresh command output that directly supports the claim.

## Verification Matrix

### Frontend changes

Run:

```bash
cd frontend && bun run lint:check && bun run type-check
```

### Backend changes

Run:

```bash
cd backend && ruff check . && ruff format --check . && pytest tests/
```

### Targeted backend verification

Run:

```bash
cd backend && pytest -p no:cov -o addopts= tests/test_file.py
```

### Harness/docs-only changes

Run the smallest direct proof:

- file existence checks
- targeted script tests
- grep-based ownership checks

## Reporting Rule

State:

- what you ran
- whether it passed or failed
- what remains unverified

Do not replace evidence with confidence.
