<template>
  <div
    class="vnc-mini-preview"
    :class="sizeClass"
    @click="emit('click')"
  >
    <!-- Scaled-down live VNC container -->
    <div class="vnc-mini-inner" :class="innerSizeClass">
      <!-- Live VNC Viewer (scaled down) -->
      <div class="vnc-mini-content">
        <VNCViewer
          v-if="sessionId && enabled"
          :session-id="sessionId"
          :enabled="enabled"
          :view-only="true"
        />
        <!-- Placeholder when no session / idle state -->
        <div v-else class="vnc-placeholder">
          <div class="idle-computer-icon">
            <Monitor class="w-8 h-8 text-gray-400" />
            <div class="idle-dot"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Expand icon on hover -->
    <button class="expand-btn">
      <Maximize2 class="w-3 h-3 sm:w-4 sm:h-4" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Maximize2, Monitor } from 'lucide-vue-next';
import VNCViewer from '@/components/VNCViewer.vue';

const props = withDefaults(defineProps<{
  sessionId?: string;
  enabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
}>(), {
  enabled: true,
  size: 'md'
});

const emit = defineEmits<{
  click: [];
}>();

const sizeClass = computed(() => {
  switch (props.size) {
    case 'sm': return 'size-sm';
    case 'lg': return 'size-lg';
    default: return 'size-md';
  }
});

const innerSizeClass = computed(() => {
  switch (props.size) {
    case 'sm': return 'inner-sm';
    case 'lg': return 'inner-lg';
    default: return 'inner-md';
  }
});
</script>

<style scoped>
.vnc-mini-preview {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bolt-elements-bg-depth-2);
  backdrop-filter: blur(40px);
  border: 1px solid var(--bolt-elements-borderColor);
  cursor: pointer;
  transition: transform 0.2s ease;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.vnc-mini-preview:hover {
  transform: scale(1.03);
  border-color: var(--bolt-elements-borderColorActive);
}

/* Size variants */
.size-sm {
  width: 80px;
  height: 50px;
}

.size-md {
  width: 130px;
  height: 80px;
}

.size-lg {
  width: 150px;
  height: 95px;
}

@media (max-width: 640px) {
  .size-sm { width: 56px; height: 40px; }
  .size-md { width: 100px; height: 65px; }
  .size-lg { width: 120px; height: 78px; }
}

/* Inner container with VNC - scaled down */
.vnc-mini-inner {
  pointer-events: none;
  transform-origin: 0 0;
  position: absolute;
  top: 0;
  left: 0;
}

/* RTL support */
:global([dir="rtl"]) .vnc-mini-inner {
  transform-origin: 100% 0;
  left: auto;
  right: 0;
}

/* Scale ratios for different sizes */
/* Target: fit 1280x800 VNC into thumbnail */
.inner-sm {
  width: 1280px;
  height: 800px;
  transform: scale(0.0625); /* 80/1280 */
}

.inner-md {
  width: 1280px;
  height: 800px;
  transform: scale(0.1015); /* 130/1280 */
}

.inner-lg {
  width: 1280px;
  height: 800px;
  transform: scale(0.117); /* 150/1280 */
}

@media (max-width: 640px) {
  .inner-sm { transform: scale(0.0437); /* 56/1280 */ }
  .inner-md { transform: scale(0.078); /* 100/1280 */ }
  .inner-lg { transform: scale(0.0937); /* 120/1280 */ }
}

.vnc-mini-content {
  position: relative;
  width: 100%;
  height: 100%;
  background: #282828;
  display: flex;
  align-items: center;
  justify-content: center;
}

.vnc-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

.idle-computer-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.idle-dot {
  position: absolute;
  bottom: -4px;
  right: -4px;
  width: 8px;
  height: 8px;
  background: #3b82f6;
  border-radius: 50%;
  animation: idle-pulse 2s ease-in-out infinite;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

@keyframes idle-pulse {
  0%, 100% {
    opacity: 0.4;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

/* Expand button */
.expand-btn {
  position: absolute;
  bottom: 3px;
  right: 3px;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.vnc-mini-preview:hover .expand-btn {
  opacity: 1;
}

@media (min-width: 640px) {
  .expand-btn {
    width: 28px;
    height: 28px;
    border-radius: 8px;
  }
}

/* Dark mode adjustments */
:global(.dark) .vnc-mini-preview {
  border-color: var(--border-dark);
}
</style>
