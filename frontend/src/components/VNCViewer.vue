<template>
  <div ref="wrapperRef" class="vnc-wrapper">
    <!-- Loading state -->
    <div
      v-if="isLoading"
      class="vnc-loading"
      :class="{ 'vnc-loading--compact': !!props.compactLoading }"
    >
      <LoadingState
        :label="props.compactLoading ? 'Connecting' : 'Connecting to screen'"
        :detail="statusText"
        :is-active="true"
        animation="globe"
      />
    </div>
    <!-- VNC renders inside this container -->
    <div ref="vncContainer" class="vnc-screen"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, watch, onMounted } from 'vue';
import { getVNCUrl } from '@/api/agent';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import { getPreconnectedVNCUrl, cacheVNCUrl } from '@/composables/useVNCPreconnect';

const props = withDefaults(
  defineProps<{
    sessionId: string;
    enabled?: boolean;
    viewOnly?: boolean;
    compactLoading?: boolean;
    reconnectAttempt?: number;
  }>(),
  {
    reconnectAttempt: 0
  }
);

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
    return RFBClass;
  } catch {
    const module = await import(/* @vite-ignore */ 'https://cdn.jsdelivr.net/gh/novnc/noVNC@v1.5.0/core/rfb.js');
    RFBClass = module.default || module.RFB || module;
    return RFBClass;
  }
}

async function initVNCConnection() {
  if (isConnecting) {
    return;
  }

  if (!vncContainer.value || !props.enabled || !props.sessionId) {
    return;
  }

  const thisConnectionId = ++connectionId;
  isConnecting = true;

  // Disconnect any existing connection
  disconnect();

  isLoading.value = true;
  statusText.value = 'Connecting...';

  try {
    // Phase 4: Try to use pre-cached URL first for faster connection
    let wsUrl = getPreconnectedVNCUrl(props.sessionId);
    if (!wsUrl) {
      wsUrl = await getVNCUrl(props.sessionId);
      // Cache for future use
      cacheVNCUrl(props.sessionId, wsUrl);
    }

    if (thisConnectionId !== connectionId) {
      return;
    }

    const RFB = await loadRFB();

    if (thisConnectionId !== connectionId || !vncContainer.value) {
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

    // Performance settings for real-time updates
    // qualityLevel: 0-9, higher = better quality but more bandwidth (6 is good balance)
    // compressionLevel: 0-9, higher = more compression/CPU usage (2 is good for LAN)
    rfb.qualityLevel = 6;
    rfb.compressionLevel = 2;

    rfb.addEventListener('connect', () => {
      isLoading.value = false;
      isConnecting = false;
      statusText.value = 'Connected';
      emit('connected');
    });

    rfb.addEventListener('disconnect', (e: any) => {
      isLoading.value = false;
      isConnecting = false;
      statusText.value = e?.detail?.clean ? 'Disconnected' : 'Connection lost';
      rfb = null;
      emit('disconnected', e?.detail);
    });

    rfb.addEventListener('credentialsrequired', () => {
      statusText.value = 'Password required';
      emit('credentialsRequired');
    });

  } catch (error) {
    isLoading.value = false;
    isConnecting = false;
    statusText.value = 'Connection failed';
    const reason = error instanceof Error ? error.message : 'connection_failed';
    emit('disconnected', reason);
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
  overflow: hidden !important;
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
  z-index: 10;
}

/* Compact loading mode for tiny/thumbnail viewers (e.g. mini VNC preview) */
.vnc-loading--compact :deep(.loading-state) {
  padding: 8px;
}

.vnc-loading--compact :deep(.loading-animation) {
  margin-bottom: 2px;
  transform: scale(0.42);
  transform-origin: center;
}

.vnc-loading--compact :deep(.loading-text) {
  gap: 4px;
}

.vnc-loading--compact :deep(.loading-label) {
  font-size: 10px;
  line-height: 1.1;
}

.vnc-loading--compact :deep(.loading-detail) {
  display: none;
}

@media (max-width: 640px) {
  .vnc-loading--compact :deep(.loading-animation) {
    transform: scale(0.34);
  }

  .vnc-loading--compact :deep(.loading-label) {
    font-size: 9px;
  }
}
</style>
