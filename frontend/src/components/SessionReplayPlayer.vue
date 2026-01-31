<template>
  <div class="replay-player">
    <!-- Header with session info -->
    <div class="replay-header">
      <div class="session-info">
        <h3 class="session-title">{{ sessionTitle || 'Session Replay' }}</h3>
        <span v-if="sessionId" class="session-id">{{ sessionId.substring(0, 8) }}...</span>
      </div>
      <div class="replay-controls-header">
        <button
          v-if="openReplayUrl"
          class="btn-external"
          @click="openInDashboard"
          title="Open in OpenReplay Dashboard"
        >
          <ExternalLink :size="16" />
          Dashboard
        </button>
        <button class="btn-close" @click="emit('close')">
          <X :size="18" />
        </button>
      </div>
    </div>

    <!-- Player area -->
    <div class="player-container">
      <!-- Loading state -->
      <div v-if="isLoading" class="player-loading">
        <div class="loading-spinner"></div>
        <span>Loading replay...</span>
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="player-error">
        <AlertCircle :size="32" />
        <span>{{ error }}</span>
        <button class="btn-retry" @click="loadReplay">Retry</button>
      </div>

      <!-- Player iframe - embeds OpenReplay player -->
      <iframe
        v-else-if="playerUrl"
        ref="playerFrame"
        class="player-iframe"
        :src="playerUrl"
        frameborder="0"
        allow="fullscreen"
        @load="onIframeLoad"
        @error="onIframeError"
      ></iframe>

      <!-- Fallback: No replay available -->
      <div v-else class="player-empty">
        <Play :size="48" class="icon-muted" />
        <span>No replay available</span>
        <p class="text-muted">Session recording may still be processing.</p>
      </div>
    </div>

    <!-- Timeline with events -->
    <ReplayTimeline
      v-if="events.length > 0"
      :events="events"
      :current-time="currentTime"
      :duration="duration"
      @seek="handleSeek"
      @event-click="handleEventClick"
    />

    <!-- Playback controls -->
    <div class="playback-controls">
      <div class="controls-left">
        <button class="btn-control" @click="togglePlay" :disabled="!playerUrl">
          <Pause v-if="isPlaying" :size="20" />
          <Play v-else :size="20" />
        </button>
        <button class="btn-control" @click="skipBackward" :disabled="!playerUrl">
          <SkipBack :size="18" />
        </button>
        <button class="btn-control" @click="skipForward" :disabled="!playerUrl">
          <SkipForward :size="18" />
        </button>
      </div>

      <div class="controls-center">
        <span class="time-display">
          {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
        </span>
      </div>

      <div class="controls-right">
        <select v-model="playbackSpeed" class="speed-select" :disabled="!playerUrl">
          <option value="0.5">0.5x</option>
          <option value="1">1x</option>
          <option value="1.5">1.5x</option>
          <option value="2">2x</option>
          <option value="4">4x</option>
        </select>
        <button class="btn-control" @click="toggleFullscreen" :disabled="!playerUrl">
          <Maximize :size="18" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Maximize,
  ExternalLink,
  X,
  AlertCircle
} from 'lucide-vue-next'
import ReplayTimeline from './ReplayTimeline.vue'

interface ReplayEvent {
  id: string
  type: string
  name: string
  timestamp: number
  payload?: Record<string, unknown>
}

const props = defineProps<{
  sessionId?: string
  sessionTitle?: string
  openReplaySessionId?: string
  events?: ReplayEvent[]
}>()

const emit = defineEmits<{
  close: []
  seek: [time: number]
  eventClick: [event: ReplayEvent]
}>()

// State
const isLoading = ref(false)
const error = ref<string | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const playbackSpeed = ref('1')
const playerFrame = ref<HTMLIFrameElement | null>(null)

// OpenReplay configuration
const openReplayApiUrl = import.meta.env.VITE_OPENREPLAY_API_URL || 'http://localhost:8090'
const openReplayUrl = computed(() => {
  if (!props.openReplaySessionId) return null
  return `${openReplayApiUrl}/session/${props.openReplaySessionId}`
})

// Player URL with embed parameters
const playerUrl = computed(() => {
  if (!props.openReplaySessionId) return null
  return `${openReplayApiUrl}/session/${props.openReplaySessionId}?embed=true&autoplay=false`
})

// Events with defaults
const events = computed(() => props.events || [])

// Load replay data
async function loadReplay(): Promise<void> {
  if (!props.openReplaySessionId) {
    error.value = 'No session ID provided'
    return
  }

  isLoading.value = true
  error.value = null

  try {
    // In a real implementation, this would fetch session metadata
    // from the OpenReplay API to get duration, events, etc.
    // For now, we rely on the iframe loading the full player

    // Simulate loading delay
    await new Promise((resolve) => setTimeout(resolve, 500))

    isLoading.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load replay'
    isLoading.value = false
  }
}

function onIframeLoad(): void {
  isLoading.value = false
  // Could communicate with iframe via postMessage for advanced control
}

function onIframeError(): void {
  error.value = 'Failed to load replay player'
  isLoading.value = false
}

function togglePlay(): void {
  isPlaying.value = !isPlaying.value
  // Send play/pause command to iframe via postMessage
  sendPlayerCommand(isPlaying.value ? 'play' : 'pause')
}

function skipBackward(): void {
  const newTime = Math.max(0, currentTime.value - 10000)
  currentTime.value = newTime
  sendPlayerCommand('seek', { time: newTime })
}

function skipForward(): void {
  const newTime = Math.min(duration.value, currentTime.value + 10000)
  currentTime.value = newTime
  sendPlayerCommand('seek', { time: newTime })
}

function handleSeek(time: number): void {
  currentTime.value = time
  sendPlayerCommand('seek', { time })
  emit('seek', time)
}

function handleEventClick(event: ReplayEvent): void {
  // Seek to event time
  currentTime.value = event.timestamp
  sendPlayerCommand('seek', { time: event.timestamp })
  emit('eventClick', event)
}

function toggleFullscreen(): void {
  if (playerFrame.value) {
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      playerFrame.value.requestFullscreen()
    }
  }
}

function openInDashboard(): void {
  if (openReplayUrl.value) {
    window.open(openReplayUrl.value, '_blank')
  }
}

function sendPlayerCommand(command: string, data?: Record<string, unknown>): void {
  // Send command to iframe via postMessage
  // This requires OpenReplay's embedded player to support these commands
  if (playerFrame.value?.contentWindow) {
    playerFrame.value.contentWindow.postMessage(
      { type: 'openreplay-command', command, ...data },
      '*'
    )
  }
}

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

// Watch playback speed changes
watch(playbackSpeed, (speed) => {
  sendPlayerCommand('setSpeed', { speed: parseFloat(speed) })
})

// Load on mount
onMounted(() => {
  if (props.openReplaySessionId) {
    loadReplay()
  }
})
</script>

<style scoped>
.replay-player {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background-gray-main, #1a1a1a);
  border-radius: 8px;
  overflow: hidden;
}

.replay-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--background-gray-secondary, #222);
  border-bottom: 1px solid var(--border-color, #333);
}

.session-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.session-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #fff);
}

.session-id {
  font-size: 12px;
  color: var(--text-muted, #888);
  font-family: monospace;
}

.replay-controls-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-external {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-secondary, #aaa);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-external:hover {
  background: var(--background-hover, #333);
  color: var(--text-primary, #fff);
}

.btn-close {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  background: transparent;
  border: none;
  color: var(--text-muted, #888);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.btn-close:hover {
  background: var(--background-hover, #333);
  color: var(--text-primary, #fff);
}

.player-container {
  flex: 1;
  position: relative;
  min-height: 300px;
}

.player-loading,
.player-error,
.player-empty {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted, #888);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #444;
  border-top-color: #10b981;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.player-error {
  color: #ef4444;
}

.btn-retry {
  padding: 8px 16px;
  background: var(--background-secondary, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-retry:hover {
  background: var(--background-hover, #444);
}

.player-iframe {
  width: 100%;
  height: 100%;
  background: #000;
}

.icon-muted {
  color: var(--text-muted, #666);
}

.text-muted {
  font-size: 12px;
  color: var(--text-muted, #666);
  margin: 0;
}

.playback-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--background-gray-secondary, #222);
  border-top: 1px solid var(--border-color, #333);
}

.controls-left,
.controls-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.controls-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.btn-control {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-control:hover:not(:disabled) {
  background: var(--background-hover, #333);
  color: var(--text-primary, #fff);
}

.btn-control:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.time-display {
  font-size: 13px;
  font-family: monospace;
  color: var(--text-secondary, #aaa);
}

.speed-select {
  padding: 6px 8px;
  background: var(--background-secondary, #333);
  border: 1px solid var(--border-color, #444);
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 12px;
  cursor: pointer;
}

.speed-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
