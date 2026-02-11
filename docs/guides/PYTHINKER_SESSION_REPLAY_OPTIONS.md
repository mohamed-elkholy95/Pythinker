# Session Replay Replacement Decision (Pythinker)

> Last updated: 2026-02-11
> Decision: remove OpenReplay and use in-app screenshot replay only.

## Decision Summary

Pythinker now uses a zero-cost, self-hosted replay path:

- Live view: CDP-first with VNC fallback (unchanged)
- Replay: screenshot timeline playback
- No OpenReplay SDKs, services, session linkage APIs, or model fields

This removes OpenReplay service overhead and keeps replay fully in the existing stack.

## What Changed

- Removed frontend OpenReplay tracker integration and replay iframe player.
- Removed backend OpenReplay route and schema/model fields.
- Removed OpenReplay Docker compose file and env template entries.
- Kept screenshot replay composable and viewer as the canonical replay implementation.

## Current Replay Flow

1. Session runs with normal live view (`LiveViewer`).
2. Backend stores screenshot timeline data.
3. When session is `completed` or `failed`, frontend loads screenshot metadata and images.
4. Tool panel replay controls navigate screenshot timeline.

## Tradeoffs

### Pros

- Zero additional vendor cost.
- Fewer services to run and maintain.
- Smaller frontend dependency surface.

### Cons

- No full DOM/session recording.
- Replay fidelity limited to screenshot cadence.

## Future Option (if higher fidelity is needed)

If you later want higher-fidelity replay without SaaS, evaluate a self-hosted `rrweb` pipeline on top of existing MongoDB storage. Keep this out of current scope unless screenshot replay proves insufficient.
