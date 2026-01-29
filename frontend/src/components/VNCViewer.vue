<template>
  <div ref="wrapperRef" class="vnc-wrapper">
    <!-- Loading state -->
    <div v-if="isLoading" class="vnc-loading">
      <div class="vnc-loading-spinner"></div>
      <span class="vnc-loading-text">{{ statusText }}</span>
    </div>
    <!-- VNC renders inside this container -->
    <div ref="vncContainer" class="vnc-screen"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, onMounted } from 'vue';
import { getVNCUrl } from '@/api/agent';

const props = defineProps<{
  sessionId: string;
  enabled?: boolean;
  viewOnly?: boolean;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [reason?: any];
  credentialsRequired: [];
}>();

const wrapperRef = ref<HTMLDivElement | null>(null);
const vncContainer = ref<HTMLDivElement | null>(null);
const isLoading = ref(false);
const statusText = ref('Connecting...');

let rfb: any = null;
let RFBClass: any = null;
let isConnecting = false;
let connectionId = 0;

// Load RFB module dynamically
async function loadRFB(): Promise<any> {
  if (RFBClass) return RFBClass;

  try {
    const module = await import('@novnc/novnc/lib/rfb');
    RFBClass = module.default || module.RFB || module;
    console.log('[VNC] RFB loaded from npm');
    return RFBClass;
  } catch (e) {
    console.warn('[VNC] npm import failed, trying CDN:', e);
    const module = await import(/* @vite-ignore */ 'https://cdn.jsdelivr.net/gh/novnc/noVNC@v1.5.0/core/rfb.js');
    RFBClass = module.default || module.RFB || module;
    console.log('[VNC] RFB loaded from CDN');
    return RFBClass;
  }
}

async function initVNCConnection() {
  if (isConnecting) {
    console.log('[VNC] Already connecting, skipping');
    return;
  }

  if (!vncContainer.value || !props.enabled || !props.sessionId) {
    console.log('[VNC] Cannot connect - missing requirements');
    return;
  }

  const thisConnectionId = ++connectionId;
  isConnecting = true;

  // Disconnect any existing connection
  disconnect();

  isLoading.value = true;
  statusText.value = 'Connecting...';

  try {
    const wsUrl = await getVNCUrl(props.sessionId);

    if (thisConnectionId !== connectionId) {
      console.log('[VNC] Connection attempt superseded');
      return;
    }

    console.log('[VNC] Connecting to:', wsUrl);

    const RFB = await loadRFB();

    if (thisConnectionId !== connectionId || !vncContainer.value) {
      console.log('[VNC] Connection attempt no longer valid');
      return;
    }

    // Clear container before creating connection
    vncContainer.value.innerHTML = '';

    // Create NoVNC connection - let noVNC handle scaling
    rfb = new RFB(vncContainer.value, wsUrl, {
      credentials: { password: '' },
      shared: true,
      wsProtocols: ['binary'],
    });

    // Configure RFB - scaleViewport scales to fit, clipViewport clips overflow
    rfb.viewOnly = props.viewOnly ?? false;
    rfb.scaleViewport = true;
    rfb.clipViewport = true;  // Must be true to prevent weird tiling artifacts
    rfb.resizeSession = false;

    rfb.addEventListener('connect', () => {
      console.log('[VNC] Connected');
      isLoading.value = false;
      isConnecting = false;
      statusText.value = 'Connected';
      emit('connected');
    });

    rfb.addEventListener('disconnect', (e: any) => {
      console.log('[VNC] Disconnected', e?.detail);
      isLoading.value = false;
      isConnecting = false;
      statusText.value = e?.detail?.clean ? 'Disconnected' : 'Connection lost';
      rfb = null;
      emit('disconnected', e?.detail);
    });

    rfb.addEventListener('credentialsrequired', () => {
      console.log('[VNC] Credentials required');
      statusText.value = 'Password required';
      emit('credentialsRequired');
    });

  } catch (error) {
    console.error('[VNC] Connection error:', error);
    isLoading.value = false;
    isConnecting = false;
    statusText.value = 'Connection failed';
  }
}

function disconnect() {
  if (rfb) {
    try {
      rfb.disconnect();
    } catch {
      // Ignore
    }
    rfb = null;
  }
  isConnecting = false;
  isLoading.value = false;

  // Clear the container
  if (vncContainer.value) {
    vncContainer.value.innerHTML = '';
  }
}

// Single watcher for connection props
watch(
  [() => props.sessionId, () => props.enabled, vncContainer],
  ([sessionId, enabled, container]) => {
    if (enabled && sessionId && container) {
      initVNCConnection();
    } else if (!enabled) {
      disconnect();
    }
  },
  { immediate: false }
);

// Watch viewOnly separately
watch(() => props.viewOnly, (viewOnly) => {
  if (rfb) {
    rfb.viewOnly = viewOnly ?? false;
  }
});

onMounted(() => {
  if (props.enabled && props.sessionId && vncContainer.value) {
    initVNCConnection();
  }
});

onBeforeUnmount(() => {
  connectionId++;
  disconnect();
});

defineExpose({
  disconnect,
  initConnection: initVNCConnection
});
</script>

<style scoped>
.vnc-wrapper {
  /* Use absolute positioning to fill parent container */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #282828;
  overflow: hidden;
}

.vnc-screen {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

/* noVNC creates a div > canvas structure - ensure it fills container */
.vnc-screen :deep(> div) {
  width: 100% !important;
  height: 100% !important;
  position: relative !important;
}

.vnc-screen :deep(canvas) {
  /* Let noVNC handle the canvas sizing with scaleViewport */
  display: block !important;
}

.vnc-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #282828;
  z-index: 10;
}

.vnc-loading-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #666;
  border-top-color: #9c7dff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.vnc-loading-text {
  color: #999;
  font-size: 14px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
