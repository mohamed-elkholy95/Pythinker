<template>
  <div class="vnc-content-wrapper">
    <!-- Text-only operation placeholder -->
    <LoadingState
      v-if="showPlaceholder"
      :label="placeholderLabel || 'Loading'"
      :detail="placeholderDetail"
      :is-active="isActive"
      animation="globe"
    />

    <!-- Live VNC - use absolute positioning to fill parent -->
    <div v-else-if="enabled" class="vnc-content-inner">
      <VNCViewer
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="viewOnly"
        @connected="emit('connected')"
        @disconnected="emit('disconnected')"
      />
    </div>

    <!-- Static screenshot -->
    <img
      v-else-if="screenshot"
      :src="screenshot"
      alt="Screenshot"
      class="vnc-screenshot"
      referrerpolicy="no-referrer"
    />

    <!-- Take over button slot -->
    <slot name="takeover"></slot>
  </div>
</template>

<script setup lang="ts">
import VNCViewer from '@/components/VNCViewer.vue';
import LoadingState from '@/components/toolViews/shared/LoadingState.vue';

defineProps<{
  sessionId: string;
  enabled: boolean;
  viewOnly?: boolean;
  showPlaceholder?: boolean;
  placeholderLabel?: string;
  placeholderDetail?: string;
  isActive?: boolean;
  screenshot?: string;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [];
}>();
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

.vnc-screenshot {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
