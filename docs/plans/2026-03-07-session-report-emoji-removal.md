# Session Report Emoji Removal

> Note: this remains a secondary presentation-cleanup follow-up. The primary Telegram correctness and evidence-integrity remediation is [`docs/plans/2026-03-07-telegram-report-integrity-remediation.md`](./2026-03-07-telegram-report-integrity-remediation.md).

## Goal

Remove decorative emoji prefixes from report presentation without rewriting quoted source text or other non-report markdown content.

## Scope

- Keep heading cleanup for report headings.
- Keep targeted cleanup for known partial/incomplete report notices.
- Do not strip arbitrary blockquotes or generic markdown content.
- Prefer report-artifact metadata, with report-path fallbacks, when deciding whether write-time cleanup should run.
