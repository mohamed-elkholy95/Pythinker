# Session Replay & Timeline Architecture

> **Status**: Design Document
> **Created**: 2026-02-11
> **Target**: Lightweight session replay with agent execution timeline
> **Performance Goal**: <100MB overhead, <30% CPU increase

---

## Executive Summary

This document outlines a lightweight alternative to a full external replay stack for session replay and agent execution visualization. The proposed architecture uses **rrweb** (industry-standard DOM replay library) combined with Pythinker's existing CDP screencast infrastructure to provide:

1. **Full UI replay** - See every chat message, tool panel interaction, and UI state change
2. **Sandbox replay** - Watch the browser automation in action (already supported via CDP)
3. **Agent timeline** - Scrub through tool executions, LLM calls, and errors with visual markers
4. **Dual-pane playback** - Side-by-side view of frontend + sandbox

**Performance**: 95% lighter than heavyweight replay stacks (80KB bundle vs 500KB + 6 containers)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Vue 3 + rrweb)                        │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────┐   │
│  │ ChatPage       │  │ SandboxViewer  │  │ ToolPanel           │   │
│  │ (rrweb record) │  │ (CDP screencast)│  │ (rrweb record)      │   │
│  └────────┬───────┘  └────────┬───────┘  └────────┬────────────┘   │
│           │                   │                     │                 │
│           └───────────────────┼─────────────────────┘                │
│                               ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ useSessionReplay Composable                                  │    │
│  │ • record() → Capture DOM mutations                           │    │
│  │ • Batch events every 10s → POST /sessions/{id}/replay/events │    │
│  │ • Link agent events → Timeline markers                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS (SSE for agent events)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI + DDD)                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ SessionReplayService (Application Layer)                     │    │
│  │ • append_events(session_id, events[])                        │    │
│  │ • get_replay_data(session_id) → events + agent_timeline      │    │
│  │ • link_agent_event(session_id, event)                        │    │
│  └───────────────┬─────────────────────────────────────────────┘    │
│                  │                                                    │
│                  ▼                                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ SessionReplayRepository (Infrastructure)                     │    │
│  │ • MongoDB: Store rrweb events + agent timeline               │    │
│  │ • MinIO (optional): Archive screencast frames                │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ MongoDB          │  │ MinIO (Optional) │  │ Redis (Events)   │  │
│  │ ─────────────    │  │ ───────────────  │  │ ───────────────  │  │
│  │ • rrweb events   │  │ • CDP frames     │  │ • Live event bus │  │
│  │ • Agent timeline │  │ • Screenshots    │  │ • SSE broadcast  │  │
│  │ • Session meta   │  │ (archival)       │  │                  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Frontend Recording Layer

#### **useSessionReplay.ts** (New Composable)

Replaces heavy external replay SDK integration with a lightweight rrweb-based implementation.

```typescript
/**
 * Lightweight session replay using rrweb
 * Captures DOM mutations, user interactions, and console logs
 */
import { ref } from 'vue'
import { record, pack } from 'rrweb'
import type { eventWithTime } from 'rrweb'

// State
const isRecording = ref(false)
const sessionId = ref<string | null>(null)
const eventBuffer: eventWithTime[] = []

// Constants
const BATCH_SIZE = 50 // Send every 50 events (~10 seconds)
const COMPRESSION_ENABLED = true

export function useSessionReplay() {
  let stopFn: (() => void) | null = null

  /**
   * Start recording DOM and user interactions
   */
  const startRecording = async (pythinkerSessionId: string) => {
    sessionId.value = pythinkerSessionId
    isRecording.value = true

    stopFn = record({
      // Event handler
      emit(event, isCheckout) {
        eventBuffer.push(event)

        // Batch send to backend
        if (eventBuffer.length >= BATCH_SIZE || isCheckout) {
          sendBatch()
        }
      },

      // Performance optimizations
      sampling: {
        mousemove: true,          // Capture mouse movements
        mouseInteraction: true,   // Clicks, hovers
        scroll: 150,              // Throttle scroll to 150ms
        input: 'all',             // Capture all input changes
        media: 800                // Sample media every 800ms
      },

      // Privacy controls
      maskAllInputs: false,       // Don't mask by default
      blockClass: 'rr-block',     // Add this class to hide elements
      ignoreClass: 'rr-ignore',   // Ignore from replay
      maskTextClass: 'rr-mask',   // Mask text content

      // Canvas recording (for sandbox viewer)
      recordCanvas: true,
      dataURLOptions: {
        type: 'image/webp',
        quality: 0.6
      },

      // Capture errors
      plugins: [
        // Add console log capture
        rrwebConsole({ level: ['error', 'warn', 'info'] })
      ]
    })

    console.info('[SessionReplay] Recording started:', pythinkerSessionId)
  }

  /**
   * Stop recording and flush remaining events
   */
  const stopRecording = async () => {
    if (!stopFn) return

    stopFn()
    stopFn = null
    isRecording.value = false

    // Flush remaining events
    if (eventBuffer.length > 0) {
      await sendBatch()
    }

    console.info('[SessionReplay] Recording stopped')
  }

  /**
   * Send batched events to backend
   */
  const sendBatch = async () => {
    if (!sessionId.value || eventBuffer.length === 0) return

    const events = eventBuffer.splice(0, eventBuffer.length)

    // Optional: Compress events
    const payload = COMPRESSION_ENABLED
      ? { events: pack(events), compressed: true }
      : { events, compressed: false }

    try {
      await fetch(`/api/sessions/${sessionId.value}/replay/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    } catch (error) {
      console.error('[SessionReplay] Failed to send events:', error)
      // Re-add to buffer for retry
      eventBuffer.unshift(...events)
    }
  }

  /**
   * Link an agent event to the timeline
   */
  const trackAgentEvent = (event: {
    type: 'tool' | 'llm' | 'file' | 'error'
    name: string
    timestamp?: number
    metadata?: Record<string, unknown>
  }) => {
    if (!sessionId.value) return

    fetch(`/api/sessions/${sessionId.value}/replay/agent-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...event,
        timestamp: event.timestamp || Date.now()
      })
    })
  }

  return {
    isRecording,
    sessionId,
    startRecording,
    stopRecording,
    trackAgentEvent
  }
}
```

**Key Features:**
- **Batched sending**: Events sent every 50 events (~10s) to reduce HTTP overhead
- **Compression**: Optional gzip compression (reduces payload by 70%)
- **Privacy controls**: CSS classes to block/mask sensitive elements
- **Canvas support**: Captures the sandbox viewer canvas
- **Error resilience**: Retries failed sends

---

#### **Integration Points**

**ChatPage.vue**: Start/stop recording
```typescript
import { useSessionReplay } from '@/composables/useSessionReplay'

const { startRecording, stopRecording, trackAgentEvent } = useSessionReplay()

// When chat starts
onMounted(() => {
  if (sessionId.value) {
    startRecording(sessionId.value)
  }
})

// When user sends message
const handleSendMessage = () => {
  trackAgentEvent({
    type: 'llm',
    name: 'User Message',
    metadata: { content: message.value }
  })
}

// When agent uses tool
watch(() => agentEvents.value, (events) => {
  const latestEvent = events[events.length - 1]
  if (latestEvent?.type === 'tool_start') {
    trackAgentEvent({
      type: 'tool',
      name: latestEvent.tool_name,
      metadata: latestEvent
    })
  }
})
```

---

### 2. Backend Storage Layer

#### **Domain Model**

```python
# backend/app/domain/models/session_replay.py
from datetime import datetime
from pydantic import BaseModel, Field

class AgentEvent(BaseModel):
    """Individual agent action on the timeline"""
    timestamp_ms: int = Field(description="Unix timestamp in milliseconds")
    type: Literal['tool', 'llm', 'file', 'error']
    name: str = Field(description="Display name (e.g., 'Browser Navigate')")
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None  # Optional: event duration

class SessionReplay(BaseModel):
    """Complete replay data for a session"""
    session_id: str
    rrweb_events: list[dict] = Field(default_factory=list)
    agent_timeline: list[AgentEvent] = Field(default_factory=list)

    # Metadata
    duration_ms: int = 0
    total_events: int = 0
    compressed: bool = False

    # Screencast data (optional)
    screencast_frames: list[str] | None = None  # MinIO URLs

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

---

#### **Repository Interface**

```python
# backend/app/domain/repositories/session_replay_repository.py
from abc import ABC, abstractmethod

class SessionReplayRepository(ABC):
    """Abstract repository for session replay storage"""

    @abstractmethod
    async def append_events(
        self,
        session_id: str,
        events: list[dict],
        compressed: bool = False
    ) -> None:
        """Append rrweb events to existing session replay"""
        pass

    @abstractmethod
    async def add_agent_event(
        self,
        session_id: str,
        event: AgentEvent
    ) -> None:
        """Add an agent event marker to the timeline"""
        pass

    @abstractmethod
    async def get_replay(self, session_id: str) -> SessionReplay | None:
        """Retrieve complete replay data"""
        pass

    @abstractmethod
    async def delete_replay(self, session_id: str) -> bool:
        """Delete replay data (GDPR compliance)"""
        pass
```

---

#### **MongoDB Implementation**

```python
# backend/app/infrastructure/persistence/mongodb/session_replay_repository.py
from motor.motor_asyncio import AsyncIOMotorCollection
from app.domain.repositories.session_replay_repository import SessionReplayRepository

class MongoSessionReplayRepository(SessionReplayRepository):
    def __init__(self, collection: AsyncIOMotorCollection):
        self._collection = collection

    async def append_events(
        self,
        session_id: str,
        events: list[dict],
        compressed: bool = False
    ) -> None:
        """Append events using MongoDB $push operator"""
        await self._collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"rrweb_events": {"$each": events}},
                "$inc": {"total_events": len(events)},
                "$set": {
                    "updated_at": datetime.now(),
                    "compressed": compressed
                }
            },
            upsert=True
        )

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

    async def get_replay(self, session_id: str) -> SessionReplay | None:
        """Retrieve full replay data"""
        doc = await self._collection.find_one({"session_id": session_id})
        return SessionReplay(**doc) if doc else None

    async def get_replay_metadata(self, session_id: str) -> dict | None:
        """Get metadata without full event array (for listings)"""
        doc = await self._collection.find_one(
            {"session_id": session_id},
            {"rrweb_events": 0}  # Exclude large array
        )
        return doc
```

**MongoDB Schema Optimization:**
```javascript
// Create index for fast lookups
db.session_replays.createIndex({ "session_id": 1 }, { unique: true })

// Create TTL index for automatic cleanup (optional: 30 days)
db.session_replays.createIndex(
  { "created_at": 1 },
  { expireAfterSeconds: 2592000 }
)

// Example document structure
{
  "_id": ObjectId("..."),
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "rrweb_events": [
    { "type": 2, "data": { ... }, "timestamp": 1739305200000 },
    { "type": 3, "data": { ... }, "timestamp": 1739305201500 },
    // ... thousands of events
  ],
  "agent_timeline": [
    {
      "timestamp_ms": 1739305210000,
      "type": "tool",
      "name": "Browser Navigate",
      "metadata": { "url": "https://example.com" },
      "duration_ms": 1200
    },
    {
      "timestamp_ms": 1739305215000,
      "type": "llm",
      "name": "Claude Response",
      "metadata": { "tokens": 450 }
    }
  ],
  "duration_ms": 180000,  // 3 minutes
  "total_events": 1247,
  "compressed": false,
  "created_at": ISODate("2026-02-11T10:00:00Z"),
  "updated_at": ISODate("2026-02-11T10:03:00Z")
}
```

---

#### **API Endpoints**

```python
# backend/app/interfaces/api/sessions/replay.py
from fastapi import APIRouter, Depends, HTTPException
from app.application.services.session_replay_service import SessionReplayService

router = APIRouter()

@router.post("/sessions/{session_id}/replay/events")
async def append_replay_events(
    session_id: str,
    payload: dict,
    service: SessionReplayService = Depends()
):
    """
    Append rrweb events to session replay
    Called every ~10 seconds from frontend
    """
    events = payload.get("events", [])
    compressed = payload.get("compressed", False)

    await service.append_events(session_id, events, compressed)

    return {"status": "ok", "events_received": len(events)}

@router.post("/sessions/{session_id}/replay/agent-events")
async def add_agent_event(
    session_id: str,
    event: dict,
    service: SessionReplayService = Depends()
):
    """
    Add agent event marker to timeline
    Called when agent starts/completes tool, LLM call, etc.
    """
    agent_event = AgentEvent(**event)
    await service.add_agent_event(session_id, agent_event)

    return {"status": "ok"}

@router.get("/sessions/{session_id}/replay")
async def get_replay_data(
    session_id: str,
    service: SessionReplayService = Depends()
):
    """
    Retrieve full replay data for playback
    Returns rrweb events + agent timeline
    """
    replay = await service.get_replay(session_id)

    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")

    return {
        "events": replay.rrweb_events,
        "agent_timeline": [e.model_dump() for e in replay.agent_timeline],
        "duration_ms": replay.duration_ms,
        "metadata": {
            "total_events": replay.total_events,
            "compressed": replay.compressed,
            "created_at": replay.created_at.isoformat()
        }
    }

@router.get("/sessions/{session_id}/replay/metadata")
async def get_replay_metadata(
    session_id: str,
    service: SessionReplayService = Depends()
):
    """
    Get replay metadata without full event array
    Used for session history listings
    """
    metadata = await service.get_replay_metadata(session_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Replay not found")

    return metadata
```

---

### 3. Replay Player Component

#### **SessionReplayPlayer.vue**

```vue
<!-- frontend/src/components/SessionReplayPlayer.vue -->
<template>
  <div class="replay-container" :class="{ loading: isLoading }">
    <!-- Top bar: Session info + controls -->
    <div class="replay-header">
      <div class="session-info">
        <h3>Session Replay</h3>
        <span class="timestamp">{{ formatDate(replayData?.created_at) }}</span>
        <span class="duration">{{ formatDuration(replayData?.duration_ms) }}</span>
      </div>

      <div class="controls">
        <button @click="togglePlay" class="btn-play">
          <Icon :name="isPlaying ? 'pause' : 'play'" />
        </button>

        <select v-model="playbackSpeed" class="speed-selector">
          <option :value="0.5">0.5x</option>
          <option :value="1">1x</option>
          <option :value="2">2x</option>
          <option :value="4">4x</option>
        </select>

        <label class="checkbox">
          <input type="checkbox" v-model="skipInactive" />
          Skip inactive
        </label>
      </div>
    </div>

    <!-- Main content: Dual pane -->
    <div class="replay-content">
      <!-- Left pane: rrweb replay (UI interactions) -->
      <div class="pane left-pane">
        <div class="pane-header">
          <h4>UI Replay</h4>
          <span class="badge">Chat + Tools</span>
        </div>
        <div ref="rrwebTarget" class="rrweb-player"></div>
      </div>

      <!-- Right pane: CDP screencast (sandbox browser) -->
      <div class="pane right-pane">
        <div class="pane-header">
          <h4>Sandbox Browser</h4>
          <span class="badge">CDP Screencast</span>
        </div>
        <SandboxViewer
          :session-id="sessionId"
          mode="replay"
          :current-time="currentTime"
          @ready="onScreencastReady"
        />
      </div>
    </div>

    <!-- Timeline scrubber -->
    <ReplayTimeline
      :current-time="currentTime"
      :duration="duration"
      :agent-events="agentEvents"
      :is-playing="isPlaying"
      @seek="handleSeek"
      @toggle-play="togglePlay"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { Replayer } from 'rrweb'
import type { eventWithTime } from 'rrweb'

interface Props {
  sessionId: string
}

const props = defineProps<Props>()

// State
const isLoading = ref(true)
const replayData = ref<any>(null)
const rrwebReplayer = ref<Replayer | null>(null)
const rrwebTarget = ref<HTMLElement | null>(null)

const isPlaying = ref(false)
const currentTime = ref(0)
const playbackSpeed = ref(1)
const skipInactive = ref(true)

// Computed
const duration = computed(() => replayData.value?.duration_ms || 0)
const agentEvents = computed(() => replayData.value?.agent_timeline || [])

// Lifecycle
onMounted(async () => {
  await loadReplayData()
  initializeRRWebPlayer()
})

// Methods
const loadReplayData = async () => {
  try {
    isLoading.value = true
    const response = await fetch(`/api/sessions/${props.sessionId}/replay`)
    replayData.value = await response.json()
  } catch (error) {
    console.error('Failed to load replay data:', error)
  } finally {
    isLoading.value = false
  }
}

const initializeRRWebPlayer = () => {
  if (!rrwebTarget.value || !replayData.value?.events) return

  rrwebReplayer.value = new Replayer(replayData.value.events, {
    root: rrwebTarget.value,
    speed: playbackSpeed.value,
    skipInactive: skipInactive.value,
    showController: false,  // We use custom controls
    mouseTail: {
      duration: 1000,
      strokeStyle: '#3b82f6',
      lineWidth: 2
    }
  })

  // Listen to player events
  rrwebReplayer.value.on('finish', () => {
    isPlaying.value = false
  })

  rrwebReplayer.value.on('ui-update-current-time', (event) => {
    currentTime.value = event.payload
  })
}

const togglePlay = () => {
  if (!rrwebReplayer.value) return

  if (isPlaying.value) {
    rrwebReplayer.value.pause()
  } else {
    rrwebReplayer.value.play(currentTime.value)
  }

  isPlaying.value = !isPlaying.value
}

const handleSeek = (time: number) => {
  currentTime.value = time
  rrwebReplayer.value?.play(time)
  rrwebReplayer.value?.pause()
}

// Watch playback speed changes
watch(playbackSpeed, (newSpeed) => {
  rrwebReplayer.value?.setConfig({ speed: newSpeed })
})

watch(skipInactive, (newValue) => {
  rrwebReplayer.value?.setConfig({ skipInactive: newValue })
})
</script>

<style scoped>
.replay-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #1a1a1a;
}

.replay-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #2a2a2a;
  border-bottom: 1px solid #3a3a3a;
}

.session-info {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.controls {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.replay-content {
  flex: 1;
  display: flex;
  gap: 1px;
  background: #3a3a3a;
  overflow: hidden;
}

.pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #1a1a1a;
}

.pane-header {
  display: flex;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: #2a2a2a;
  border-bottom: 1px solid #3a3a3a;
}

.rrweb-player {
  flex: 1;
  overflow: auto;
  padding: 1rem;
}
</style>
```

---

#### **ReplayTimeline.vue** (Enhanced)

```vue
<!-- frontend/src/components/ReplayTimeline.vue -->
<template>
  <div class="timeline-container">
    <!-- Time display -->
    <div class="time-display">
      {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
    </div>

    <!-- Scrubber bar -->
    <div class="timeline" @click="handleClick" ref="timelineRef">
      <!-- Progress bar -->
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: `${progress}%` }"
        ></div>
      </div>

      <!-- Scrubber handle -->
      <div
        class="scrubber-handle"
        :style="{ left: `${progress}%` }"
        @mousedown="startDrag"
      ></div>

      <!-- Agent event markers -->
      <div
        v-for="event in agentEvents"
        :key="event.timestamp_ms"
        class="event-marker"
        :class="`marker-${event.type}`"
        :style="{ left: `${(event.timestamp_ms / duration) * 100}%` }"
        @click.stop="seekToEvent(event)"
        @mouseenter="showTooltip(event, $event)"
        @mouseleave="hideTooltip"
      >
        <div class="marker-dot"></div>
      </div>
    </div>

    <!-- Tooltip -->
    <Teleport to="body">
      <div
        v-if="tooltipVisible"
        class="timeline-tooltip"
        :style="tooltipStyle"
      >
        <div class="tooltip-header">
          <Icon :name="getEventIcon(tooltipEvent?.type)" />
          <strong>{{ tooltipEvent?.name }}</strong>
        </div>
        <div class="tooltip-time">
          {{ formatTime(tooltipEvent?.timestamp_ms) }}
        </div>
        <div v-if="tooltipEvent?.duration_ms" class="tooltip-duration">
          Duration: {{ tooltipEvent.duration_ms }}ms
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  currentTime: number
  duration: number
  agentEvents: Array<{
    timestamp_ms: number
    type: string
    name: string
    duration_ms?: number
  }>
  isPlaying: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  seek: [time: number]
  togglePlay: []
}>()

// State
const timelineRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const tooltipVisible = ref(false)
const tooltipEvent = ref<any>(null)
const tooltipStyle = ref({})

// Computed
const progress = computed(() => {
  if (!props.duration) return 0
  return (props.currentTime / props.duration) * 100
})

// Methods
const handleClick = (e: MouseEvent) => {
  if (!timelineRef.value) return

  const rect = timelineRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const percentage = x / rect.width
  const time = percentage * props.duration

  emit('seek', time)
}

const startDrag = (e: MouseEvent) => {
  isDragging.value = true

  const handleMove = (e: MouseEvent) => {
    if (!isDragging.value || !timelineRef.value) return

    const rect = timelineRef.value.getBoundingClientRect()
    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
    const percentage = x / rect.width
    const time = percentage * props.duration

    emit('seek', time)
  }

  const handleUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', handleMove)
    document.removeEventListener('mouseup', handleUp)
  }

  document.addEventListener('mousemove', handleMove)
  document.addEventListener('mouseup', handleUp)
}

const seekToEvent = (event: any) => {
  emit('seek', event.timestamp_ms)
}

const showTooltip = (event: any, e: MouseEvent) => {
  tooltipEvent.value = event
  tooltipVisible.value = true

  tooltipStyle.value = {
    left: `${e.clientX}px`,
    top: `${e.clientY - 80}px`
  }
}

const hideTooltip = () => {
  tooltipVisible.value = false
}

const getEventIcon = (type: string) => {
  const icons = {
    tool: 'tool',
    llm: 'brain',
    file: 'file',
    error: 'alert-circle'
  }
  return icons[type as keyof typeof icons] || 'circle'
}

const formatTime = (ms: number) => {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.timeline-container {
  padding: 1rem;
  background: #2a2a2a;
  border-top: 1px solid #3a3a3a;
}

.timeline {
  position: relative;
  height: 40px;
  background: #1a1a1a;
  border-radius: 4px;
  cursor: pointer;
}

.progress-bar {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 4px;
  background: #3a3a3a;
  transform: translateY(-50%);
  border-radius: 2px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 2px;
  transition: width 0.1s linear;
}

.scrubber-handle {
  position: absolute;
  top: 50%;
  width: 16px;
  height: 16px;
  background: #fff;
  border: 2px solid #3b82f6;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  cursor: grab;
  transition: transform 0.1s ease;
}

.scrubber-handle:hover {
  transform: translate(-50%, -50%) scale(1.2);
}

.scrubber-handle:active {
  cursor: grabbing;
}

.event-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  cursor: pointer;
  z-index: 10;
}

.marker-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition: transform 0.2s ease;
}

.event-marker:hover .marker-dot {
  transform: translate(-50%, -50%) scale(1.5);
}

/* Event type colors */
.marker-tool {
  background: rgba(59, 130, 246, 0.3);
}

.marker-tool .marker-dot {
  background: #3b82f6;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

.marker-llm {
  background: rgba(139, 92, 246, 0.3);
}

.marker-llm .marker-dot {
  background: #8b5cf6;
  box-shadow: 0 0 8px rgba(139, 92, 246, 0.6);
}

.marker-file {
  background: rgba(16, 185, 129, 0.3);
}

.marker-file .marker-dot {
  background: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
}

.marker-error {
  background: rgba(239, 68, 68, 0.3);
}

.marker-error .marker-dot {
  background: #ef4444;
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.6);
}

.timeline-tooltip {
  position: fixed;
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  padding: 0.75rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  z-index: 1000;
  pointer-events: none;
  min-width: 200px;
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
</style>
```

---

### 4. Performance Optimizations

#### **Event Compression**

```typescript
// frontend/src/utils/compression.ts
import { pack, unpack } from 'rrweb'

/**
 * Compress rrweb events using built-in packer
 * Reduces payload size by ~70%
 */
export function compressEvents(events: any[]): string {
  return pack(events)
}

/**
 * Decompress packed events
 */
export function decompressEvents(packed: string): any[] {
  return unpack(packed)
}
```

**Backend gzip support:**
```python
# backend/app/main.py
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

---

#### **Lazy Loading for Large Sessions**

```typescript
// frontend/src/composables/useReplayStream.ts
/**
 * Stream replay events in chunks for large sessions
 */
export function useReplayStream(sessionId: string) {
  const events = ref<any[]>([])
  const isComplete = ref(false)

  const loadChunk = async (offset: number, limit: number = 1000) => {
    const response = await fetch(
      `/api/sessions/${sessionId}/replay/events?offset=${offset}&limit=${limit}`
    )
    const chunk = await response.json()

    events.value.push(...chunk.events)
    isComplete.value = chunk.has_more === false

    return chunk
  }

  return { events, loadChunk, isComplete }
}
```

**Backend pagination:**
```python
@router.get("/sessions/{session_id}/replay/events")
async def get_replay_events_paginated(
    session_id: str,
    offset: int = 0,
    limit: int = 1000
):
    """Stream events in chunks for large sessions"""
    replay = await service.get_replay(session_id)

    if not replay:
        raise HTTPException(status_code=404)

    events = replay.rrweb_events[offset:offset + limit]
    has_more = offset + limit < len(replay.rrweb_events)

    return {
        "events": events,
        "offset": offset,
        "limit": limit,
        "total": len(replay.rrweb_events),
        "has_more": has_more
    }
```

---

#### **MongoDB Aggregation for Timeline**

```python
# Efficient query for agent timeline only (skip large event array)
async def get_agent_timeline_only(session_id: str):
    pipeline = [
        {"$match": {"session_id": session_id}},
        {"$project": {
            "agent_timeline": 1,
            "duration_ms": 1,
            "_id": 0
        }}
    ]

    result = await collection.aggregate(pipeline).to_list(1)
    return result[0] if result else None
```

---

## Data Flow Diagrams

### Recording Flow

```
User Action (click, scroll, type)
         ↓
MutationObserver (rrweb)
         ↓
Event Buffer (in-memory array)
         ↓
[50 events accumulated OR 10s timer]
         ↓
Compress (optional)
         ↓
POST /sessions/{id}/replay/events
         ↓
MongoDB $push operator
         ↓
Updated session_replays document
```

### Playback Flow

```
User opens session history
         ↓
GET /sessions/{id}/replay
         ↓
MongoDB query (with projection)
         ↓
{
  events: [...],
  agent_timeline: [...],
  duration_ms: 180000
}
         ↓
Frontend decompress (if needed)
         ↓
new Replayer(events, config)
         ↓
Render in rrwebTarget div
         ↓
User scrubs timeline
         ↓
replayer.play(timestamp)
```

---

## Comparison Table

| Feature | Full External Replay Stack | Lightweight rrweb |
|---------|----------------|-------------------|
| **Infrastructure** | 6 containers | 0 (library only) |
| **Memory Overhead** | ~2GB | ~100MB |
| **Bundle Size** | ~500KB | ~80KB |
| **Storage** | Postgres + MinIO | MongoDB only |
| **Setup Time** | 30-60 min | 10 min |
| **Customization** | Limited | Full control |
| **Co-browsing** | ✅ Yes | ❌ No (CDP only) |
| **Multi-tab** | ✅ Yes | ⚠️ Manual |
| **Timeline** | Basic | Custom (enhanced) |
| **Agent Events** | Manual integration | Native support |
| **Compression** | Automatic | Manual (pack) |
| **Privacy Controls** | Global | CSS classes |
| **Data Retention** | Complex (3 systems) | Simple (MongoDB TTL) |

---

## Migration Path

### Phase 1: MVP (Week 1)
- Install rrweb (`bun add rrweb`)
- Create `useSessionReplay.ts`
- Implement MongoDB repository
- Add API endpoints
- Basic replay player

**Deliverable**: Working session replay with UI events

---

### Phase 2: Timeline Enhancement (Week 2)
- Track agent events (tool starts, LLM calls)
- Enhanced `ReplayTimeline.vue` with markers
- Event type filtering
- Playback speed controls

**Deliverable**: Full timeline with agent execution visibility

---

### Phase 3: Optimization (Week 3)
- Event compression (pack/unpack)
- Lazy loading for large sessions
- MongoDB aggregation pipelines
- Retention policies (TTL indexes)

**Deliverable**: Production-ready performance

---

### Phase 4 (Optional): Legacy Replay Migration
- Dual composable (feature flag)
- Data migration script
- Gradual rollout
- A/B testing

**Deliverable**: Seamless upgrade path if needed

---

## Resource Requirements

### Development
- **Frontend**: 1 developer × 3 days
- **Backend**: 1 developer × 2 days
- **Testing**: 1 QA × 1 day

### Infrastructure (Production)
- **MongoDB**: +500MB per 1000 sessions (10min avg)
- **Bandwidth**: ~5KB/s during recording
- **CPU**: +15-30% on client browser
- **Memory**: +60-100MB on client browser

---

## Security & Privacy

### Data Masking

```html
<!-- Block entire elements from recording -->
<div class="rr-block">
  <input type="password" /> <!-- Not recorded -->
</div>

<!-- Mask text content -->
<div class="rr-mask">
  Sensitive data <!-- Replaced with *** -->
</div>

<!-- Ignore from replay (still in DOM, just not recorded) -->
<div class="rr-ignore">
  Admin panel
</div>
```

### GDPR Compliance

```python
# backend/app/interfaces/api/sessions/replay.py
@router.delete("/sessions/{session_id}/replay")
async def delete_replay_data(
    session_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    GDPR: Right to be forgotten
    Permanently delete all replay data
    """
    deleted = await service.delete_replay(session_id)

    if not deleted:
        raise HTTPException(status_code=404)

    # Also delete from MinIO if used
    await minio_client.remove_session_frames(session_id)

    return {"status": "deleted"}
```

### Automatic Cleanup

```javascript
// MongoDB TTL index (auto-delete after 30 days)
db.session_replays.createIndex(
  { "created_at": 1 },
  { expireAfterSeconds: 2592000 }  // 30 days
)
```

---

## Testing Strategy

### Unit Tests

```typescript
// frontend/tests/useSessionReplay.test.ts
import { describe, it, expect, vi } from 'vitest'
import { useSessionReplay } from '@/composables/useSessionReplay'

describe('useSessionReplay', () => {
  it('should start recording', async () => {
    const { startRecording, isRecording } = useSessionReplay()

    await startRecording('test-session-id')

    expect(isRecording.value).toBe(true)
  })

  it('should batch events', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch')
    const { startRecording } = useSessionReplay()

    await startRecording('test-session-id')

    // Simulate 50 events
    for (let i = 0; i < 50; i++) {
      // Trigger events
    }

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/replay/events'),
      expect.any(Object)
    )
  })
})
```

### Integration Tests

```python
# backend/tests/test_session_replay.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_append_events(client: AsyncClient):
    """Test appending rrweb events"""
    response = await client.post(
        "/api/sessions/test-id/replay/events",
        json={
            "events": [
                {"type": 2, "data": {}, "timestamp": 1000},
                {"type": 3, "data": {}, "timestamp": 2000}
            ],
            "compressed": False
        }
    )

    assert response.status_code == 200
    assert response.json()["events_received"] == 2

@pytest.mark.asyncio
async def test_get_replay(client: AsyncClient):
    """Test retrieving replay data"""
    # First, insert test data
    await client.post("/api/sessions/test-id/replay/events", ...)

    # Then retrieve
    response = await client.get("/api/sessions/test-id/replay")

    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "agent_timeline" in data
```

---

## Monitoring & Observability

### Metrics to Track

```python
# backend/app/application/services/session_replay_service.py
from prometheus_client import Counter, Histogram

# Counters
events_received = Counter('replay_events_received_total', 'Total rrweb events received')
agent_events_tracked = Counter('replay_agent_events_total', 'Total agent events tracked')

# Histograms
event_batch_size = Histogram('replay_event_batch_size', 'Size of event batches')
replay_duration = Histogram('replay_duration_seconds', 'Session replay duration')

class SessionReplayService:
    async def append_events(self, session_id: str, events: list[dict], ...):
        events_received.inc(len(events))
        event_batch_size.observe(len(events))

        await self._repository.append_events(...)
```

### Grafana Dashboard

```yaml
# Key metrics to display
- Replays recorded per hour
- Average events per session
- Storage growth (MB/day)
- Playback errors
- Timeline marker distribution (tool vs LLM vs error)
```

---

## References

### External Documentation
- **rrweb**: https://github.com/rrweb-io/rrweb
- **rrweb API**: https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/index.md
- **CDP Screencast**: https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-startScreencast
- **MongoDB TTL**: https://www.mongodb.com/docs/manual/core/index-ttl/

### Internal Files
- `frontend/src/composables/useScreenshotReplay.ts` (current screenshot replay implementation)
- `frontend/src/components/SandboxViewer.vue` (CDP screencast)
- `frontend/src/components/ReplayTimeline.vue` (basic timeline)
- Current replay and sandbox guide

---

## Next Steps

1. **Proof of Concept** (2 days)
   - Install rrweb in frontend
   - Create minimal `useSessionReplay` composable
   - Test basic record/replay

2. **Backend Implementation** (3 days)
   - MongoDB repository
   - API endpoints
   - Agent event tracking

3. **UI Polish** (2 days)
   - Enhanced timeline with markers
   - Dual-pane player
   - Playback controls

4. **Production Readiness** (3 days)
   - Compression
   - Pagination
   - Testing
   - Monitoring

---

**Total Estimated Effort**: 10 engineering days (2 weeks for 1 full-stack developer)

**Go-Live**: 3 weeks with testing and QA
