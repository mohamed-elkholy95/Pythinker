<template>
  <SandboxViewer
    :key="`cdp-${sessionId}`"
    :session-id="sessionId"
    :enabled="enabled"
    :view-only="viewOnly"
    :quality="quality"
    :max-fps="maxFps"
    :show-stats="showStats"
    @connected="emit('connected')"
    @disconnected="(reason?: string) => emit('disconnected', reason)"
    @error="(error: string) => emit('error', error)"
  />
</template>

<script setup lang="ts">
import SandboxViewer from '@/components/SandboxViewer.vue'

withDefaults(
  defineProps<{
    sessionId?: string
    enabled?: boolean
    viewOnly?: boolean
    quality?: number
    maxFps?: number
    showStats?: boolean
    compactLoading?: boolean
  }>(),
  {
    sessionId: '',
    enabled: true,
    viewOnly: true,
    quality: 70,
    maxFps: 15,
    showStats: false,
    compactLoading: false
  }
)

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
  error: [error: string]
  credentialsRequired: []
}>()
</script>
