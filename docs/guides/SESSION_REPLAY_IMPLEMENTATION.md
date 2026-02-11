# Session Replay Implementation Guide

> **Quick Start**: Get session replay working in 15 minutes
> **Tech Stack**: rrweb + MongoDB + Vue 3 + FastAPI

---

## Installation

### Frontend

```bash
cd frontend
bun add rrweb rrweb-player
```

**Package sizes:**
- `rrweb`: ~82KB (gzipped: ~28KB)
- `rrweb-player`: ~35KB (gzipped: ~12KB)
- **Total overhead**: ~40KB gzipped

### Backend

No additional packages needed! Uses existing MongoDB and FastAPI.

---

## Quick Implementation (MVP)

### Step 1: Create Session Replay Composable (5 min)

```typescript
// frontend/src/composables/useSessionReplay.ts
import { ref } from 'vue'
import { record, pack } from 'rrweb'
import type { eventWithTime } from 'rrweb'

const isRecording = ref(false)
const sessionId = ref<string | null>(null)
let stopFn: (() => void) | null = null
let eventBuffer: eventWithTime[] = []

export function useSessionReplay() {
  /**
   * Start recording DOM and user interactions
   */
  const startRecording = (pythinkerSessionId: string) => {
    sessionId.value = pythinkerSessionId
    isRecording.value = true

    stopFn = record({
      emit(event) {
        eventBuffer.push(event)

        // Send batch every 50 events (~10 seconds)
        if (eventBuffer.length >= 50) {
          sendBatch()
        }
      },

      // Optimize performance
      sampling: {
        scroll: 150,  // Throttle scroll events to 150ms
        input: 'all'  // Capture all input changes
      },

      // Privacy
      blockClass: 'rr-block',
      maskTextClass: 'rr-mask'
    })

    console.info('[SessionReplay] Started:', pythinkerSessionId)
  }

  /**
   * Stop recording
   */
  const stopRecording = () => {
    stopFn?.()
    stopFn = null
    isRecording.value = false

    // Flush remaining events
    if (eventBuffer.length > 0) {
      sendBatch()
    }
  }

  /**
   * Send events to backend
   */
  const sendBatch = async () => {
    if (!sessionId.value || eventBuffer.length === 0) return

    const events = eventBuffer.splice(0, eventBuffer.length)

    try {
      await fetch(`/api/sessions/${sessionId.value}/replay/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events })
      })
    } catch (error) {
      console.error('[SessionReplay] Send failed:', error)
      // Re-add to buffer for retry
      eventBuffer.unshift(...events)
    }
  }

  return {
    isRecording,
    startRecording,
    stopRecording
  }
}
```

---

### Step 2: Integrate in ChatPage (3 min)

```typescript
// frontend/src/pages/ChatPage.vue
import { useSessionReplay } from '@/composables/useSessionReplay'

const { startRecording, stopRecording } = useSessionReplay()

onMounted(() => {
  if (sessionId.value) {
    startRecording(sessionId.value)
  }
})

onBeforeUnmount(() => {
  stopRecording()
})
```

---

### Step 3: Backend - MongoDB Model (2 min)

```python
# backend/app/domain/models/session_replay.py
from datetime import datetime
from pydantic import BaseModel, Field

class SessionReplay(BaseModel):
    """Session replay data model"""
    session_id: str
    rrweb_events: list[dict] = Field(default_factory=list)
    total_events: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

---

### Step 4: Backend - Repository (5 min)

```python
# backend/app/infrastructure/persistence/mongodb/session_replay_repository.py
from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime

class MongoSessionReplayRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self._collection = collection

    async def append_events(
        self,
        session_id: str,
        events: list[dict]
    ) -> None:
        """Append events using MongoDB $push"""
        await self._collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"rrweb_events": {"$each": events}},
                "$inc": {"total_events": len(events)},
                "$set": {"updated_at": datetime.now()}
            },
            upsert=True
        )

    async def get_replay(self, session_id: str) -> dict | None:
        """Get full replay data"""
        return await self._collection.find_one({"session_id": session_id})
```

---

### Step 5: Backend - API Endpoint (3 min)

```python
# backend/app/interfaces/api/sessions/replay.py
from fastapi import APIRouter, Depends

router = APIRouter()

@router.post("/sessions/{session_id}/replay/events")
async def append_events(
    session_id: str,
    payload: dict,
    repo = Depends(get_replay_repository)
):
    """Receive rrweb events from frontend"""
    events = payload.get("events", [])
    await repo.append_events(session_id, events)

    return {"status": "ok", "events_received": len(events)}

@router.get("/sessions/{session_id}/replay")
async def get_replay(
    session_id: str,
    repo = Depends(get_replay_repository)
):
    """Get replay data for playback"""
    replay = await repo.get_replay(session_id)

    if not replay:
        raise HTTPException(status_code=404)

    return {
        "events": replay["rrweb_events"],
        "total_events": replay["total_events"]
    }
```

---

### Step 6: Replay Player Component (7 min)

```vue
<!-- frontend/src/components/SessionReplayPlayer.vue -->
<template>
  <div class="replay-player">
    <div class="controls">
      <button @click="togglePlay">
        {{ isPlaying ? 'Pause' : 'Play' }}
      </button>
      <span>{{ currentTime }}ms / {{ duration }}ms</span>
    </div>

    <div ref="replayTarget" class="replay-container"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Replayer } from 'rrweb'

interface Props {
  sessionId: string
}

const props = defineProps<Props>()

const replayTarget = ref<HTMLElement | null>(null)
const replayer = ref<Replayer | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)

onMounted(async () => {
  // Load replay data
  const response = await fetch(`/api/sessions/${props.sessionId}/replay`)
  const data = await response.json()

  // Initialize rrweb player
  if (replayTarget.value) {
    replayer.value = new Replayer(data.events, {
      root: replayTarget.value,
      speed: 1
    })

    duration.value = data.events[data.events.length - 1]?.timestamp || 0

    // Listen to time updates
    replayer.value.on('ui-update-current-time', (event) => {
      currentTime.value = event.payload
    })
  }
})

const togglePlay = () => {
  if (!replayer.value) return

  if (isPlaying.value) {
    replayer.value.pause()
  } else {
    replayer.value.play()
  }

  isPlaying.value = !isPlaying.value
}
</script>

<style scoped>
.replay-container {
  width: 100%;
  height: 600px;
  border: 1px solid #ccc;
  overflow: auto;
}
</style>
```

---

## 🎯 **That's it!** You now have working session replay.

**Test it:**
1. Start a chat session
2. Interact with the UI (click, type, scroll)
3. Open MongoDB and check `session_replays` collection
4. Navigate to `/sessions/{id}/replay` to watch the playback

---

## Advanced Features

### 1. Agent Timeline Markers

#### Track Agent Events

```typescript
// frontend/src/composables/useSessionReplay.ts (add this method)
export function useSessionReplay() {
  // ... existing code ...

  /**
   * Track agent events (tool executions, LLM calls)
   */
  const trackAgentEvent = (event: {
    type: 'tool' | 'llm' | 'file' | 'error'
    name: string
    metadata?: Record<string, unknown>
  }) => {
    if (!sessionId.value) return

    fetch(`/api/sessions/${sessionId.value}/replay/agent-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...event,
        timestamp: Date.now()
      })
    })
  }

  return {
    isRecording,
    startRecording,
    stopRecording,
    trackAgentEvent  // Export new method
  }
}
```

#### Call from Agent Events

```typescript
// frontend/src/composables/useAgentEvents.ts
import { useSessionReplay } from './useSessionReplay'

const { trackAgentEvent } = useSessionReplay()

// When agent starts a tool
watch(() => latestEvent.value, (event) => {
  if (event?.type === 'tool_start') {
    trackAgentEvent({
      type: 'tool',
      name: event.tool_name,
      metadata: {
        tool: event.tool_name,
        arguments: event.arguments
      }
    })
  }

  if (event?.type === 'error') {
    trackAgentEvent({
      type: 'error',
      name: event.message,
      metadata: event
    })
  }
})
```

#### Backend - Store Agent Events

```python
# backend/app/domain/models/session_replay.py
class AgentEvent(BaseModel):
    timestamp: int  # Unix ms
    type: Literal['tool', 'llm', 'file', 'error']
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class SessionReplay(BaseModel):
    session_id: str
    rrweb_events: list[dict] = Field(default_factory=list)
    agent_timeline: list[AgentEvent] = Field(default_factory=list)  # NEW
    # ... rest
```

```python
# backend/app/infrastructure/persistence/mongodb/session_replay_repository.py
async def add_agent_event(
    self,
    session_id: str,
    event: AgentEvent
) -> None:
    """Add agent event to timeline"""
    await self._collection.update_one(
        {"session_id": session_id},
        {
            "$push": {"agent_timeline": event.model_dump()},
            "$set": {"updated_at": datetime.now()}
        },
        upsert=True
    )
```

---

### 2. Timeline Scrubber with Markers

```vue
<!-- frontend/src/components/ReplayTimeline.vue -->
<template>
  <div class="timeline">
    <!-- Scrubber bar -->
    <input
      type="range"
      :value="currentTime"
      :max="duration"
      @input="seek"
      class="scrubber"
    />

    <!-- Event markers -->
    <div
      v-for="event in agentEvents"
      :key="event.timestamp"
      class="marker"
      :class="`marker-${event.type}`"
      :style="{ left: `${(event.timestamp / duration) * 100}%` }"
      @click="seekToEvent(event)"
    >
      <div class="marker-dot"></div>
      <div class="marker-label">{{ event.name }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Props {
  currentTime: number
  duration: number
  agentEvents: Array<{
    timestamp: number
    type: string
    name: string
  }>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  seek: [time: number]
}>()

const seek = (e: Event) => {
  const target = e.target as HTMLInputElement
  emit('seek', parseInt(target.value))
}

const seekToEvent = (event: any) => {
  emit('seek', event.timestamp)
}
</script>

<style scoped>
.timeline {
  position: relative;
  padding: 20px 0;
}

.scrubber {
  width: 100%;
  height: 8px;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 4px;
  appearance: none;
}

.marker {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  cursor: pointer;
}

.marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: -20px;
  margin-left: -4px;
}

/* Event type colors */
.marker-tool .marker-dot {
  background: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

.marker-llm .marker-dot {
  background: #8b5cf6;
  box-shadow: 0 0 8px rgba(139, 92, 246, 0.6);
}

.marker-error .marker-dot {
  background: #ef4444;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
}

.marker-label {
  position: absolute;
  top: -30px;
  left: 50%;
  transform: translateX(-50%);
  background: #2a2a2a;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.marker:hover .marker-label {
  opacity: 1;
}
</style>
```

---

### 3. Compression (Reduce Payload by 70%)

#### Frontend

```typescript
// frontend/src/composables/useSessionReplay.ts
import { pack } from 'rrweb'

const sendBatch = async () => {
  if (!sessionId.value || eventBuffer.length === 0) return

  const events = eventBuffer.splice(0, eventBuffer.length)

  // Compress using rrweb's pack()
  const compressed = pack(events)

  try {
    await fetch(`/api/sessions/${sessionId.value}/replay/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        events: compressed,
        compressed: true  // Flag for backend
      })
    })
  } catch (error) {
    console.error('[SessionReplay] Send failed:', error)
  }
}
```

#### Backend

```python
# backend/app/interfaces/api/sessions/replay.py
@router.post("/sessions/{session_id}/replay/events")
async def append_events(
    session_id: str,
    payload: dict,
    repo = Depends(get_replay_repository)
):
    events = payload.get("events", [])
    compressed = payload.get("compressed", False)

    if compressed:
        # Store as-is (already packed)
        # Frontend will unpack during playback
        pass

    await repo.append_events(session_id, events, compressed)

    return {"status": "ok"}
```

---

### 4. Privacy Controls

#### Block Sensitive Elements

```html
<!-- Don't record password inputs -->
<div class="rr-block">
  <input type="password" placeholder="Enter password" />
</div>

<!-- Mask text content -->
<div class="rr-mask">
  API Key: sk-1234567890
  <!-- Will appear as: *** -->
</div>

<!-- Ignore from recording -->
<div class="rr-ignore">
  <p>Admin-only content</p>
</div>
```

#### Auto-mask Inputs

```typescript
// frontend/src/composables/useSessionReplay.ts
stopFn = record({
  // ... other config ...

  // Automatically mask all inputs
  maskAllInputs: true,

  // Except these (allow recording)
  unmaskInputOptions: {
    password: false,  // Never record passwords
    email: false,     // Never record emails
    text: true        // Allow text inputs
  }
})
```

---

### 5. Performance Optimization

#### Throttle Events

```typescript
stopFn = record({
  sampling: {
    // Mouse movements: sample every 50ms
    mousemove: 50,

    // Scroll: sample every 150ms
    scroll: 150,

    // Input: capture all changes
    input: 'all',

    // Media (audio/video): sample every 800ms
    media: 800
  }
})
```

#### Skip Inactive Periods

```typescript
// During playback
const replayer = new Replayer(events, {
  root: replayTarget.value,
  skipInactive: true,  // Skip periods with no activity
  speed: 1
})
```

---

### 6. Multi-Tab Support

#### Track Tab Changes

```typescript
// frontend/src/composables/useSessionReplay.ts
export function useSessionReplay() {
  // ... existing code ...

  const trackTabChange = (tabName: string) => {
    if (!sessionId.value) return

    trackAgentEvent({
      type: 'navigation',
      name: `Tab: ${tabName}`,
      metadata: { tab: tabName }
    })
  }

  return {
    // ... existing exports ...
    trackTabChange
  }
}
```

#### Call on Tab Switch

```typescript
// frontend/src/components/TabPanel.vue
import { useSessionReplay } from '@/composables/useSessionReplay'

const { trackTabChange } = useSessionReplay()

watch(() => activeTab.value, (newTab) => {
  trackTabChange(newTab)
})
```

---

### 7. Error Tracking Integration

```typescript
// frontend/src/composables/useSessionReplay.ts
export function useSessionReplay() {
  // ... existing code ...

  const trackError = (error: Error) => {
    trackAgentEvent({
      type: 'error',
      name: error.message,
      metadata: {
        stack: error.stack,
        timestamp: Date.now()
      }
    })
  }

  return {
    // ... existing exports ...
    trackError
  }
}
```

#### Global Error Handler

```typescript
// frontend/src/main.ts
import { useSessionReplay } from './composables/useSessionReplay'

const { trackError } = useSessionReplay()

window.addEventListener('error', (event) => {
  trackError(event.error)
})

window.addEventListener('unhandledrejection', (event) => {
  trackError(new Error(event.reason))
})
```

---

## Production Deployment

### 1. Environment Variables

```bash
# frontend/.env
VITE_SESSION_REPLAY_ENABLED=true
VITE_SESSION_REPLAY_COMPRESSION=true
VITE_SESSION_REPLAY_BATCH_SIZE=50

# backend/.env
SESSION_REPLAY_RETENTION_DAYS=30  # Auto-delete after 30 days
SESSION_REPLAY_MAX_EVENTS=10000   # Max events per session
```

### 2. MongoDB Indexes

```javascript
// Create indexes for performance
db.session_replays.createIndex({ "session_id": 1 }, { unique: true })

// TTL index for automatic cleanup
db.session_replays.createIndex(
  { "created_at": 1 },
  { expireAfterSeconds: 2592000 }  // 30 days
)

// Index for querying by date range
db.session_replays.createIndex({ "created_at": -1 })
```

### 3. Backend Validation

```python
# backend/app/interfaces/api/sessions/replay.py
from pydantic import BaseModel, Field, validator

class ReplayEventsPayload(BaseModel):
    events: list[dict] = Field(..., min_items=1, max_items=100)
    compressed: bool = False

    @validator('events')
    def validate_events(cls, v):
        # Limit event size to prevent abuse
        if len(v) > 100:
            raise ValueError("Max 100 events per batch")
        return v

@router.post("/sessions/{session_id}/replay/events")
async def append_events(
    session_id: str,
    payload: ReplayEventsPayload,  # Validated
    repo = Depends(get_replay_repository)
):
    # Check session exists
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await repo.append_events(session_id, payload.events, payload.compressed)

    return {"status": "ok", "events_received": len(payload.events)}
```

---

## Monitoring

### 1. Prometheus Metrics

```python
# backend/app/application/services/session_replay_service.py
from prometheus_client import Counter, Histogram

events_received = Counter(
    'replay_events_received_total',
    'Total rrweb events received'
)

replay_sessions = Counter(
    'replay_sessions_total',
    'Total replay sessions created'
)

event_batch_size = Histogram(
    'replay_event_batch_size',
    'Size of event batches'
)

class SessionReplayService:
    async def append_events(self, session_id: str, events: list[dict], ...):
        events_received.inc(len(events))
        event_batch_size.observe(len(events))

        await self._repository.append_events(...)
```

### 2. Grafana Dashboard

```yaml
# Metrics to track:
- Replays recorded per hour
- Average events per session
- Storage growth (MB/day)
- Top event types (tool, llm, error)
- Playback requests per hour
```

---

## Troubleshooting

### Issue: Events Not Being Recorded

**Symptom**: Frontend shows recording started, but no events in MongoDB

**Debug:**
```typescript
// frontend/src/composables/useSessionReplay.ts
stopFn = record({
  emit(event) {
    console.log('[rrweb] Event:', event.type)  // Debug log
    eventBuffer.push(event)
  }
})
```

**Common causes:**
- `rr-block` class applied to root element
- MutationObserver blocked by browser extension
- CORS issue (check browser console)

---

### Issue: High Memory Usage

**Symptom**: Browser tab uses >500MB RAM

**Solution:**
```typescript
// Reduce sampling rate
stopFn = record({
  sampling: {
    scroll: 300,     // Increase from 150ms
    mousemove: 100,  // Increase from 50ms
    media: 1600      // Increase from 800ms
  },

  // Disable canvas recording if not needed
  recordCanvas: false
})
```

---

### Issue: Playback Not Working

**Symptom**: Player loads but shows blank screen

**Debug:**
```typescript
// frontend/src/components/SessionReplayPlayer.vue
const replayer = new Replayer(data.events, {
  root: replayTarget.value,
  liveMode: false,
  insertStyleRules: [
    // Add missing styles
    'body { margin: 0; }'
  ]
})

// Check for errors
replayer.on('error', (err) => {
  console.error('[Replayer] Error:', err)
})
```

---

## Migration from Legacy Replay Provider

### Feature Flag Approach

```typescript
// frontend/src/composables/useSessionReplay.ts
const USE_LEGACY_REPLAY = import.meta.env.VITE_USE_LEGACY_REPLAY === 'true'

export function useSessionReplay() {
  if (USE_LEGACY_REPLAY) {
    // Use existing legacy replay composable
    return useLegacyReplayTracker()
  } else {
    // Use new rrweb implementation
    return useRRWebRecorder()
  }
}
```

### Data Migration Script

```python
# scripts/migrate_legacy_replay_to_rrweb.py
"""
Migrate legacy replay session data to rrweb format
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def migrate():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["pythinker"]

    # Get all sessions with legacy replay data
    sessions = await db.sessions.find({
        "legacy_replay_session_id": {"$exists": True}
    }).to_list(None)

    for session in sessions:
        # Convert legacy replay format to rrweb format
        # (Implementation depends on legacy replay data structure)
        rrweb_events = convert_legacy_replay_to_rrweb(session)

        # Insert into session_replays collection
        await db.session_replays.insert_one({
            "session_id": session["_id"],
            "rrweb_events": rrweb_events,
            "migrated_from": "legacy_replay",
            "created_at": session["created_at"]
        })

    print(f"Migrated {len(sessions)} sessions")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## Resources

### Official Documentation
- **rrweb GitHub**: https://github.com/rrweb-io/rrweb
- **rrweb Guide**: https://github.com/rrweb-io/rrweb/blob/master/guide.md
- **API Reference**: https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/index.md

### Live Examples
- **rrweb Demo**: https://www.rrweb.io/
- **Playground**: https://rrweb.io/demo/checkout-form

### Community
- **Discord**: https://discord.gg/rrweb
- **Issues**: https://github.com/rrweb-io/rrweb/issues

---

## FAQ

**Q: How much storage does session replay use?**
A: ~500KB per 10-minute session (uncompressed). With compression: ~150KB.

**Q: Does rrweb work on mobile?**
A: Yes, rrweb supports mobile browsers (iOS Safari, Chrome Android).

**Q: Can I replay sessions across different browsers?**
A: Yes, replays are browser-agnostic.

**Q: Does it record iframes?**
A: No by default. Set `captureIFrames: true` to enable (increases overhead).

**Q: GDPR compliance?**
A: Use `maskAllInputs: true` and `blockClass` for sensitive data. Implement deletion endpoint.

**Q: Can I export sessions as video?**
A: Not directly. Use Puppeteer to record the replay player as video.

---

## Next Steps

1. **Try the MVP** (15 min)
   - Install rrweb
   - Implement basic recording
   - Test playback

2. **Add Timeline** (30 min)
   - Track agent events
   - Build scrubber UI
   - Add event markers

3. **Production Ready** (2 hours)
   - Compression
   - Privacy controls
   - Monitoring
   - Testing

4. **Advanced Features** (1 day)
   - Multi-tab support
   - Error tracking
   - Export functionality
   - Custom analytics

---

**Ready to implement?** Start with the MVP and iterate based on user feedback!
