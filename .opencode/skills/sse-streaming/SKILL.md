---
name: sse-streaming
description: Server-Sent Events streaming patterns — event types, reconnection, heartbeat, Redis stream queues, frontend SSE composable
---

# SSE Streaming Skill

## When to Use
When working with real-time event streaming between backend and frontend.

## Architecture

### Backend → Frontend Flow
```
Agent Execution → Event Emission → Redis Stream → SSE Endpoint → Frontend useSSE
```

### Event Types
- `ProgressEvent` — Phase transitions, heartbeats, status updates
- `ToolEvent` — Tool execution start/complete with results
- `ReportEvent` — Final report content delivery
- `DoneEvent` — Session completion signal
- `ErrorEvent` — Error propagation

### SSE Best Practices
- Include `id:` field for reconnect support
- Include `retry:` for browser reconnect interval
- 30s heartbeat prevents proxy timeouts
- Content-Type: `text/event-stream`

### Reconnection
- Redis liveness key: `task:liveness:{session_id}` (10s heartbeat, 30s TTL)
- Carries `task_id` for cross-worker reconnect
- `RedisStreamQueue(f"task:output:{task_id}")` for stream access

### Frontend Composable
```typescript
const { connect, disconnect, events } = useSSE(sessionId)
```

### Coalescing Buffer
- `ResponseGenerator` buffers streaming tokens
- `_coalesce_pending` tracks unflushed content for error recovery
- Salvages partial content on stream interruption

## Key Files
- `backend/app/interfaces/api/routes/session_routes.py` — SSE endpoint
- `backend/app/infrastructure/adapters/redis_task.py` — Redis stream queue
- `frontend/src/composables/useSSE.ts` — SSE client composable
- `backend/app/domain/services/agents/execution.py` — Event emission
