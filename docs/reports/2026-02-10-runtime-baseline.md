# Runtime Stability Baseline (2026-02-10)

## Data Sources

- Backend log: `/tmp/backend_2h.log` (`21827` lines)
- Stack log: `/tmp/stack_2h.log` (`91144` lines)
- Window: last 2 hours from capture time on 2026-02-10

## Error Signature Counts (Backend)

Pattern set:

- `WebSocket error: Session has no sandbox environment`
- `ASGI callable returned without completing response`
- `tool_failed: browser_navigate`
- `xread error`
- `Invalid stream ID`
- `Strategy _try_direct_parse failed`
- `Incomplete tool sequence detected`
- `Context ([0-9]+ tokens) exceeds limit`

Total matched events: `258`

Breakdown:

- `Strategy _try_direct_parse failed`: `76`
- `Incomplete tool sequence detected`: `61`
- `Context (...) exceeds limit`: `51`
- `xread error`: `42`
- `Invalid stream ID`: `40`
- `ASGI callable returned without completing response`: `21`
- `WebSocket error: Session has no sandbox environment`: `5`
- `tool_failed: browser_navigate`: `2`

## Top 20 Slowest Endpoints (Backend)

Sorted by response time (ms), extracted from request completion lines:

1. `457512.26` - `POST /api/v1/sessions`
2. `405235.07` - `POST /api/v1/sessions`
3. `361530.04` - `POST /api/v1/sessions/38a176cf23db4c19/chat`
4. `357681.75` - `POST /api/v1/sessions`
5. `291687.90` - `POST /api/v1/sessions`
6. `289407.02` - `POST /api/v1/sessions/0aeceb1c3cf64bab/chat`
7. `215759.37` - `POST /api/v1/sessions`
8. `211783.84` - `POST /api/v1/sessions`
9. `193544.20` - `POST /api/v1/sessions/34835642f6c14c73/chat`
10. `189811.70` - `POST /api/v1/sessions`
11. `189215.88` - `POST /api/v1/sessions`
12. `182224.58` - `POST /api/v1/sessions/66aef707542143d9/chat`
13. `166980.26` - `POST /api/v1/sessions/a3706d19c78b4357/chat`
14. `160249.23` - `POST /api/v1/sessions`
15. `139782.80` - `POST /api/v1/sessions`
16. `131835.77` - `POST /api/v1/sessions`
17. `125719.76` - `POST /api/v1/sessions/72f48924f09547f1/chat`
18. `120017.45` - `POST /api/v1/sessions/43fb6b34f5614b3c/chat`
19. `120016.06` - `POST /api/v1/sessions/e58c570295c0477f/chat`
20. `120015.17` - `POST /api/v1/sessions/f8fb42faa36d47a0/chat`

## Baseline Observations

- P0 transport/runtime faults are present and non-trivial (`ASGI incomplete response`, `no sandbox WebSocket`, Redis read path faults).
- Message/tool integrity failures (`Incomplete tool sequence`, parser failures, token overflow context warnings) are high-frequency.
- Latency outliers are severe, especially `POST /api/v1/sessions` and session chat calls with multi-minute durations.
