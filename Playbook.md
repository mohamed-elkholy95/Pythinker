# Pythinker Reliability Playbook (Standardized)

Validated: **2026-02-15**

Scope: Python 3.11+, FastAPI/ASGI, Vue 3 + TypeScript, MongoDB/Beanie, Redis, Qdrant, MinIO, WebSockets/SSE, xterm.js/CDP screencast, MCP/LLM agents, Docker + Supervisord, Playwright/Monaco.

This playbook standardizes how to classify, detect, triage, and stabilize failures in the current stack. Use the taxonomy tags in incidents, PRs, tests, dashboards, and postmortems.

Context7 validation baseline used for this revision:
- FastAPI request disconnect checks (`request.is_disconnected`) and WebSocket disconnect handling (`WebSocketDisconnect`).
- ESLint Vue rule coverage for reactivity/lifecycle pitfalls.
- Pydantic v2 validator patterns (`@field_validator` with `@classmethod`) and boundary strictness options.

## 0) Standard Taxonomy

### Plane tags (origin)
- `CL`: Client (Vue/TS/UI runtime)
- `CP`: Control plane (FastAPI, auth, routing, orchestration)
- `EP`: Execution plane (sandbox containers, browser/tool runtime, CDP/X)
- `DP`: Data plane (Mongo/Redis/Qdrant/MinIO)

### Failure mode tags (type)
- `CONC`: Concurrency/deadlock/starvation
- `RES`: Resource leak/exhaustion (mem/fd/cpu)
- `STRM`: Streaming lifecycle (SSE/WS buffering/disconnect/duplication)
- `SCHEMA`: Validation/contract drift (Pydantic/OpenAPI/TS)
- `SEC`: Security (injection, authz/authn, token, SSRF, XSS)
- `PERF`: Latency/throughput regression
- `CONS`: Consistency/ordering/idempotency
- `OPS`: Deploy/runtime config (docker/proxy/signals/logging)

### Tag usage rule
Every incident, bug ticket, and remediation PR must include:
- One plane tag
- One primary failure mode tag
- Optional secondary failure mode tag

Example: `CP/STRM` or `EP/OPS+RES`.

## 1) Deterministic-First Incident Workflow

1. Capture impact, scope, first failing timestamp (absolute date/time, timezone).
2. Assign tags using section 0.
3. Run deterministic checks first (static rule, reproducible test, explicit runtime probe).
4. Only then use heuristic signals (trend anomalies, correlated spikes).
5. Apply stabilizing pattern from section 2 while root cause fix is in progress.
6. Record owner and remediation status as `Completed`, `In Progress`, or `Not Started`.

## 2) Merged Top Issue List (Standardized)

Each entry: **Issue -> Symptoms -> Deterministic Detection -> Heuristic Detection -> Stabilizing Pattern**.

### A) FastAPI / asyncio / event loop (`CP/CONC/RES/PERF`)

#### 1. Event loop blocking (sync I/O or CPU in `async def`)
- Symptoms: request stalls, WS ping/pong drops, SSE freezes, low CPU but hung behavior.
- Deterministic detection: Ruff `flake8-async` (`ASYNC210`, `ASYNC251`); code audit for `requests`, `time.sleep`, CPU-heavy loops in endpoints.
- Heuristic detection: event-loop lag and p95 latency spikes without proportional CPU increase.
- Stabilizing pattern: offload CPU to process pool; sync I/O via `run_in_threadpool`; cooperative yields in long loops; CI async-safety gate.

#### 2. Orphaned tasks/background leaks
- Symptoms: rising CPU, memory creep, work continues after client disconnect.
- Deterministic detection: audit `create_task()` call sites for missing cancellation/join path.
- Heuristic detection: growing task/thread counts and per-session work after disconnect.
- Stabilizing pattern: per-session task registry; `finally` cancel+await; bounded queues; explicit timeouts.

#### 3. RSS creep/allocator fragmentation
- Symptoms: RSS rises and does not drop while GC appears normal.
- Deterministic detection: compare `tracemalloc` snapshots vs RSS; allocator inspection (musl/alpine risk).
- Heuristic detection: steady RSS growth tied to large buffers/stream payloads.
- Stabilizing pattern: jemalloc with decay config when needed; avoid large base64 payloads; stream bytes; cap WS/SSE frame sizes.

### B) Streaming (SSE + WebSockets) (`CL/CP/STRM/RES/CONS`)

#### 4. SSE generator continues after disconnect
- Symptoms: backend continues DB/API calls after client drop; token/cost burn continues.
- Deterministic detection: ensure loop checks `await request.is_disconnected()` and response has send timeout.
- Heuristic detection: downstream calls continue after client disconnect.
- Stabilizing pattern: disconnect-aware generators; send timeout; heartbeats that flush; fallback non-streaming mode.

#### 5. Proxy buffering breaks SSE
- Symptoms: events arrive in bursts or all-at-once.
- Deterministic detection: reproduce through production proxy path; verify buffering/compression headers and proxy config.
- Heuristic detection: long idle gaps followed by bulk delivery.
- Stabilizing pattern: disable buffering for SSE; heartbeat cadence; disable buffering transforms/compression where required.

#### 6. WebSocket accumulation/stale references
- Symptoms: too many open connections, memory/CPU creep.
- Deterministic detection: require `try/except WebSocketDisconnect` and `finally` cleanup from connection manager.
- Heuristic detection: open WS count only rises; per-connection tasks never terminate.
- Stabilizing pattern: strict connection lifecycle manager; close-code policy (e.g., `1008` for policy); cancel per-connection tasks on close.

#### 7. Reconnect duplication/ordering faults
- Symptoms: duplicated messages around reconnect; partial history replay conflicts.
- Deterministic detection: validate event IDs + `Last-Event-ID` handling; client dedupe keyed by message ID.
- Heuristic detection: duplicates cluster around transient network blips.
- Stabilizing pattern: globally unique IDs; idempotent client reducer; bounded replay window.

### C) Pydantic v2 + API contracts (`CP/DP/SCHEMA/SEC/CONS`)

#### 8. Silent data loss from `extra='ignore'`
- Symptoms: typoed client fields silently dropped; incorrect defaults downstream.
- Deterministic detection: `@model_validator(mode='before')` logging for unknown fields; contract tests.
- Heuristic detection: telemetry on unexpected fields per endpoint.
- Stabilizing pattern: ignore-but-log for non-critical boundaries; forbid on critical endpoints; schema drift alerts.

#### 9. Over-strict `extra='forbid'` causes brittle clients
- Symptoms: sudden 422 spikes after additive client changes.
- Deterministic detection: compatibility tests; OpenAPI schema diffs in CI.
- Heuristic detection: deploy-correlated 422 increase.
- Stabilizing pattern: endpoint versioning; additive changes default-allow with telemetry and deprecation windows.

#### 10. Typing gaps bypass validation
- Symptoms: runtime type surprises despite model boundaries.
- Deterministic detection: Ruff `ANN*`, Pyright strict mode; ban `Any` in request/response models.
- Heuristic detection: runtime type mismatch counters.
- Stabilizing pattern: `Annotated` dependency types; explicit return typing; schema tests at boundaries.

### D) Vue 3 reactivity + TS (`CL/CONS/RES/PERF`)

#### 11. Reactivity severed by destructuring props/reactive objects
- Symptoms: stale UI despite state updates.
- Deterministic detection: ESLint `vue/no-setup-props-reactivity-loss`.
- Heuristic detection: intermittent stale fields after navigation/state transitions.
- Stabilizing pattern: `toRefs()` prior to destructuring; composable conventions; lint gate required in CI.

#### 12. Ref used as operand (`Ref` object truthiness bugs)
- Symptoms: auth/feature flags incorrectly always true; equality checks fail.
- Deterministic detection: ESLint `vue/no-ref-as-operand`.
- Heuristic detection: logic works only when logged/inspected with `.value`.
- Stabilizing pattern: unwrap refs in script logic; use computed wrappers; enforce lint gate.

#### 13. Lifecycle/watch registration after `await`
- Symptoms: leaked watchers, duplicated handlers, memory growth after route changes.
- Deterministic detection: ESLint `vue/no-lifecycle-after-await` and `vue/no-watch-after-await`.
- Heuristic detection: handler counts increase on repeated mount/unmount cycles.
- Stabilizing pattern: register hooks synchronously; move async work inside hook callback; composable authoring checklist.

### E) xterm.js / browser streaming security + correctness (`CL/EP/SEC/STRM`)

#### 14. PTY resize race corrupts terminal rendering
- Symptoms: wrap corruption and curses glitches during resize under load.
- Deterministic detection: replay rapid resize while streaming heavy stdout.
- Heuristic detection: reproduces only when load and resize coincide.
- Stabilizing pattern: atomic resize protocol; backend `ioctl(TIOCSWINSZ)` + `SIGWINCH`; apply backpressure.

#### 15. Escape-sequence injection/DCS abuse
- Symptoms: suspicious terminal behavior, unwanted paste/input, exfiltration paths.
- Deterministic detection: ANSI/DCS parser review; sanitizer fuzzing.
- Heuristic detection: anomalous clipboard/input events while viewing logs/output.
- Stabilizing pattern: sanitize terminal output; disable dangerous sequences; avoid `innerHTML`/`eval`; treat terminal output as untrusted.

### F) MCP / LLM agent orchestration (`CP/SEC/CONS/OPS`)

#### 16. Confused deputy / indirect prompt injection
- Symptoms: unauthorized tool calls, data exfil attempts, unsafe actions.
- Deterministic detection: red-team prompt suite; tool policy tests; approval flow tests.
- Heuristic detection: high-risk tool calls triggered by untrusted content.
- Stabilizing pattern: capability-scoped tool authz; human approval for high-impact actions; provenance tagging; deny-by-default tool catalog.

#### 17. Command injection via tool args
- Symptoms: arbitrary command execution on tool host.
- Deterministic detection: SAST rules for `shell=True`, `os.system`, string command execution.
- Heuristic detection: anomalous separators/tokens (`;`, `&&`, `|`) in tool args.
- Stabilizing pattern: `subprocess.run([...], shell=False)`; strict arg schema allowlists; path normalization.

#### 18. SSRF through fetch/browse tools
- Symptoms: requests to metadata/internal endpoints (e.g., `169.254.169.254`).
- Deterministic detection: URL validator tests + egress policy tests; deny private ranges.
- Heuristic detection: unusual internal destination traffic from tool runner.
- Stabilizing pattern: egress filtering; private CIDR denylist; DNS pinning; policy-aware fetch proxy.

#### 19. Token passthrough / audience confusion
- Symptoms: token reuse across unintended services.
- Deterministic detection: JWT tests for `aud`, `iss`, `scope`; assert no downstream passthrough.
- Heuristic detection: cross-service token reuse anomalies.
- Stabilizing pattern: per-service minted tokens; short TTL and rotation; minimal scopes; audited token events.

### G) RAG + Qdrant (`DP/CP/CONS/PERF`)

#### 20. Embedding drift/dimension mismatch
- Symptoms: retrieval quality drops, empty/irrelevant hits.
- Deterministic detection: enforce embedding model version metadata; validate vector dimensions on upsert/query; collection schema checks.
- Heuristic detection: `Recall@K`, `MRR`, `NDCG` regression trends.
- Stabilizing pattern: versioned collections (`memory_v1`, `memory_v2`); full reindex on model change; continuous eval gates.

#### 21. Retrieval timing desync
- Symptoms: generation starts with empty/partial context intermittently.
- Deterministic detection: enforce await ordering; trace spans retrieval -> prompt build -> LLM call.
- Heuristic detection: occasional empty context despite available corpus.
- Stabilizing pattern: pipeline barriers; bounded timeouts; fallback retrieval path; structured prompt builder.

#### 22. Position bias (lost in the middle)
- Symptoms: relevant chunks retrieved but ignored in answer.
- Deterministic detection: reranker and prompt placement A/B tests.
- Heuristic detection: answer cites low-relevance early chunks.
- Stabilizing pattern: two-stage retrieval + reranker; inject only top 3-5; deterministic chunk ordering.

### H) MongoDB / Beanie (`DP/CP/PERF/CONS/RES`)

#### 23. N+1 linked-document fetches
- Symptoms: nonlinear latency growth with relation depth.
- Deterministic detection: DB call count per request; worst-case fixture tests.
- Heuristic detection: p95/p99 blow-up with larger documents.
- Stabilizing pattern: `fetch_links=True` or aggregation/prefetch; required indexes.

#### 24. Lost updates from concurrent writes
- Symptoms: session/tool state rollback or overwrite anomalies.
- Deterministic detection: optimistic concurrency/revision tests with parallel writers.
- Heuristic detection: rare state anomalies under concurrency.
- Stabilizing pattern: revision tokens; compare-and-set retry with backoff; transactional patterns where supported.

### I) Redis coordination + cache split (`DP/CP/CONS/RES/OPS`)

#### 25. Wrong Redis instance for key class
- Symptoms: inconsistent rate limiting, missing revocations, disappearing jobs.
- Deterministic detection: config assertions and key-prefix integration tests.
- Heuristic detection: unexpected TTL/eviction behavior by key type.
- Stabilizing pattern: strict namespaces; separate clients; startup assertions; per-instance dashboards.

#### 26. Eviction/TTL stampede
- Symptoms: synchronized load spikes and cache miss storms.
- Deterministic detection: eviction counter monitoring + expiry load tests.
- Heuristic detection: periodic synchronized latency spikes.
- Stabilizing pattern: TTL jitter; request coalescing; circuit-breaker fallbacks.

### J) MinIO object lifecycle (`DP/CL/OPS/CONS/SEC`)

#### 27. Presigned URL host/clock/CORS mismatch
- Symptoms: `403 SignatureDoesNotMatch`, browser-only failures.
- Deterministic detection: browser-path integration test; verify external hostname and clock sync.
- Heuristic detection: failures concentrated by environment/client.
- Stabilizing pattern: environment-aware public base URL; NTP sync; explicit CORS policy; avoid docker-internal hostnames in browser URLs.

#### 28. Transient network instability + retry amplification
- Symptoms: `MaxRetryError`, `ResponseError`, cascading timeouts.
- Deterministic detection: chaos/drop simulation.
- Heuristic detection: correlated storage error spikes.
- Stabilizing pattern: exponential backoff with bounded retries; startup health checks (`bucket_exists()`).

### K) Containers + Supervisord + logging (`EP/OPS/RES`)

#### 29. Signal swallowing and zombie processes
- Symptoms: unclean shutdowns, orphaned connections, slow termination.
- Deterministic detection: staged `SIGTERM` drills and teardown verification.
- Heuristic detection: orphan connections/processes increase after deploys.
- Stabilizing pattern: `stopsignal=TERM`; `exec` entrypoints; correct PID1 behavior.

#### 30. Log buffering masks root cause
- Symptoms: crash with missing trailing logs.
- Deterministic detection: crash test with unbuffered logging verification.
- Heuristic detection: missing final error lines around failure window.
- Stabilizing pattern: `PYTHONUNBUFFERED=1`; structured logs with correlation IDs.

### L) E2E + Monaco + Playwright (`CL/EP/CONS/OPS`)

#### 31. Flaky UI tests from async DOM/worker timing
- Symptoms: intermittent CI failures and non-reproducible local runs.
- Deterministic detection: Playwright traces, explicit readiness checks, deterministic network stubbing.
- Heuristic detection: failure clusters under CI load.
- Stabilizing pattern: `page.route()` for deterministic network; strict locators/visibility waits; trace-on-retry.

## 3) Standard Detection Toolchain (Deterministic First)

### Static gates (PR blocking)

Backend:
- `conda activate pythinker && cd backend && ruff check .`
- `conda activate pythinker && cd backend && ruff format --check .`
- `conda activate pythinker && cd backend && pytest tests/`
- Pyright/Mypy strict profile for boundary packages (request/response, domain DTOs).
- SAST grep rules: block `shell=True`, `os.system`, unsafe command concatenation.

Frontend:
- `cd frontend && bun run lint`
- `cd frontend && bun run type-check`
- Required Vue rules: `vue/no-setup-props-reactivity-loss`, `vue/no-ref-as-operand`, `vue/no-lifecycle-after-await`, `vue/no-watch-after-await`, `vue/no-template-shadow`.

Dependency/security hygiene:
- `pip-audit` (backend) and `npm audit`/Bun equivalent (frontend) in CI.

### Runtime profiling (root cause proof)
- Event-loop lag histogram + request latency histogram.
- Active task/thread counts + open file descriptors.
- Active SSE/WS connections and disconnect/reconnect rates.
- RSS and `tracemalloc` snapshots for memory leak triage.
- Distributed traces for retrieval, tool execution, storage calls, and stream generator loops.

### Heuristic detection (degradation early warning)
- RAG quality metrics (`Recall@K`, `MRR`, `NDCG`) and embedding drift alerts.
- Streaming health metrics (heartbeat receipt rate, reconnect rate, bytes/sec continuity).
- Security anomaly metrics (blocked SSRF, policy-denied tool calls, suspicious command tokens).

## 4) Standard Stability Patterns (Always-On Checklist)

### Streaming
- Heartbeats with verified flush.
- Disconnect-aware loops and explicit send/read timeouts.
- Idempotent event IDs with dedupe/replay semantics.

### Concurrency
- No blocking calls inside async handlers.
- CPU offload and bounded work queues.
- Per-session cancellation and cleanup semantics.

### Resource hygiene
- Cleanup in `finally` for WS/tasks/subscriptions.
- Caps on payload/frame size and connection limits.
- Memory allocator strategy when RSS pressure appears.

### Contracts
- Unknown-field policy explicitly chosen per endpoint (`ignore+log` vs `forbid`).
- OpenAPI diffs and schema compatibility checks in CI.
- Strict typing at boundaries; no unbounded `Any` in critical models.

### LLM/MCP security
- Capability-based authz per tool.
- Deny-by-default tool exposure.
- Human approval for destructive/high-scope operations.
- Structured args only; no shell command passthrough.
- SSRF egress controls and token audience validation.

### Data correctness
- Beanie prefetch/aggregation where N+1 appears.
- Optimistic concurrency for mutable shared state.
- Redis namespace isolation + TTL jitter.
- Qdrant collection versioning with full reindex on embedding change.
- MinIO external URL correctness + CORS + clock sync.

### Operations
- Graceful signal handling and clean teardown.
- Unbuffered structured logs with correlation IDs.
- Canary checks for streaming and sandbox readiness.

### Testing
- Boundary smoke tests for SSE, WS takeover, sandbox spawn/tool run, and Mongo/Redis/Qdrant/MinIO CRUD.

## 5) Boundary Smoke Test Minimums

Run these in a compose-backed CI job at least once per merge to `main`:

1. SSE stream opens, heartbeat arrives, forced reconnect replays without duplicates.
2. WS takeover channels (`screencast`, `input`) connect and exchange expected frames/messages.
3. Sandbox starts and runs one minimal Python tool, one minimal Node tool, one minimal Playwright navigation.
4. Mongo CRUD for session docs with linked-document retrieval path.
5. Redis coordination key round-trip and cache key TTL/eviction sanity.
6. Qdrant insert + search on active collection version.
7. MinIO put/get and browser-path presigned URL fetch.

## 6) Ownership Mapping

- `CL`: Frontend owner (Vue/TS/runtime UX)
- `CP`: Backend/API owner (FastAPI/auth/orchestration)
- `EP`: Runtime/platform owner (sandbox/container/supervisor)
- `DP`: Data/platform owner (Mongo/Redis/Qdrant/MinIO)

Primary owner is assigned by plane tag. Secondary reviewers are assigned from any secondary failure mode.

## 7) Maintenance Rule

Update this playbook in the same PR when changing:
- Streaming protocols/events/retry semantics
- Sandbox lifecycle/runtime process graph
- Data store topology, schema policy, or cache partitioning
- Tool execution security controls

Do not mark a playbook control as implemented until code, tests, and runtime probes are all in place.
