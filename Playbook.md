# Pythinker Bug Playbook for the Current Stack

This playbook is written against the stack you provided (validated **2026-02-15**) and focuses on how bugs tend to manifest across the **Vue 3 ↔ FastAPI streaming ↔ sandbox containers ↔ storage** boundaries, plus the fastest ways to isolate root cause and mitigate impact.

## System overview and bug-surface map

Pythinker’s highest-risk bug surfaces line up with its cross-service, streaming-heavy runtime model: a Vue 3 UI that must remain responsive while consuming SSE streams and WebSockets, a FastAPI backend that orchestrates sessions/tools and proxies real-time sandbox streams, and sandboxes that run browsers and tools inside constrained containers with X/VNC/CDP plumbing. Your persistence topology (MongoDB for domain/session state, Redis for runtime coordination, Qdrant for vector memory, MinIO for object artifacts) introduces classic “it worked yesterday” failure modes: connectivity, timeouts, incompatible assumptions about eventual consistency, and misaligned TTL/caching behaviors.

![Pythinker integration boundaries](sandbox:/mnt/data/pythinker_architecture.png)

A practical way to think about debugging Pythinker is to treat the platform as four “fault planes”:

**Client plane (frontend)**: Vite build/runtime, streaming consumers (`fetch-event-source` and native `EventSource`), WebSocket takeover UI, heavy interactive components (Monaco, Tiptap, Plotly/Konva), and networking/cors/proxy behavior.

**Control plane (backend)**: FastAPI routes and dependency wiring (`backend/app/main.py`, `backend/app/interfaces/api/routes.py`), SSE event composition (`backend/app/interfaces/api/session_routes.py`), WebSocket proxy endpoints (`/sessions/{session_id}/vnc`, `/screencast`, `/input`), auth/JWT, rate limiting/token revocation in Redis, and tool orchestration plus external calls (OpenAI, browser tool agents).

**Execution plane (sandbox containers)**: container lifecycle via Docker socket (backend-managed), browser installs and Playwright runtime, Node/Python tool runtime, and GUI streaming stack (`xvfb`, `x11vnc`, `websockify`, `openbox`, `supervisord`) under restrictive security settings (seccomp, `no-new-privileges`, `cap_drop`).

**Data plane (Mongo/Redis/Qdrant/MinIO)**: schema/index drift, TTL/eviction surprises, vector collection mismatches, presigned URL clocks/hosts, object lifecycle inconsistencies, and cross-service consistency gaps.

When you debug, the goal is to quickly answer one question: **which plane is failing first?** Everything else is follow-through.

## Triage workflow and evidence capture

### Establish impact, scope, and “first failing timestamp”
Start every bug/incident with three short facts (write them into the ticket immediately):

**Impact**: what is broken from the user’s point of view (e.g., “chat stream stalls after tool call begins”, “takeover view black screen”, “files fail to upload”).

**Scope**: single user/session or systemic; single sandbox or all sandboxes; single deployment profile or all.

**First failing timestamp**: exact local time and timezone (your environment is America/New_York) plus how long it has been happening.

This makes log correlation and bisecting possible across services, especially because streaming systems often “fail silently” until a timeout.

### Produce a minimal reproduction that crosses the boundary once
Design reproductions so they cross **exactly one boundary** if possible:

- UI-only: reproduce without backend changes by mocking SSE/WebSocket or using fixture responses.
- Backend-only: reproduce with a headless client (`curl`, `httpx`, or a tiny script) calling the SSE/WebSocket endpoints.
- Sandbox-only: reproduce by attaching directly to the sandbox container and running the tool/browser sequence there.
- Storage-only: reproduce with direct DB/object calls (Mongo query, Redis command, Qdrant collection check, MinIO object retrieval).

If your reproduction crosses UI → backend → sandbox → storage all at once, you’ll waste time.

### Capture “required evidence” before you restart anything
Before restarting containers or redeploying, capture evidence that disappears:

**Correlation IDs / session IDs**: always note `session_id` (since your routes are session-scoped) and any user ID.

**Streaming transcript**: in the browser devtools Network tab, save the SSE stream and WebSocket frames (or at minimum screenshots of the frames around failure).

**Container state**: `docker compose ps` and `docker compose logs --tail=200 <service>` for `frontend`, `backend`, the relevant `sandbox`/`sandbox2`, plus `mongodb`, the two Redis instances, `qdrant`, and `minio`.

**Resource symptoms**: CPU/memory spikes (OOM-kills), file descriptor exhaustion, disk pressure, or throttling. Most “it hangs” bugs in streaming stacks are either buffering or resource starvation.

### Apply a standard decision ladder
Use this ladder to converge quickly:

- **If the frontend shows disconnect / reconnect loops** → suspect proxy buffering, server-side heartbeat, or auth on a signed URL.
- **If SSE connects but events stop** → suspect backend generator blocked (DB call, tool call, deadlock), or server flush/keepalive not happening.
- **If WebSocket connects but video/input doesn’t work** → suspect sandbox streaming subsystem (X/VNC/CDP), port/proxy routing, or permission limits.
- **If tool execution fails intermittently** → suspect sandbox resource limits, Playwright browser install/path, or Docker socket lifecycle races.
- **If the backend throws 5xx under load** → suspect Redis/Mongo connection pool exhaustion, long-running tasks on the event loop, or downstream rate limits.

## Streaming and realtime runbooks

This section targets the “Pythinker special”: **SSE for chat/session events** and **WebSockets for takeover (VNC/screencast/input)**. Most user-visible bugs will land here.

### SSE bug patterns and how to isolate them quickly
Your backend uses `EventSourceResponse` in `backend/app/interfaces/api/session_routes.py`, and the frontend consumes SSE via both `@microsoft/fetch-event-source` and native `EventSource`. That means you need to consider two distinct client implementations and their retry/resume differences.

**Symptoms you’ll see**
A chat stream that freezes mid-response, duplicated messages after reconnect, messages arriving in bursts (buffering), or a client that permanently shows “connecting”.

**Fast isolation checks**
Check these in order, because each eliminates a whole class of causes:

1) **Is the connection dropping or just stalling?**  
In browser devtools Network tab, see if the SSE request completes/aborts, or stays open but stops receiving bytes.

2) **Does the failure reproduce in both SSE transports?**  
If `fetch-event-source` fails but native `EventSource` works (or vice versa), suspect client parsing/retry handling or signed URL handling differences.

3) **Does it reproduce without nginx / in dev profile?**  
Because your production-like containerized profile runs the frontend behind nginx, proxy buffering and timeouts can be radically different from local dev.

**Most common root causes in SSE stacks**
- **Proxy buffering**: nginx (or a load balancer) buffers server output, so “streaming” becomes “chunked at random”. This creates the classic “it finishes all at once” bug.
- **Missing/insufficient heartbeat**: idle connections get cut by proxies if no bytes are sent periodically.
- **Event format drift**: one side expects `event:` / `data:` format or JSON envelope fields that the other side stopped sending.
- **Reconnect semantics**: client retries can cause duplicate events unless you use an event ID and handle `Last-Event-ID` logic consistently.
- **Backend generator blocked**: your SSE endpoint is alive, but the code producing events is awaiting a slow DB call, external API, a lock, or a tool execution.

**Concrete debugging steps**
Run through these steps without changing code if possible:

- Compare devtools “Timing” and “Response” behavior for the failing SSE call between:
  - local dev (`docker-compose-development.yml` or direct dev server)
  - containerized deployment (`docker-compose.yml` / nginx front)
- In backend logs, search for the SSE route entry log and confirm whether it logs periodic heartbeats (your playbook suggests heartbeat/retry metadata is handled explicitly).
- Temporarily reduce the system to one worker and one sandbox to rule out race conditions and load balancing issues. Streaming bugs frequently appear only when multiple workers are present.

**Mitigations that are safe during an incident**
- Prefer **degrading to non-streaming** (deliver whole response) when a streaming route is unstable. This keeps the product functioning while you fix buffering/heartbeat.
- Increase heartbeat frequency slightly and ensure the heartbeat actually flushes data (a heartbeat that never reaches the client is not a heartbeat).
- If duplicates appear after reconnect, temporarily treat SSE messages as idempotent client-side by discarding already-seen message IDs.

### WebSocket takeover bugs (VNC/screencast/input proxy)
Your backend exposes WebSocket proxy routes:
- `/sessions/{session_id}/vnc`
- `/sessions/{session_id}/screencast`
- `/sessions/{session_id}/input`

Your frontend uses signed URLs with browser WebSocket clients, and the sandbox provides display/remote control via `xvfb`, `x11vnc`, `websockify`, `openbox`, and `supervisord`.

**Symptoms you’ll see**
Black screen, frozen frame, input lag, “connected but nothing happens”, immediate disconnect on connect, or one of the three channels works while another fails.

**One-minute isolation**
You can isolate takeover failures by checking whether each channel is independently healthy:

- **VNC channel**: if VNC fails but input connects, suspect the sandbox display server or VNC server.
- **Screencast channel**: if screencast fails but VNC works, suspect CDP/video pipeline (depending on implementation) or whichever component produces frames.
- **Input channel**: if video works but input doesn’t, suspect permission/key mapping or the proxy’s message routing.

**The fastest way to find the failing plane**
- If the browser WebSocket fails to connect at all, suspect **backend auth/signed URL** or **reverse proxy Upgrade headers**.
- If the WebSocket connects but no frames arrive, suspect **sandbox runtime** (X/VNC/CDP not running) or **backend proxy routing**.
- If it works for some sessions but not others, suspect **sandbox lifecycle/container reuse** bugs or per-session resource leaks.

**Sandbox-first checks**
Attach to the sandbox container for the failing session and validate that the supervisor-managed processes are alive. Even without exact paths, the intent is:

- Confirm `supervisord` is running and managing `xvfb`, `openbox`, `x11vnc`, and `websockify`.
- Confirm the display is available (`DISPLAY` set, X socket exists) and that the VNC server is bound.
- Confirm ports are listening inside the container and correctly mapped/proxied.

**Mitigation options**
- Restart only the affected sandbox container (not the whole system) if takeover is session-scoped.
- If takeover is broadly broken, temporarily disable takeover features in UI (feature flag) while you fix proxy headers or sandbox start order.

## Sandbox and tool-execution runbooks

Pythinker’s sandboxes are not generic “run a command” containers; they are **browser-capable, GUI-capable, security-constrained execution environments**. That combination yields a predictable set of bug classes.

### Container lifecycle and Docker socket orchestration
Your backend requires a Docker socket mount to provision/manage sandbox containers. That makes these failure modes common:

**Symptoms**
Tools never start, sessions hang while “starting sandbox”, sandboxes leak over time, or the backend logs permission errors when trying to create containers.

**Likely causes**
- Docker socket missing or not mounted in the running backend container.
- Permission mismatch (backend process user can’t access the socket).
- Resource limits / quotas prevent new containers from starting.
- Container naming/cleanup race conditions (especially with `sandbox` and `sandbox2` and concurrent sessions).

**Debug flow**
- Confirm the backend container can talk to Docker at runtime (simple container list / create test).
- Check for stuck “created” containers, restart loops, or containers that never pass health checks.
- Look for cleanup logic failures: on session end, ensure sandbox is actually stopped/removed.

**Mitigation**
- Drain new sessions (stop provisioning new sandboxes) while allowing existing sessions to complete.
- Force-remove only the sandboxes belonging to broken sessions, not the entire stack, to preserve state in Mongo/Redis.

### Playwright/browser automation failures
Your sandbox installs Playwright browsers in the image and is Chromium-first. Typical bug patterns:

**Symptoms**
Browser launch fails, browser downloads missing, “executable doesn’t exist”, crashes when opening pages, flaky navigation, or works locally but fails in container.

**Likely causes**
- Browser executable path differences between build-time and runtime layers.
- Missing OS dependencies (fonts, libX*, shared libraries).
- Running headful without X correctly configured (DISPLAY/Xvfb issues).
- Concurrency/resource exhaustion (too many headless Chromium instances).

**Debug flow**
- Run a minimal Playwright script inside the sandbox container (one page, one navigation).
- Validate that the expected browser binaries exist where your runtime expects them.
- If using headful: validate Xvfb and window manager are running before browser launch.

**Mitigation**
- Reduce concurrency per sandbox and queue tool runs via Redis (if already used for coordination).
- Fall back to headless-only mode temporarily when X stack is unstable.

### GUI streaming stack failures (Xvfb + VNC + websockify)
Because you’re using `xvfb`, `x11vnc`, and `websockify`, you inherit classic GUI-remote pitfalls:

- X server not running or crashed
- VNC server bound to wrong display
- websockify not connected to VNC port
- supervisor starts processes in the wrong order (websockify comes up before VNC)
- health checks that don’t actually validate end-to-end readiness

**Operational rule**: treat takeover readiness as an **end-to-end** property. A green container health check is meaningless if it only checks that a process exists, not that frames can be produced.

## Storage and state runbooks

In Pythinker, persistent correctness depends on four stores that behave very differently. Bugs often happen when assumptions from one store are applied to another.

### MongoDB (Beanie/Motor) session and domain state issues
**Symptoms**
Sessions “disappear”, tool state reverts, auth/session lookups fail, unexpected validation errors, or performance degrades with time.

**Primary suspects**
- Index drift (missing indexes, wrong compound indexes for session lookups).
- Document growth (chat transcripts or tool histories expanding without bounds).
- Connection pool saturation or timeouts under load.
- Pydantic v2 validation strictness changes causing previously-accepted payloads to fail.

**Debug flow**
- Identify the exact query pattern failing (find-by-session-id, user-to-session mapping, auth token record).
- Check whether failures correlate with large sessions (big documents).
- Examine whether the problem is write-path (insert/update failures) or read-path (query/index).

**Mitigations**
- Add guarded truncation/archival for unbounded fields (chat logs, tool transcripts).
- Introduce pagination or split documents for long sessions to avoid the “one document to rule them all” scaling trap.

### Redis and Redis-cache (coordination vs cache isolation)
You have two Redis instances: one for runtime coordination/queues/rate limiting/token revocation, and a second for cache isolation/eviction control. That’s good, but it doubles configuration surfaces.

**Symptoms**
Rate limiting behaves bizarrely, tokens don’t revoke, jobs never run, cache returns stale results, or eviction spikes cause read storms.

**Root causes**
- Keys accidentally written to the wrong instance (coordination keys into cache or vice versa).
- TTL misconfiguration: critical coordination data expiring prematurely.
- Eviction policy on cache instance purging keys needed for correct behavior.
- Hot key amplification (same key hammered by many sessions).

**Debug flow**
- Verify which Redis client points to which instance in your backend config.
- Sample keys by prefix (you should standardize key prefixes by subsystem).
- Monitor memory usage and eviction counters separately for Redis vs Redis-cache.

**Mitigations**
- Enforce strict key namespaces and add runtime assertions: “coordination keys must never hit redis-cache”.
- If eviction is causing load, increase TTL jitter and add request coalescing.

### Qdrant (vector memory/search artifacts)
Vector issues often look like “the agent is getting dumber” rather than a clean error.

**Symptoms**
Retrieval returns empty results, irrelevant results spike, performance regresses, or collection not found errors appear.

**Likely causes**
- Collection name mismatch between environments.
- Embedding dimensionality mismatch (new embedding model, old collection schema).
- Inconsistent upserts (writes failing silently while reads still work).
- Background compaction/optimization load spikes.

**Debug flow**
- Confirm the target collection exists and has points.
- Confirm points have the expected vector size and payload schema.
- Correlate retrieval failures with recent deploys that changed embedding models or sentence-transformers versions.

**Mitigations**
- Version your collections (e.g., `memory_v1`, `memory_v2`) and migrate rather than mutate in place.
- Add a fallback path: if Qdrant is unhealthy, degrade to BM25 (`rank-bm25`) or recent-message context only.

### MinIO (files, screenshots, presigned URLs)
MinIO-related bugs frequently present as frontend failures (“download doesn’t work”) even though the issue is clock drift, wrong host, or signature mismatch.

**Symptoms**
403/SignatureDoesNotMatch, presigned URL works in backend but not in browser, uploads succeed but downloads fail, or objects “vanish”.

**Likely causes**
- Presigned URL generated with an internal hostname that the browser can’t resolve.
- Time skew between services (presigned URLs are time-sensitive).
- Bucket policy/permissions differ between environments.
- CORS misconfiguration for browser direct access.

**Debug flow**
- Test presigned URL from:
  - backend container
  - frontend container (or an environment that mirrors browser network)
  - real browser
- Compare the host in the URL with what the browser can reach.
- Check CORS headers and whether the browser is blocking the response.

**Mitigations**
- Avoid minting browser-facing presigned URLs with internal Docker hostnames.
- Centralize MinIO URL construction so it is environment-aware (internal vs external base URL).

## Prevention, quality gates, and postmortems

### Create a “bug intake template” that matches how Pythinker fails
A good bug ticket for this stack should always include:

- Exact time range and timezone
- `session_id` and user ID (or anonymized)
- Frontend evidence: SSE request payload + last events received; WebSocket handshake status + frames screenshot
- Backend evidence: log snippet for that session ID, plus any tool orchestration logs
- Sandbox evidence (if involved): whether the session’s sandbox was running, and whether supervisor processes were healthy
- Data plane evidence: Mongo read/write error text, Redis key/TTL anomalies, Qdrant collection stats, MinIO presign errors

This prevents the “three teams guessing” loop.

### Add lightweight, targeted smoke tests that cover the real boundaries
Given your CI already runs ESLint/type-check/Vitest and Ruff/Pytest/pip-audit, the missing layer in many agent platforms is **boundary smoke tests**:

- SSE smoke test: open a stream, ensure heartbeat events arrive, then force reconnect and confirm idempotency behavior.
- WebSocket smoke test: connect to the three takeover routes and verify data flow (even if it’s dummy frames).
- Sandbox smoke test: spawn a sandbox, run a minimal Python tool, a minimal Node tool, and a minimal Playwright navigation.
- Storage smoke test: Mongo CRUD, Redis coordination key set/get with TTL, Qdrant collection insert/search, MinIO put/get with presign.

These tests should run in a docker-compose CI job so they test the same networking/proxy surfaces as production-like deployments.

### Treat “streaming regression” as a first-class release risk
Streaming is brittle under proxies, compression, worker restarts, and transient packet loss. Put explicit guardrails in place:

- A canary session that continuously exercises SSE + takeover and reports if heartbeats stop.
- Rate-limit and backpressure controls so that one noisy session cannot starve the backend event loop or Redis.
- A documented “degrade mode” switch: disable takeover, reduce tool concurrency, or fall back from streaming to non-streaming responses.

### Postmortem format that produces real fixes
When you run a postmortem, force specificity:

- **Customer impact**: how many sessions/users, and which features.
- **Trigger**: deploy, traffic spike, upstream outage, data growth, expired credential.
- **First failure**: which plane failed first (client/control/execution/data).
- **Detection gap**: why you didn’t notice sooner (missing metric, missing log correlation, missing alert).
- **Fix forward**: code/config changes.
- **Fix systemic**: add tests, add guardrails, add observability, reduce coupling.

The outcome should be a PR that updates both code and this playbook (your maintenance rule already requires keeping the playbook updated when stack/protocol/runtime changes).
