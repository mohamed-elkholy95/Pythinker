# Agent Workflow Log Monitoring Report

## Scope

- Repo: `Pythinker`
- Date: March 23, 2026
- Session ID: `4871f7cfa70548bb`
- Agent ID: `010608068e3742b5`
- Primary model: `glm-5-turbo`
- Services reviewed: `backend`, `sandbox`, `gateway`
- Live monitor window: `2026-03-23T18:47:08Z` to `2026-03-23T18:53:10Z` (`6m02s`)
- Backfilled retained-log window for full workflow coverage: `2026-03-23T18:44:40Z` to `2026-03-23T18:53:10Z`
- Full workflow session observed from logs:
  - Session object lifetime: `2026-03-23T18:44:43.158823Z` to `2026-03-23T18:52:43.800099Z` (`8m00.641s`)
  - Chat request lifetime: `2026-03-23T18:44:51.802358Z` to `2026-03-23T18:52:43.799542Z` (`471997.22ms`)

## Summary

The Python agent completed the workflow end-to-end: session creation, sandbox warm-up, planning, three execution steps, summarization, verification, and request completion. No container restarts, crashes, or hard backend exceptions were observed. The workflow used `backend` and `sandbox`; `gateway` emitted no relevant events during this session.

The main problems were output integrity and latency, not outright execution failure. The session produced repeated tool-tracing anomalies, required empty-message recovery during execution, needed citation auto-repair during summarization, and still ended with grounding verification flagging `10/16` claims as unsupported (`62.5%`). The summarization phase was especially slow, with `37.3s` time-to-first-token and `134.6s` total stream time.

## Session Metrics

- Total reviewed log lines: `466`
- Container distribution:
  - `backend`: `354`
  - `sandbox`: `112`
  - `gateway`: `0`
- Warning lines: `14`
- Error lines: `10`
- Tool anomaly lines: `11`
- Flagged unsupported-claim lines: `10`
- Tool invocations:
  - Started: `18`
  - Completed: `18`
  - Explicit tool failures: `1`
- Workflow transitions: `7`
- LLM `ask()` calls:
  - Count: `32`
  - Average latency: `7.9s`
  - Min: `2.1s`
  - Max: `40.6s`
  - `>=20s`: `3`
  - `>=30s`: `2`
  - `tools=yes`: `25`
  - `tools=no`: `7`
- LLM `ask_stream()`:
  - TTFT: `37.3s`
  - Completion: `134.6s`
  - Characters streamed: `26825`
- Chat completion event count: `548`

## Timeline

| Time (UTC) | Event | Notes |
| --- | --- | --- |
| `18:44:43.158823Z` | Session created | Session `4871f7cfa70548bb` and agent `010608068e3742b5` created |
| `18:44:43.161121Z` | Sandbox warm-up started | Background warm-up kicked off immediately |
| `18:44:51.570293Z` | Chrome cold start completed | Chrome ready in `5376.6ms` |
| `18:44:51.802358Z` | Chat request started | `POST /api/v1/sessions/4871f7cfa70548bb/chat` |
| `18:44:58.115246Z` | Acknowledgment emitted | User-facing ack delivered before planning |
| `18:44:58.122950Z` | `idle -> planning` | Planning phase begins |
| `18:45:15.062628Z` | Plan structured output completed | `PlanResponse` in `10.0s` |
| `18:45:16.211828Z` | `planning -> executing` | Execution begins |
| `18:45:16.213720Z` | Step 1 started | Research step |
| `18:46:49.953356Z` | Step 1 completed | Action audit later shows expected `search` unmet |
| `18:46:49.955155Z` | `executing -> updating` | Plan update after step 1 |
| `18:46:52.379901Z` | Plan update completed | `PlanUpdateResponse` in `2.4s` |
| `18:46:52.381839Z` | `updating -> executing` | Step 2 begins |
| `18:46:52.381919Z` | Step 2 started | Structured comparison/report drafting |
| `18:47:08.000000Z` | Live monitor attached | Continuous live tail began here |
| `18:48:35.937054Z` | Step 2 completed | Empty-final-message recovery occurred during this phase |
| `18:48:35.937350Z` | `executing -> updating` | Second plan update |
| `18:48:39.295712Z` | Plan update completed | `PlanUpdateResponse` in `3.3s` |
| `18:48:39.295878Z` | `updating -> executing` | Step 3 begins |
| `18:48:39.296561Z` | Step 3 started | Review, validate, and deliver |
| `18:49:21.711197Z` | Status poll observed | UI polling session status remains healthy |
| `18:49:43.499275Z` | No more steps | Execution finished |
| `18:49:43.950773Z` | Final checkpoint written | Step 3 checkpoint persisted |
| `18:49:43.950882Z` | `executing -> summarizing` | Summarization begins |
| `18:50:21.515829Z` | Stream TTFT warning | `37.3s` to first token |
| `18:51:58.785352Z` | Stream completed | `134.6s`, `26825` chars |
| `18:51:58.813065Z` | Citation repair | `24` references rebuilt, `4` fabricated removed |
| `18:52:29.248992Z` | Grounding verification | `10/16` claims unsupported (`62.5%`) |
| `18:52:43.799947Z` | SSE disconnect | Domain stream detached; agent had already continued |
| `18:52:43.800099Z` | Chat completed | Total request time `471983.51ms` |
| `18:53:10.000000Z` | Live monitor stopped | Monitoring session closed |

## Findings By Severity

### Critical

#### 1. Output integrity failure after summarization

- Type: `quality`, `verification`, `grounding`
- Evidence:
  - `2026-03-23T18:52:29.248992Z`: `LLM grounding: 10/16 claims unsupported (score=0.62)`
  - `2026-03-23T18:52:29.249065Z`: `LLM grounding: 10 unsupported claim(s), score: 62.5%`
  - `2026-03-23T18:52:29.249192Z` through `18:52:29.250557Z`: unsupported claims include price, CPU/GPU, weight, battery, launch timing, and hardware feature assertions.
- Impact:
  - The final report likely contained materially unreliable product facts even after summarization, citation repair, and output verification.
  - This is a trust issue, not a cosmetic issue.
- Root-cause inference:
  - The verifier detects unsupported claims but does not hard-fail or force regeneration when the unsupported ratio is high.

### High

#### 2. Summarization required citation repair for fabricated references

- Type: `quality`, `citations`
- Evidence:
  - `2026-03-23T18:51:58.813065Z`: `Rebuilt 24 reference(s) from authoritative source list (removed 4 fabricated)`
  - `2026-03-23T18:51:58.813524Z`: `Citation integrity auto-repair resolved detected issues`
- Impact:
  - The first-pass summary contained fabricated references.
  - Auto-repair mitigated the problem, but only after incorrect citations were produced.
- Root-cause inference:
  - The model can draft citation structures that outrun the retrieved-source set, and the current safeguard is reactive rather than preventive.

#### 3. User-facing latency was high, especially in summarization

- Type: `performance`, `latency`
- Evidence:
  - `2026-03-23T18:48:23.188588Z`: one `ask()` took `40.6s`
  - `2026-03-23T18:49:43.458023Z`: one `ask()` took `22.5s`
  - `2026-03-23T18:50:21.515829Z`: `ask_stream()` TTFT `37.3s`
  - `2026-03-23T18:51:58.785352Z`: `ask_stream()` completed in `134.6s`
  - Chat request duration: `471997.22ms`
- Impact:
  - End-user perceived delay is substantial.
  - Summarization alone consumed roughly the final `3` minutes of the request.
- Root-cause inference:
  - The summarization model path is expensive and late-streaming; no evidence of a faster fallback or progressive partial summary path appears in logs.

#### 4. Final-message robustness broke twice before fallback succeeded

- Type: `model-output`, `resilience`
- Evidence:
  - `2026-03-23T18:46:44.656408Z`: `Attempting summarization recovery for empty final message`
  - `2026-03-23T18:48:30.937862Z`: `Attempting summarization recovery for empty final message`
  - `2026-03-23T18:48:35.912289Z`: `Agent produced empty final message — yielding fallback`
- Impact:
  - The agent could not reliably produce a non-empty final response at least twice.
  - Recovery saved the workflow, but this is a fragile path in a core agent capability.
- Root-cause inference:
  - `glm-5-turbo` is not consistently satisfying the final-output contract in this workflow shape.

### Medium

#### 5. Tool argument validation appears non-blocking or misaligned

- Type: `validation`, `instrumentation`
- Evidence:
  - `2026-03-23T18:48:23.240000Z`: `args_validation_failed on file_write`
  - `2026-03-23T18:48:56.556427Z`: `args_validation_failed, oversized_result on file_read`
  - `2026-03-23T18:49:01.593110Z`: `args_validation_failed on file_read`
  - `2026-03-23T18:49:06.756282Z`: `args_validation_failed on file_read`
  - All four corresponding tool executions still completed successfully.
- Impact:
  - Either the validator is logging false positives, or invalid arguments are allowed through execution.
  - In either case, the signal quality of tool-tracing diagnostics is degraded.
- Root-cause inference:
  - Most likely a schema mismatch between traced arguments and actual tool contracts, or validation is running after normalization/truncation.

#### 6. Step 1 action accounting did not match actual behavior

- Type: `workflow-audit`, `observability`
- Evidence:
  - `2026-03-23T18:46:49.899429Z`: `Step 1 action audit: expected=['search'] fulfilled=[] missed=['search'] tools_used=['browser', 'search']`
- Impact:
  - Audit metadata says `search` was missed even though both search and browser tools were used during the step.
  - This can mislead step-quality assessment and postmortem reporting.
- Root-cause inference:
  - Tool-to-action fulfillment mapping is incomplete or does not treat mixed browser/search evidence as satisfying the `search` action.

#### 7. Retrieval path hit avoidable navigation failure before recovering

- Type: `retrieval`, `resilience`
- Evidence:
  - `2026-03-23T18:47:12.001099Z`: Apple specs URL returned `404`
  - `2026-03-23T18:47:16.386180Z`: search tool instructed to treat source as unavailable
  - `2026-03-23T18:47:20.689425Z` to `18:47:22.780354Z`: fallback `info_search_web` succeeded
- Impact:
  - One tool failure was tolerated, but it added latency and noise.
- Root-cause inference:
  - The agent/browser path attempted a stale or malformed official URL before verifying it via search results.

### Low

#### 8. Sandbox browser emitted repeated SSL and graphics warnings

- Type: `environment`, `browser-runtime`
- Evidence:
  - `10` SSL handshake errors between `18:46:44.347484Z` and `18:47:10.342724Z`
  - `2026-03-23T18:46:47.326708818Z`: `Warning: Couldn't get proc eglChooseConfig`
  - `2026-03-23T18:46:13.993909Z` and `18:46:46.241114Z`: two SSRF-blocked third-party subrequests
- Impact:
  - These did not stop the workflow, but they clutter logs and can hide meaningful browser failures.
- Root-cause inference:
  - The browser is loading pages with blocked or unreachable third-party assets under sandboxed networking/GPU constraints.

## Positive Signals

- Session and agent creation were fast and clean.
- Sandbox warm-up succeeded; Chrome became ready in `5376.6ms`.
- All `18` started tools produced matching completion events.
- Only `1` tool invocation failed explicitly, and the workflow recovered.
- Checkpointing, workspace injection, MinIO upload, citation repair, and final request completion all executed without backend crashes.

## Actionable Recommendations

1. Make grounding verification fail closed above a hard threshold.
   - A report with `10/16` unsupported claims should trigger rewrite, re-research, or user-visible downgrade instead of normal completion.

2. Tighten citation-generation constraints before summarization output is accepted.
   - Auto-repair is useful, but `4` fabricated references indicates the first-pass summary is too unconstrained.
   - Require citations to map to a retrieved-source registry before final emission.

3. Investigate why `args_validation_failed` does not prevent file operations.
   - Confirm whether the validator is false-positive telemetry or whether invalid argument payloads are really executing.
   - If false positive, fix or downgrade the signal. If real, block execution before tool dispatch.

4. Treat empty-final-message recovery as a model-contract bug, not normal behavior.
   - Add explicit metrics and alerting for empty final responses.
   - Consider a stricter structured-output wrapper or a different summarization model path.

5. Reduce summarization latency.
   - The current summarization path adds `37.3s` TTFT and `134.6s` stream time.
   - Consider model substitution for summary generation, earlier streaming, or phase-specific compression before the stream call.

6. Fix step-action fulfillment mapping.
   - The step 1 audit should not report `missed=['search']` when search/browser evidence exists.
   - This should be corrected before relying on audit metrics for evaluation or auto-remediation.

7. Normalize or validate official product URLs before browser navigation.
   - The Apple `404` was recoverable, but it wasted tool budget and time.
   - Prefer verified search results or URL canonicalization for vendor spec pages.

8. Separate benign browser noise from actionable runtime failures.
   - Route repeated Chrome SSL/GPU warnings to a lower-severity channel or tag them so they do not drown out true browser regressions.

## Overall Assessment

The Python agent remained operational and completed the workflow, but the quality guardrails did not fully protect the final answer. The strongest risk is not system stability; it is that the agent can finish successfully while still delivering materially unsupported claims. The highest-value remediation is to make grounding and citation integrity checks block final completion when they cross a defined risk threshold.
