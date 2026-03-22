# Codex Command Equivalents

This repo does not depend on a custom slash-command system for Codex. Use these thin command equivalents instead.

## Planning

- `/plan`
  - Use `skills/pythinker-plan-execute/SKILL.md`
  - Store plans in `docs/superpowers/plans/`

## Review

- `/review`
  - Use `skills/pythinker-review/SKILL.md`

## Verify

- `/verify`
  - Use `skills/pythinker-verification/SKILL.md`
  - Or run `node .codex/hooks/quality-gate.js` to print the likely verification path

## Harness Audit

- `/harness-audit`

```bash
python3 scripts/ai/harness_audit.py
```

## Skill Stocktake

- `/skill-stocktake`

```bash
python3 scripts/ai/skill_stocktake.py
```

## Session Summary

- `/session-summary`

```bash
python3 scripts/ai/session_summary.py
```
