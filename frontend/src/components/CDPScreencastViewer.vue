<template>
  <div ref="wrapperRef" class="cdp-viewer-wrapper">
    <!-- Loading state -->
    <div v-if="isLoading" class="cdp-loading">
      <div class="cdp-loading-spinner"></div>
      <span class="cdp-loading-text">{{ statusText }}</span>
    </div>

    <!-- Error state -->
    <div v-if="error" class="cdp-error">
      <span class="cdp-error-icon">!</span>
      <span class="cdp-error-text">{{ error }}</span>
      <button @click="reconnect" class="cdp-retry-btn">Retry</button>
    </div>

    <!-- Frame display -->
    <img
      v-show="!isLoading && !error"
      ref="frameImg"
      class="cdp-frame"
      alt="Browser view"
      @load="onFrameLoad"
      @error="onFrameError"
    />

    <!-- Stats overlay (debug mode) -->
    <div v-if="showStats && stats.frameCount > 0" class="cdp-stats">
      <span>{{ stats.fps.toFixed(1) }} FPS</span>
      <span>{{ formatBytes(stats.bytesPerSec) }}/s</span>
      <span>{{ stats.frameCount }} frames</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue';

const props = defineProps<{
  sandboxUrl: string;
  enabled?: boolean;
  quality?: number;
  maxFps?: number;
  showStats?: boolean;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [reason?: string];
  error: [error: string];
}>();

// Refs
const wrapperRef = ref<HTMLDivElement | null>(null);
const frameImg = ref<HTMLImageElement | null>(null);

// State
const isLoading = ref(false);
const statusText = ref('Connecting...');
const error = ref<string | null>(null);

// WebSocket connection
let ws: WebSocket | null = null;
let reconnectTimeout: number | null = null;
let connectionAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Stats tracking
const stats = ref({
  frameCount: 0,
  bytesReceived: 0,
  fps: 0,
  bytesPerSec: 0,
  lastFrameTime: 0,
});

let statsInterval: number | null = null;
let lastStatsTime = Date.now();
let lastStatsFrameCount = 0;
let lastStatsBytesReceived = 0;

// Computed WebSocket URL
const wsUrl = computed(() => {
  const baseUrl = props.sandboxUrl.replace(/^http/, 'ws');
  const quality = props.quality ?? 70;
  const maxFps = props.maxFps ?? 15;
  return `${baseUrl}/api/v1/screencast/stream?quality=${quality}&max_fps=${maxFps}`;
});

// Connect to WebSocket stream
async function connect() {
  if (ws) {
    disconnect();
  }

  if (!props.enabled) {
    return;
  }

  isLoading.value = true;
  statusText.value = 'Connecting to CDP...';
  error.value = null;

  try {
    ws = new WebSocket(wsUrl.value);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('[CDP Viewer] Connected');
      isLoading.value = false;
      connectionAttempts = 0;
      emit('connected');
      startStatsTracking();
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary frame data
        displayFrame(event.data);
      } else {
        // JSON message (error or control)
        try {
          const msg = JSON.parse(event.data);
          if (msg.error) {
            handleError(msg.error);
          }
        } catch {
          // Not JSON, ignore
        }
      }
    };

    ws.onerror = (e) => {
      console.error('[CDP Viewer] WebSocket error:', e);
      handleError('Connection error');
    };

    ws.onclose = (e) => {
      console.log('[CDP Viewer] Disconnected:', e.code, e.reason);
      ws = null;
      stopStatsTracking();

      if (props.enabled && connectionAttempts < MAX_RECONNECT_ATTEMPTS) {
        // Auto-reconnect
        const delay = Math.min(1000 * Math.pow(2, connectionAttempts), 10000);
        connectionAttempts++;
        statusText.value = `Reconnecting in ${delay / 1000}s...`;
        isLoading.value = true;

        reconnectTimeout = window.setTimeout(() => {
          connect();
        }, delay);
      } else {
        emit('disconnected', e.reason);
      }
    };
  } catch (e) {
    handleError(`Failed to connect: ${e}`);
  }
}

function disconnect() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  if (ws) {
    try {
      ws.close();
    } catch {
      // Ignore
    }
    ws = null;
  }

  stopStatsTracking();
  isLoading.value = false;
}

function reconnect() {
  connectionAttempts = 0;
  error.value = null;
  connect();
}

// Display a frame from binary data
function displayFrame(data: ArrayBuffer) {
  if (!frameImg.value) return;

  // Create blob URL from binary data
  const blob = new Blob([data], { type: 'image/jpeg' });
  const url = URL.createObjectURL(blob);

  // Revoke previous URL to prevent memory leak
  if (frameImg.value.src && frameImg.value.src.startsWith('blob:')) {
    URL.revokeObjectURL(frameImg.value.src);
  }

  frameImg.value.src = url;

  // Update stats
  stats.value.frameCount++;
  stats.value.bytesReceived += data.byteLength;
  stats.value.lastFrameTime = Date.now();
}

function onFrameLoad() {
  // Frame loaded successfully
}

function onFrameError() {
  // Frame failed to load - likely corrupt data
  console.warn('[CDP Viewer] Frame load error');
}

function handleError(msg: string) {
  console.error('[CDP Viewer] Error:', msg);
  error.value = msg;
  isLoading.value = false;
  emit('error', msg);
}

// Stats tracking
function startStatsTracking() {
  if (statsInterval) return;

  lastStatsTime = Date.now();
  lastStatsFrameCount = 0;
  lastStatsBytesReceived = 0;

  statsInterval = window.setInterval(() => {
    const now = Date.now();
    const elapsed = (now - lastStatsTime) / 1000;

    if (elapsed > 0) {
      const frames = stats.value.frameCount - lastStatsFrameCount;
      const bytes = stats.value.bytesReceived - lastStatsBytesReceived;

      stats.value.fps = frames / elapsed;
      stats.value.bytesPerSec = bytes / elapsed;

      lastStatsTime = now;
      lastStatsFrameCount = stats.value.frameCount;
      lastStatsBytesReceived = stats.value.bytesReceived;
    }
  }, 1000);
}

function stopStatsTracking() {
  if (statsInterval) {
    clearInterval(statsInterval);
    statsInterval = null;
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes.toFixed(0)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Send control message
function pause() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('pause');
  }
}

function resume() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send('resume');
  }
}

// Watch enabled prop
watch(() => props.enabled, (enabled) => {
  if (enabled) {
    connect();
  } else {
    disconnect();
  }
});

// Lifecycle
onMounted(() => {
  if (props.enabled) {
    connect();
  }
});

onBeforeUnmount(() => {
  disconnect();

  // Clean up blob URL
  if (frameImg.value?.src?.startsWith('blob:')) {
    URL.revokeObjectURL(frameImg.value.src);
  }
});

// Expose methods
defineExpose({
  connect,
  disconnect,
  reconnect,
  pause,
  resume,
});
</script>

<style scoped>
.cdp-viewer-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #1a1a1a;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cdp-frame {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.cdp-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #1a1a1a;
  z-index: 10;
}

.cdp-loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #444;
  border-top-color: #10b981;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.cdp-loading-text {
  color: #888;
  font-size: 13px;
}

.cdp-error {
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
  background: #1a1a1a;
  z-index: 10;
}

.cdp-error-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ef4444;
  color: white;
  border-radius: 50%;
  font-weight: bold;
  font-size: 18px;
}

.cdp-error-text {
  color: #ef4444;
  font-size: 13px;
  max-width: 300px;
  text-align: center;
}

.cdp-retry-btn {
  padding: 6px 16px;
  background: #333;
  color: #ddd;
  border: 1px solid #444;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.cdp-retry-btn:hover {
  background: #444;
  border-color: #555;
}

.cdp-stats {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: flex;
  gap: 12px;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 4px;
  font-size: 11px;
  color: #10b981;
  font-family: monospace;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
