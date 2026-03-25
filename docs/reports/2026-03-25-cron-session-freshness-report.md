# Pythinker Cron Session Freshness Report

Date: 2026-03-25
Status: in progress

## Objective
Fix cron-run session behavior so the autonomous canary creates a fresh Pythinker session, does not latch onto an old/cancelled one, and reports failures clearly when freshness or completion guarantees are violated.

## What was observed before patching
- Manual cron trigger worked.
- Monitoring stack queries/log pulling worked.
- Pythinker session API activity occurred.
- A visible session (`bb8f0fa6ef68469f`) ended cancelled instead of clearly completing.
- The failure pattern strongly suggested session reuse / wrong-session attachment / premature stop semantics in the cron canary flow.

## Root-cause hypothesis
The cron flow was prompt-driven and insufficiently strict about:
1. proving the session was newly created,
2. binding all follow-up monitoring to that exact new session id,
3. treating stop/cancel/reuse as hard failures,
4. tagging each run uniquely for auditability.

Because the API supports idempotency and exposes stop/cancel endpoints, a weak runbook can accidentally reuse or terminate the wrong session without noticing.

## Changes made
### 1. `.pythinker-cron/cycle-prompt.md`
Updated the live task test section to require:
- unique run tag per cycle,
- snapshot of recent sessions before creation,
- unique `X-Idempotency-Key`,
- hard validation that returned `session_id` did not exist before creation,
- failure on reused session ids,
- failure on attaching to a different session,
- failure on cancelled/stopped canary sessions,
- explicit recording of run tag, session id, endpoint, freshness result, final status.

### 2. `.pythinker-cron/run-cycle.sh`
Updated runner to:
- generate and export a unique run tag,
- inject run-tag/session-freshness requirements into Claude via `--append-system-prompt`,
- mark known session lifecycle failure markers in the log as a hard failure by overriding exit code.

## Remaining validation steps
1. Run the patched cron runner or a dry-run canary against the live dev stack.
2. Confirm a newly created session id does not appear in the pre-create session list.
3. Confirm no `/stop` or `/cancel` is issued for the fresh canary session.
4. Confirm final session state is non-cancelled and clearly successful or clearly reported failed.
5. Review any remaining issues aside from logs:
   - ambiguous API semantics between create session and start work,
   - unclear completion-state contract,
   - auth/session listing edge cases,
   - SSE disconnect side effects,
   - idempotency-key reuse windows.

## Open issues to review next
- Whether the canary currently uses the correct endpoint after session creation to actually start the task.
- Whether EventSource/SSE disconnect logic can indirectly trigger deferred cancellation.
- Whether session status semantics are rich enough to distinguish complete vs idle vs aborted.
- Whether cron should use `require_fresh_sandbox=true` for stricter isolation.

## Conclusion
The main fix here is not a backend rewrite; it is making the cron autonomous flow prove freshness and fail loudly when it cannot. If backend behavior still cancels a truly fresh session after this, the next bug is likely in session lifecycle handling rather than the cron instructions.