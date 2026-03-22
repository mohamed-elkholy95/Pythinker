# Harness Observations

This directory stores reviewed observations about recurring Codex behavior in the Pythinker repo.

## Storage Model

- raw ephemeral artifacts live under `.codex/session/`
- reviewed summaries live here

## What To Capture

- repeated user corrections
- repeated validation misses
- repeated path confusion
- repeated architecture-boundary mistakes
- repeated tool misuse

## What Not To Do

- do not auto-promote observations into skills
- do not rewrite `AGENTS.md`, `instructions.md`, or `skills/` from raw session artifacts
- do not treat one-off mistakes as stable guidance

## Review Workflow

1. collect raw evidence in `.codex/session/`
2. summarize repeated patterns here
3. update a skill or harness rule only after explicit review

The goal is disciplined harness improvement, not self-modifying prompt drift.
