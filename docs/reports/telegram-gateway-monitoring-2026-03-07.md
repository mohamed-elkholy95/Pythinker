# Telegram Gateway Monitoring Report

## Summary

This monitoring pass identified 4 primary issues in the Telegram report-delivery path:

1. Reused Telegram sessions could leak stale deliverables from earlier runs.
2. Weakly grounded final reports could still be delivered after summarization.
3. Report-output sanitization was broad enough to rewrite non-report markdown content.
4. Telegram final delivery was paying an unnecessary summarization round-trip even when the cached full draft was already deliverable.

The issue count above matches the 4 detailed findings below.

## Findings

### 1. Cross-run deliverable contamination

Reused Telegram sessions kept writing under the same session workspace root, which allowed stale files from previous runs to survive into later sweeps, manifests, and final attachments.

### 2. Weak final report delivery

The delivery-integrity gate treated some Telegram report-quality failures as warnings. That allowed polished but weak summaries to pass even when references or verification signals were missing.

### 3. Over-broad markdown sanitization

Decorative emoji cleanup was running on markdown-like files broadly enough to affect non-report content. The cleanup needed to stay limited to known report artifacts and known notice formats.

### 4. Redundant summarization latency

When the pre-trim cached draft already satisfied Telegram delivery requirements, the summarize step still ran an unnecessary extra pass instead of sending the already-grounded draft directly.

## Remediation Link

Primary remediation plan: `docs/plans/2026-03-07-telegram-report-integrity-remediation.md`
