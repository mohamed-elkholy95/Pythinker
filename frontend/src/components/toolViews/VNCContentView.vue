<template>
  <div class="vnc-content-wrapper">
    <!-- Placeholder for loading/text-only operations -->
    <LoadingState
      v-if="showPlaceholder"
      :label="placeholderLabel || 'Loading'"
      :detail="placeholderDetail"
      :is-active="isActive"
      :animation="placeholderAnimation || 'globe'"
    />

    <!-- Live VNC - use absolute positioning to fill parent -->
    <div v-else-if="enabled" class="vnc-content-inner">
      <VNCViewer
        ref="vncViewerRef"
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="viewOnly"
        @connected="emit('connected')"
        @disconnected="emit('disconnected')"
      />
    </div>

    <!-- Fallback when no session -->
    <div v-else class="vnc-empty">
      <div class="vnc-empty-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
          <line x1="8" y1="21" x2="16" y2="21"/>
          <line x1="12" y1="17" x2="12" y2="21"/>
        </svg>
      </div>
      <span class="vnc-empty-text">No live session</span>
    </div>

    <!-- Take over button slot -->
    <slot name="takeover"></slot>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import VNCViewer from '@/components/VNCViewer.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

defineProps<{
  sessionId: string;
  enabled: boolean;
  viewOnly?: boolean;
  showPlaceholder?: boolean;
  placeholderLabel?: string;
  placeholderDetail?: string;
  placeholderAnimation?: 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner' | 'check';
  isActive?: boolean;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [];
}>();

const vncViewerRef = ref<InstanceType<typeof VNCViewer> | null>(null);
</script>

<style scoped>
/* Use absolute positioning to fill flex parent properly */
.vnc-content-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgb(40, 40, 40);
}

.vnc-content-inner {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}

.vnc-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--text-tertiary);
  gap: 12px;
}

.vnc-empty-icon {
  opacity: 0.5;
}

.vnc-empty-text {
  font-size: 14px;
}
</style>
