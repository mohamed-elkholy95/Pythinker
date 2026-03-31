<template>
  <div class="vnc-viewer">
    <!-- Connecting overlay -->
    <Transition name="vnc-fade">
      <div v-if="isConnecting" class="vnc-overlay">
        <div class="vnc-overlay-content">
          <Loader2 :size="24" class="animate-spin text-[var(--icon-secondary)]" />
          <span class="text-sm text-[var(--text-secondary)]">Connecting to desktop...</span>
        </div>
      </div>
    </Transition>

    <!-- Error overlay -->
    <Transition name="vnc-fade">
      <div v-if="error" class="vnc-overlay">
        <div class="vnc-overlay-content">
          <span class="text-sm text-[var(--function-error)]">{{ error }}</span>
          <button
            class="mt-2 px-3 py-1.5 text-xs rounded-lg bg-[var(--button-secondary)] border border-[var(--border-main)] text-[var(--text-primary)] hover:bg-[var(--fill-tsp-white-dark)] transition-colors"
            @click="reconnect"
          >
            Retry
          </button>
        </div>
      </div>
    </Transition>

    <!-- noVNC renders into this container -->
    <div
      ref="vncContainerRef"
      class="vnc-canvas-container"
      :style="vncCursorStyle"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { Loader2 } from 'lucide-vue-next'
import { getVncUrl } from '@/api/agent'
import { getApplePointerCursorCss } from '@/utils/appleCursorStyle'

// noVNC RFB types — declared inline to avoid a top-level import that Vite
// would try to resolve at HMR time (the package is CJS-only).
interface RFBInstance {
  scaleViewport: boolean
  clipViewport: boolean
  resizeSession: boolean
  qualityLevel: number
  compressionLevel: number
  viewOnly: boolean
  background: string
  disconnect: () => void
  addEventListener: (event: string, handler: (e: unknown) => void) => void
  removeEventListener: (event: string, handler: (e: unknown) => void) => void
}
type RFBConstructor = new (
  target: HTMLElement,
  urlOrChannel: string,
  options?: Record<string, unknown>,
) => RFBInstance

const props = defineProps<{
  sessionId: string
  enabled: boolean
}>()

const emit = defineEmits<{
  connected: []
  disconnected: [reason?: string]
}>()

const vncContainerRef = ref<HTMLElement | null>(null)

const vncCursorStyle = { cursor: getApplePointerCursorCss() }
const isConnecting = ref(false)
const error = ref<string | null>(null)

/** x11vnc with -ncache advertises a tall framebuffer (e.g. 1280×12288); scaling it to fit looks like a paper-thin strip. */
function isAbsurdFramebuffer(width: number, height: number): boolean {
  if (width <= 0 || height <= 0) return false
  return height > width * 3 && height > 3000
}

/**
 * When the server reports an ncache-inflated height, scaleViewport scales the whole bitmap into the
 * container → unusable aspect ratio. The real desktop sits in the top band (see man x11vnc -ncache).
 * Use 1:1 pixels with viewport clipping so the visible area is the top-left of the framebuffer.
 */
function applyNcacheFramebufferWorkaround(): void {
  const canvas = vncContainerRef.value?.querySelector('canvas')
  if (!canvas || !rfb) return
  const w = canvas.width
  const h = canvas.height
  if (!isAbsurdFramebuffer(w, h)) return

  rfb.scaleViewport = false
  rfb.clipViewport = true
  const kickResize = (): void => {
    window.dispatchEvent(new Event('resize'))
  }
  requestAnimationFrame(() => {
    kickResize()
    requestAnimationFrame(kickResize)
  })
  setTimeout(kickResize, 50)
  setTimeout(kickResize, 200)
}

let rfb: RFBInstance | null = null
let RFBClass: RFBConstructor | null = null
let hasConnectedOnce = false

async function loadRFB(): Promise<RFBConstructor> {
  if (RFBClass) return RFBClass
  // Dynamic import for the noVNC RFB module
  const mod = await import('@novnc/novnc/lib/rfb.js')
  RFBClass = (mod.default || mod) as RFBConstructor
  return RFBClass
}

async function connect() {
  // Wait for DOM flush — ref may be null when called during component setup
  await nextTick()
  if (!props.sessionId || !vncContainerRef.value) return

  // Clean up any existing connection
  disconnect()

  isConnecting.value = true
  error.value = null
  hasConnectedOnce = false

  try {
    const wsUrl = await getVncUrl(props.sessionId)
    const Rfb = await loadRFB()

    await nextTick()
    if (!vncContainerRef.value || !props.enabled) return

    rfb = new Rfb(vncContainerRef.value, wsUrl, {
      wsProtocols: ['binary'],
    })

    // Configure display behavior
    rfb.scaleViewport = true
    // Keep false: resizeSession uses container size from getBoundingClientRect(). If that
    // runs before layout (width still 0), the server can get a tall-narrow resolution and
    // the UI shows as a thin vertical strip. scaleViewport alone scales the remote fb to fit.
    rfb.resizeSession = false
    rfb.qualityLevel = 6
    rfb.compressionLevel = 2
    rfb.viewOnly = false
    rfb.background = 'rgb(24, 24, 27)' // zinc-900

    rfb.addEventListener('connect', handleConnect)
    rfb.addEventListener('disconnect', handleDisconnect)
    rfb.addEventListener('credentialsrequired', handleCredentials)
  } catch (err) {
    // Connection failed
    isConnecting.value = false
    error.value = err instanceof Error ? err.message : 'Failed to connect to desktop'
    emit('disconnected', error.value)
  }
}

function disconnect() {
  if (rfb) {
    try {
      rfb.removeEventListener('connect', handleConnect)
      rfb.removeEventListener('disconnect', handleDisconnect)
      rfb.removeEventListener('credentialsrequired', handleCredentials)
      rfb.disconnect()
    } catch {
      // Ignore errors during cleanup
    }
    rfb = null
  }
}

function handleConnect() {
  isConnecting.value = false
  hasConnectedOnce = true
  error.value = null
  emit('connected')
  // Re-run layout after paint so noVNC’s ResizeObserver / autoscale sees real dimensions.
  const kickResize = (): void => {
    window.dispatchEvent(new Event('resize'))
  }
  requestAnimationFrame(() => {
    kickResize()
    requestAnimationFrame(kickResize)
  })
  setTimeout(kickResize, 100)
  setTimeout(kickResize, 400)
  setTimeout(() => {
    applyNcacheFramebufferWorkaround()
  }, 200)
}

function handleDisconnect(e: unknown) {
  isConnecting.value = false
  const detail = (e as { detail?: { clean?: boolean } })?.detail
  rfb = null

  if (detail?.clean) {
    emit('disconnected', 'Clean disconnect')
    return
  }

  // If we never connected, VNC is likely not running in the sandbox
  const reason = hasConnectedOnce
    ? 'Connection lost'
    : 'VNC is not available in the sandbox. Set ENABLE_VNC=1 and restart the sandbox.'

  if (props.enabled) {
    error.value = reason
  }
  emit('disconnected', reason)
}

function handleCredentials() {
  // Sandbox VNC has no password (x11vnc -nopw), so this shouldn't fire.
  // If it does, send empty credentials to proceed.
  if (rfb) {
    rfb.disconnect()
    error.value = 'VNC server unexpectedly requires credentials'
  }
}

function reconnect() {
  error.value = null
  void connect()
}

// Watch enabled prop — connect when enabled, disconnect when disabled
// Note: with { immediate: true }, the old value is `undefined` on the first call.
watch(
  () => [props.enabled, props.sessionId] as const,
  ([enabled, sessionId], oldValue) => {
    const [prevEnabled, prevSessionId] = oldValue ?? [false, '']
    if (enabled && sessionId) {
      if (!prevEnabled || sessionId !== prevSessionId) {
        void connect()
      }
    } else {
      disconnect()
    }
  },
  { immediate: true, flush: 'post' },
)

onBeforeUnmount(() => {
  disconnect()
})

defineExpose({ reconnect })
</script>

<style scoped>
/* Fill the absolute inset-0 parent from TakeOverView — do not override noVNC’s _screen flex;
   forcing min-width:0 on the server’s div was collapsing to a narrow column. */
.vnc-viewer {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: rgb(24, 24, 27);
}

.vnc-canvas-container {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
}

.vnc-canvas-container :deep(canvas) {
  display: block;
  cursor: inherit !important;
}

.vnc-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(24, 24, 27, 0.85);
  z-index: 10;
}

.vnc-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.vnc-fade-enter-active,
.vnc-fade-leave-active {
  transition: opacity 0.2s ease;
}

.vnc-fade-enter-from,
.vnc-fade-leave-to {
  opacity: 0;
}
</style>
