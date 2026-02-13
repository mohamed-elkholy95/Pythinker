<template>
  <SandboxViewer
    v-if="activeRenderer === 'cdp'"
    :key="`cdp-${sessionId}`"
    :session-id="sessionId"
    :enabled="enabled"
    :view-only="viewOnly"
    :quality="quality"
    :max-fps="maxFps"
    :show-stats="showStats"
    @connected="emit('connected')"
    @disconnected="handleCdpDisconnected"
    @error="handleCdpError"
  />
  <VNCViewer
    v-else
    :key="`vnc-${sessionId}-${vncKey}`"
    :session-id="sessionId"
    :enabled="enabled"
    :view-only="viewOnly"
    :compact-loading="compactLoading"
    :reconnect-attempt="vncReconnectAttempts"
    @connected="handleVncConnected"
    @disconnected="handleVncDisconnected"
    @credentialsRequired="emit('credentialsRequired')"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import SandboxViewer from '@/components/SandboxViewer.vue'
import VNCViewer from '@/components/VNCViewer.vue'

type LiveRenderer = 'cdp' | 'vnc'
const CDP_BLOCK_TTL_MS = 60_000
const MAX_VNC_RECONNECT_ATTEMPTS = 30  // Increased from 5 to handle long recovery times (browser crashes, etc.)
const cdpBlockedUntil = new Map<string, number>()

const props = withDefaults(
  defineProps<{
    sessionId?: string
    enabled?: boolean
    viewOnly?: boolean
    quality?: number
    maxFps?: number
    showStats?: boolean
    prefer?: LiveRenderer
    allowFallback?: boolean
    compactLoading?: boolean
  }>(),
  {
    sessionId: '',
    enabled: true,
    viewOnly: true,
    quality: 70,
    maxFps: 15,
    showStats: false,
    allowFallback: true,
    compactLoading: false
  }
)

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
  error: [error: string]
  credentialsRequired: []
  fallback: [renderer: LiveRenderer, reason?: string]
}>()

const envRenderer = computed<LiveRenderer>(() => {
  const value = (import.meta.env.VITE_LIVE_RENDERER || '').toLowerCase()
  return value === 'vnc' ? 'vnc' : 'cdp'
})

const preferredRenderer = computed<LiveRenderer>(() => props.prefer ?? envRenderer.value)
const vncKey = ref(0)
const vncReconnectAttempts = ref(0)
let vncReconnectTimer: number | null = null

const isCdpBlockedForSession = (sessionId: string): boolean => {
  if (!sessionId) return false
  const blockedUntil = cdpBlockedUntil.get(sessionId)
  if (!blockedUntil) return false
  if (Date.now() > blockedUntil) {
    cdpBlockedUntil.delete(sessionId)
    return false
  }
  return true
}

const resolveRenderer = (preferred: LiveRenderer, sessionId: string): LiveRenderer => {
  if (preferred === 'cdp' && isCdpBlockedForSession(sessionId)) {
    return 'vnc'
  }
  return preferred
}

const activeRenderer = ref<LiveRenderer>(resolveRenderer(preferredRenderer.value, props.sessionId || ''))

watch(
  () => [props.sessionId, props.enabled, preferredRenderer.value] as const,
  ([sessionId, enabled, preferred], [prevSessionId]) => {
    if (vncReconnectTimer) {
      window.clearTimeout(vncReconnectTimer)
      vncReconnectTimer = null
    }
    vncReconnectAttempts.value = 0
    if (!enabled || sessionId !== prevSessionId || activeRenderer.value !== preferred) {
      activeRenderer.value = resolveRenderer(preferred, sessionId || '')
    }
  }
)

const fallbackEnabled = computed(() => props.allowFallback && preferredRenderer.value === 'cdp')

const shouldBlockCdp = (reason?: string): boolean => {
  if (!reason) return true
  const text = reason.toLowerCase()
  return (
    text.includes('404') ||
    text.includes('not found') ||
    text.includes('failed to initialize') ||
    text.includes('failed to connect') ||
    text.includes('connection error')
  )
}

const blockCdpForCurrentSession = (): void => {
  if (!props.sessionId) return
  cdpBlockedUntil.set(props.sessionId, Date.now() + CDP_BLOCK_TTL_MS)
}

const handleCdpDisconnected = (reason?: string) => {
  emit('disconnected', reason)
  if (!fallbackEnabled.value || activeRenderer.value === 'vnc') return
  if (shouldBlockCdp(reason)) {
    blockCdpForCurrentSession()
  }
  console.warn('[LiveViewer] CDP disconnected, falling back to VNC', { reason })
  activeRenderer.value = 'vnc'
  vncKey.value++
  emit('fallback', 'vnc', reason)
}

const handleCdpError = (error: string) => {
  emit('error', error)
  if (!fallbackEnabled.value || activeRenderer.value === 'vnc') return
  if (shouldBlockCdp(error)) {
    blockCdpForCurrentSession()
  }
  console.warn('[LiveViewer] CDP error, falling back to VNC', { error })
  activeRenderer.value = 'vnc'
  vncKey.value++
  emit('fallback', 'vnc', error)
}

const handleVncConnected = () => {
  if (vncReconnectTimer) {
    window.clearTimeout(vncReconnectTimer)
    vncReconnectTimer = null
  }
  vncReconnectAttempts.value = 0
  emit('connected')
}

const handleVncDisconnected = (reason?: string) => {
  emit('disconnected', reason)
  if (!props.enabled || activeRenderer.value !== 'vnc') return
  if (vncReconnectAttempts.value >= MAX_VNC_RECONNECT_ATTEMPTS) return

  const delayMs = Math.min(1000 * Math.pow(2, vncReconnectAttempts.value), 10000)
  vncReconnectAttempts.value += 1

  if (vncReconnectTimer) {
    window.clearTimeout(vncReconnectTimer)
  }

  vncReconnectTimer = window.setTimeout(() => {
    vncKey.value += 1
  }, delayMs)
}

onBeforeUnmount(() => {
  if (vncReconnectTimer) {
    window.clearTimeout(vncReconnectTimer)
    vncReconnectTimer = null
  }
})
</script>
