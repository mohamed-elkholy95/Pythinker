---
name: pythinker-review
description: Review Pythinker changes for bugs, regressions, architectural boundary violations, and missing verification, with findings presented before summaries.
---

# Pythinker Review

Use this skill when asked to review changes or when a significant implementation chunk is ready for inspection.

## Review Priorities

1. Behavioral bugs
2. Regression risk
3. Architecture boundary violations
4. Missing tests or weak verification
5. Type-safety or validation holes

## Pythinker-Specific Checks

- Is business logic leaking into routes or components?
- Did the change add a new outward dependency from `domain/`?
- Are Pydantic v2 validators also marked `@classmethod`?
- Did a frontend change bypass existing composables or stores unnecessarily?
- Did a harness change duplicate rules already defined in `AGENTS.md`, `instructions.md`, or `skills/`?

## Output Format

- Findings first, ordered by severity
- Each finding should reference a concrete file path
- Keep summaries brief and secondary

If there are no findings, say so explicitly and note any residual verification gaps.
