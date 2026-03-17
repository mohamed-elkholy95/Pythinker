<template>
  <KonvaCanvas
    ref="canvasRef"
    :height="height"
    :min-height="minHeight"
    :aria-label="ariaLabel"
    @resize="handleResize"
    @mousedown="handleMouseDown"
    @mouseup="handleMouseUp"
    @mousemove="handleMouseMove"
  >
    <template #default="{ colors }">
      <!-- Background layer (cached for performance) -->
      <v-layer ref="backgroundLayerRef" :config="{ listening: false }">
        <!-- Track background -->
        <v-rect :config="trackConfig" />
      </v-layer>

      <!-- Markers layer -->
      <v-layer ref="markersLayerRef">
        <TimelineMarkerNode
          v-for="marker in konvaTimeline.markers.value"
          :key="marker.id"
          :marker="marker"
          :dimensions="konvaTimeline.dimensions.value"
          @hover="handleMarkerHover"
          @click="handleMarkerClick"
        />
      </v-layer>

      <!-- Scrubber layer (on top) -->
      <v-layer ref="scrubberLayerRef">
        <TimelineScrubber
          :x="konvaTimeline.scrubberX.value"
          :dimensions="konvaTimeline.dimensions.value"
          :colors="colors.timeline"
          :is-dragging="konvaTimeline.isDragging.value"
          @drag-start="handleScrubberDragStart"
          @drag="handleScrubberDrag"
          @drag-end="handleScrubberDragEnd"
        />
      </v-layer>
    </template>
  </KonvaCanvas>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, toRef } from 'vue'
import type { AgentSSEEvent } from '@/types/event'
import KonvaCanvas from '@/components/canvas/KonvaCanvas.vue'
import TimelineMarkerNode from './TimelineMarkerNode.vue'
import TimelineScrubber from './TimelineScrubber.vue'
import { useKonvaTimeline, getTrackConfig } from '@/composables/useKonvaTimeline'
import { useThemeColors } from '@/utils/themeColors'

interface Props {
  /** Events to display on timeline */
  events: AgentSSEEvent[]
  /** Timeline height */
  height?: number
  /** Minimum height */
  minHeight?: number
  /** Accessibility label */
  ariaLabel?: string
  /** Auto-follow live events */
  autoLive?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  height: 60,
  minHeight: 50,
  ariaLabel: 'Session timeline',
  autoLive: true,
})

const emit = defineEmits<{
  (e: 'seek', index: number): void
  (e: 'marker-hover', markerId: string | null): void
  (e: 'marker-click', markerId: string, event: AgentSSEEvent): void
}>()

// Refs
const canvasRef = ref<InstanceType<typeof KonvaCanvas> | null>(null)
const backgroundLayerRef = ref(null)
const markersLayerRef = ref(null)
const scrubberLayerRef = ref(null)

// Reactive ref from prop (stays in sync automatically)
const eventsRef = toRef(props, 'events')

// Theme colors
const { colors } = useThemeColors()

// Konva timeline state
const konvaTimeline = useKonvaTimeline(eventsRef, {
  autoLive: props.autoLive,
})

// Track configuration
const trackConfig = computed(() =>
  getTrackConfig(konvaTimeline.dimensions.value, colors.value.timeline)
)

// Handle resize
const handleResize = (width: number, height: number) => {
  konvaTimeline.setDimensions(width, height)
}

// Mouse event handlers for scrubbing
const handleMouseDown = (_e: unknown) => {
  if (!canvasRef.value) return

  const stage = canvasRef.value.getStage()
  if (!stage) return

  const pointer = stage.getPointerPosition()
  if (!pointer) return

  // Check if clicking on track area (not on a marker)
  const dims = konvaTimeline.dimensions.value
  const trackTop = dims.height / 2 - dims.trackHeight / 2 - 10
  const trackBottom = dims.height / 2 + dims.trackHeight / 2 + 10

  if (pointer.y >= trackTop && pointer.y <= trackBottom) {
    konvaTimeline.startDrag()
    konvaTimeline.handleScrubberDrag(pointer.x)
  }
}

const handleMouseUp = () => {
  if (konvaTimeline.isDragging.value) {
    konvaTimeline.endDrag()
  }
}

const handleMouseMove = (_e: unknown) => {
  if (!konvaTimeline.isDragging.value) return
  if (!canvasRef.value) return

  const stage = canvasRef.value.getStage()
  if (!stage) return

  const pointer = stage.getPointerPosition()
  if (!pointer) return

  konvaTimeline.handleScrubberDrag(pointer.x)
}

// Marker event handlers
const handleMarkerHover = (markerId: string | null) => {
  konvaTimeline.handleMarkerHover(markerId)
  emit('marker-hover', markerId)
}

const handleMarkerClick = (markerId: string) => {
  konvaTimeline.handleMarkerClick(markerId)

  const marker = konvaTimeline.markers.value.find((m) => m.id === markerId)
  if (marker) {
    emit('marker-click', markerId, marker.event)
  }
}

// Scrubber drag handlers
const handleScrubberDragStart = () => {
  konvaTimeline.startDrag()
}

const handleScrubberDrag = (x: number) => {
  konvaTimeline.handleScrubberDrag(x)
}

const handleScrubberDragEnd = () => {
  konvaTimeline.endDrag()
}

// Lifecycle
onMounted(() => {
  konvaTimeline.startAnimation()
})

onUnmounted(() => {
  konvaTimeline.stopAnimation()
})

// Expose timeline controls
defineExpose({
  timeline: konvaTimeline.timeline,
  play: konvaTimeline.timeline.play,
  pause: konvaTimeline.timeline.pause,
  seek: konvaTimeline.timeline.seek,
  jumpToLive: konvaTimeline.timeline.jumpToLive,
})
</script>
