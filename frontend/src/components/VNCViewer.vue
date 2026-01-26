<template>
  <div class="vnc-wrapper" style="position: relative; width: 100%; height: 100%;">
    <!-- Loading overlay -->
    <div v-if="!isConnected" class="loading-overlay">
      <div class="loading-content">
        <div class="loading-shape" :class="currentShape"></div>
        <span class="loading-text">Connecting</span>
      </div>
    </div>
    <!-- VNC container -->
    <div
      ref="vncContainer"
      class="vnc-container"
      :class="{ 'vnc-viewonly': props.viewOnly }"
      style="display: flex; width: 100%; height: 100%; overflow: auto; background: rgb(40, 40, 40);">
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted, onUnmounted, watch } from 'vue';
import { getVNCUrl } from '@/api/agent';
// @ts-expect-error - NoVNC doesn't have TypeScript definitions
import RFB from '@novnc/novnc/lib/rfb';

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

const vncContainer = ref<HTMLDivElement | null>(null);
const isConnected = ref(false);
let rfb: RFB | null = null;

// Morphing shape animation
const shapes = ['circle', 'diamond', 'cube'] as const;
type Shape = typeof shapes[number];
const currentShapeIndex = ref(0);
const currentShape = ref<Shape>('circle');
let shapeIntervalId: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  shapeIntervalId = setInterval(() => {
    currentShapeIndex.value = (currentShapeIndex.value + 1) % shapes.length;
    currentShape.value = shapes[currentShapeIndex.value];
  }, 800);
});

onUnmounted(() => {
  if (shapeIntervalId) {
    clearInterval(shapeIntervalId);
  }
});

const initVNCConnection = async () => {
  if (!vncContainer.value || !props.enabled) return;

  // Disconnect existing connection
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }

  isConnected.value = false;

  try {
    const wsUrl = await getVNCUrl(props.sessionId);

    // Create NoVNC connection
    rfb = new RFB(vncContainer.value, wsUrl, {
      credentials: { password: '' },
      shared: true,
      repeaterID: '',
      wsProtocols: ['binary'],
      // Scaling options
      scaleViewport: true,  // Automatically scale to fit container
      //resizeSession: true   // Request server to adjust resolution
    });

    // Set viewOnly based on props, default to false (interactive)
    rfb.viewOnly = props.viewOnly ?? false;
    rfb.scaleViewport = true;
    //rfb.resizeSession = true;

    rfb.addEventListener('connect', () => {
      console.log('VNC connection successful');
      isConnected.value = true;
      emit('connected');
    });

    rfb.addEventListener('disconnect', (e: any) => {
      console.log('VNC connection disconnected', e);
      isConnected.value = false;
      emit('disconnected', e);
    });

    rfb.addEventListener('credentialsrequired', () => {
      console.log('VNC credentials required');
      emit('credentialsRequired');
    });
  } catch (error) {
    console.error('Failed to initialize VNC connection:', error);
    isConnected.value = false;
  }
};

const disconnect = () => {
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }
  isConnected.value = false;
};

// Watch for session ID or enabled state changes
watch([() => props.sessionId, () => props.enabled], () => {
  if (props.enabled && vncContainer.value) {
    initVNCConnection();
  } else {
    disconnect();
  }
}, { immediate: true });

// Watch for container availability
watch(vncContainer, () => {
  if (vncContainer.value && props.enabled) {
    initVNCConnection();
  }
});

onBeforeUnmount(() => {
  disconnect();
});

// Expose methods for parent component
defineExpose({
  disconnect,
  initConnection: initVNCConnection
});
</script>

<style scoped>
.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgb(40, 40, 40);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.loading-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-shape {
  width: 10px;
  height: 10px;
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  background-size: 200% 200%;
  animation: shimmer 1.5s ease-in-out infinite;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.loading-shape.circle {
  border-radius: 50%;
}

.loading-shape.diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

.loading-shape.cube {
  border-radius: 2px;
}

.loading-text {
  font-size: 14px;
  font-weight: 500;
  color: #ffffff;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.vnc-container.vnc-viewonly {
  cursor: default;
}

.vnc-container.vnc-viewonly :deep(canvas) {
  cursor: default !important;
}
</style>
