<script setup lang="ts">
/**
 * CodeServerView — iframe-based VS Code web IDE viewer.
 * Loads code-server via a signed URL from the backend.
 */
import { ref, watch, computed, onBeforeUnmount } from 'vue'

const props = defineProps<{
  sessionId: string
  enabled: boolean
  codeServerUrl?: string
}>()

const emit = defineEmits<{
  connected: []
  disconnected: []
  error: [message: string]
}>()

const iframeRef = ref<HTMLIFrameElement | null>(null)
const status = ref<'loading' | 'connected' | 'error'>('loading')

const iframeSrc = computed(() => {
  if (!props.enabled || !props.codeServerUrl) return ''
  return props.codeServerUrl
})

watch(
  () => props.enabled,
  (enabled) => {
    if (enabled) {
      status.value = 'loading'
    } else {
      status.value = 'error'
      emit('disconnected')
    }
  },
)

function onIframeLoad() {
  status.value = 'connected'
  emit('connected')
}

function onIframeError() {
  status.value = 'error'
  emit('error', 'Failed to load code-server')
}

onBeforeUnmount(() => {
  emit('disconnected')
})
</script>

<template>
  <div class="code-server-view relative w-full h-full">
    <div
      v-if="status === 'loading' && enabled"
      class="absolute inset-0 flex items-center justify-center bg-zinc-900 z-10"
    >
      <div class="text-zinc-400 text-sm">Loading VS Code...</div>
    </div>

    <div
      v-if="status === 'error' || !enabled"
      class="absolute inset-0 flex items-center justify-center bg-zinc-900"
    >
      <div class="text-zinc-500 text-sm">
        {{ !enabled ? 'Code-server not available' : 'Connection failed' }}
      </div>
    </div>

    <iframe
      v-if="enabled && iframeSrc"
      ref="iframeRef"
      :src="iframeSrc"
      class="w-full h-full border-0"
      allow="clipboard-read; clipboard-write"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>
