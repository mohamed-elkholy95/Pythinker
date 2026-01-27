<template>
  <ContentContainer :scrollable="false" padding="none" class="vnc-view">
    <div class="vnc-content">
      <!-- Text-only operation placeholder -->
      <LoadingState
        v-if="showPlaceholder"
        :label="placeholderLabel || 'Loading'"
        :detail="placeholderDetail"
        :is-active="isActive"
        animation="globe"
      />

      <!-- Live VNC -->
      <VNCViewer
        v-else-if="enabled"
        :session-id="sessionId"
        :enabled="enabled"
        :view-only="viewOnly"
        @connected="emit('connected')"
        @disconnected="emit('disconnected')"
        class="vnc-viewer"
      />

      <!-- Static screenshot -->
      <img v-else-if="screenshot" :src="screenshot" alt="Screenshot" class="vnc-screenshot" />

      <!-- Take over button -->
      <slot name="takeover"></slot>
    </div>
  </ContentContainer>
</template>

<script setup lang="ts">
import VNCViewer from '@/components/VNCViewer.vue';
import ContentContainer from '@/components/toolViews/shared/ContentContainer.vue';
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
.vnc-view {
  position: relative;
}

.vnc-content {
  position: relative;
  width: 100%;
  height: 100%;
}

.vnc-viewer {
  position: absolute;
  inset: 0;
}

.vnc-screenshot {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
