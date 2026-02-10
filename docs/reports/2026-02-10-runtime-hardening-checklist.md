# Runtime Hardening Checklist (2026-02-10)

## Config

- [x] Security warnings are deduplicated per process to reduce log noise.
- [x] Startup banner logs `environment`, `auth_provider`, and `llm_provider` once.
- [x] `AUTH_PROVIDER=none` remains explicitly warned (development-only).

## Redis / Queue Runtime

- [x] Redis container uses explicit runtime flags (`appendonly no`, `save ""`, `loglevel warning`, `timeout 0`).
- [x] Redis container healthcheck (`redis-cli ping`) is enabled in development compose.
- [x] Backend xread cursor normalization and invalid-ID warning dedup are in place (Task 2).

## Transport / Session Runtime

- [x] VNC websocket no-sandbox path closes with policy violation (`1008`) and stable reason.
- [x] Missing sandbox in VNC URL resolution maps to `NotFoundError`.
- [x] Exception handler maps 404 app errors without warning/error-level log pollution.

## Browser Runtime

- [x] Browser crash signatures include `Target crashed`.
- [x] Connection pool force-release is cooldown-limited per CDP URL to prevent warning spam loops.

## LLM / Message Integrity

- [x] Tool-sequence normalization drops mismatched tool responses while pending IDs exist.
- [x] JSON parser strategy warnings are deduplicated to avoid repeated warning storms.
- [x] Token compaction logs preserve_recent reduction once per compaction cycle.

## Latency Guardrails

- [x] Session warm-up wait is clamped to a bounded max budget.
- [x] Chat stream emits controlled timeout error event instead of hanging indefinitely.
- [x] Create/chat paths emit timing logs for operational visibility.

## Monitoring

- [x] `MONITORING.md` includes runtime log signatures:
  - `vnc_ws_rejected_no_sandbox`
  - `asgi_incomplete_response`
  - `redis_xread_invalid_id`
  - `browser_cdp_init_retry_exhausted`
