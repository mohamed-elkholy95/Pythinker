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
      <LiveViewer
        ref="vncViewerRef"
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="viewOnly"
        @connected="emit('connected')"
        @disconnected="emit('disconnected')"
      />
    </div>

    <!-- Inactive state when no session - Manus-style design -->
    <InactiveState
      v-else
      :message="inactiveMessage"
    />

    <!-- Take over button slot -->
    <slot name="takeover"></slot>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import LiveViewer from '@/components/LiveViewer.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';
import InactiveState from '@/components/toolViews/shared/InactiveState.vue';

withDefaults(defineProps<{
  sessionId: string;
  enabled: boolean;
  viewOnly?: boolean;
  showPlaceholder?: boolean;
  placeholderLabel?: string;
  placeholderDetail?: string;
  placeholderAnimation?: 'globe' | 'search' | 'file' | 'terminal' | 'code' | 'spinner' | 'check';
  isActive?: boolean;
  inactiveMessage?: string;
}>(), {
  inactiveMessage: "Pythinker's computer is inactive"
});

const emit = defineEmits<{
  connected: [];
  disconnected: [];
}>();

const vncViewerRef = ref<InstanceType<typeof LiveViewer> | null>(null);
</script>

<style scoped>
/* Use absolute positioning to fill flex parent properly */
.vnc-content-wrapper {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--background-gray-main);
}

.vnc-content-inner {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}
</style>
