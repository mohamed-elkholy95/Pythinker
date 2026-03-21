<template>
  <Teleport to="body">
    <Transition name="canvas-fade">
      <div
        v-if="visible"
        class="canvas-viewer-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Canvas viewer"
        @wheel.prevent="handleWheel"
      >
        <!-- Top bar -->
        <div class="canvas-viewer-modal__top-bar">
          <CanvasZoomControls
            :zoom="zoom"
            @zoom-in="zoomIn"
            @zoom-out="zoomOut"
            @zoom-reset="zoomReset"
            @settings-click="handleSettingsClick"
          />

          <div class="canvas-viewer-modal__top-actions">
            <button
              type="button"
              class="canvas-viewer-modal__icon-btn"
              aria-label="Toggle fullscreen"
              @click="toggleFullscreen"
            >
              <Maximize2 :size="16" />
            </button>
            <button
              type="button"
              class="canvas-viewer-modal__icon-btn"
              aria-label="Close viewer"
              @click="emit('close')"
            >
              <X :size="16" />
            </button>
          </div>
        </div>

        <!-- Content area -->
        <div
          class="canvas-viewer-modal__content"
          @click.self="selected = false"
          @dblclick="handleDoubleClick"
        >
          <div class="canvas-viewer-modal__centered">
            <CanvasImageActionBar
              @download="emit('download')"
            />

            <CanvasImageFrame
              :image-url="imageUrl"
              :filename="filename"
              :width="width"
              :height="height"
              :zoom="zoom"
              :selected="selected"
              @click.stop
            />
          </div>
        </div>

        <!-- Bottom toolbar -->
        <CanvasBottomToolbar
          :active-tool="activeTool"
          @tool-change="handleToolChange"
        />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { Maximize2, X } from 'lucide-vue-next'

import CanvasZoomControls from './CanvasZoomControls.vue'
import CanvasBottomToolbar from './CanvasBottomToolbar.vue'
import CanvasImageActionBar from './CanvasImageActionBar.vue'
import CanvasImageFrame from './CanvasImageFrame.vue'

interface Props {
  visible: boolean
  imageUrl: string
  filename: string
  width: number
  height: number
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'download'): void
}>()

const zoom = ref(0.72)
const activeTool = ref<'select' | 'hand'>('select')
const selected = ref(true)

const ZOOM_STEP = 0.10
const ZOOM_MIN = 0.1
const ZOOM_MAX = 5.0

function clampZoom(value: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, value))
}

function zoomIn(): void {
  zoom.value = clampZoom(zoom.value + ZOOM_STEP)
}

function zoomOut(): void {
  zoom.value = clampZoom(zoom.value - ZOOM_STEP)
}

function zoomReset(): void {
  zoom.value = computeFitZoom()
}

function computeFitZoom(): number {
  const padX = 96
  const padY = 180
  const availW = window.innerWidth - padX
  const availH = window.innerHeight - padY
  if (props.width <= 0 || props.height <= 0) return 0.72
  const fitW = availW / props.width
  const fitH = availH / props.height
  return clampZoom(Math.min(fitW, fitH, 1))
}

function handleWheel(event: WheelEvent): void {
  const delta = event.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
  zoom.value = clampZoom(zoom.value + delta)
}

function handleToolChange(tool: 'select' | 'hand'): void {
  activeTool.value = tool
}

function handleSettingsClick(): void {
  // Placeholder for future settings panel
}

function toggleFullscreen(): void {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {
      // Fullscreen request denied — no action needed
    })
  } else {
    document.exitFullscreen().catch(() => {
      // Exit fullscreen failed — no action needed
    })
  }
}

function handleDoubleClick(): void {
  const fitZoom = computeFitZoom()
  zoom.value = Math.abs(zoom.value - 1.0) < 0.05 ? fitZoom : 1.0
}

function handleKeydown(event: KeyboardEvent): void {
  if (!props.visible) return

  const tag = (event.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || (event.target as HTMLElement)?.isContentEditable) return

  if ((event.metaKey || event.ctrlKey) && event.key === 's') {
    event.preventDefault()
    emit('download')
    return
  }

  switch (event.key) {
    case 'Escape':
      emit('close')
      break
    case 'v':
    case 'V':
      activeTool.value = 'select'
      break
    case 'h':
    case 'H':
      activeTool.value = 'hand'
      break
    case '+':
    case '=':
      zoomIn()
      break
    case '-':
      zoomOut()
      break
    case '0':
      zoomReset()
      break
  }
}

watch(
  () => props.visible,
  (isVisible) => {
    if (isVisible) {
      document.body.style.overflow = 'hidden'
      zoom.value = computeFitZoom()
      selected.value = true
    } else {
      document.body.style.overflow = ''
    }
  },
)

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.canvas-viewer-modal {
  position: fixed;
  inset: 0;
  z-index: 50000;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

:global(.dark) .canvas-viewer-modal {
  background: #1a1a1a;
}

.canvas-viewer-modal__top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
  flex-shrink: 0;
  z-index: 10;
}

.canvas-viewer-modal__top-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.canvas-viewer-modal__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-main);
  border-radius: var(--radius-full);
  background: var(--fill-tsp-white-main);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}

.canvas-viewer-modal__icon-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.canvas-viewer-modal__content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  padding: var(--space-4);
}

.canvas-viewer-modal__centered {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

/* Transition */
.canvas-fade-enter-active,
.canvas-fade-leave-active {
  transition: opacity 0.2s ease;
}

.canvas-fade-enter-from,
.canvas-fade-leave-to {
  opacity: 0;
}
</style>
