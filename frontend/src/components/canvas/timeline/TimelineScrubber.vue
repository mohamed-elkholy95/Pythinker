<template>
  <v-group ref="groupRef" :config="groupConfig">
    <!-- Scrubber line -->
    <v-line :config="lineConfig" />

    <!-- Scrubber handle -->
    <v-circle
      :config="handleConfig"
      @mouseenter="handleMouseEnter"
      @mouseleave="handleMouseLeave"
      @mousedown="handleDragStart"
      @touchstart="handleDragStart"
    />
  </v-group>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type Konva from 'konva'
import type { TimelineDimensions } from '@/composables/useKonvaTimeline'
import { getScrubberConfig } from '@/composables/useKonvaTimeline'

interface Props {
  x: number
  dimensions: TimelineDimensions
  colors: {
    scrubber: string
    track: string
  }
  isDragging?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isDragging: false,
})

const emit = defineEmits<{
  (e: 'drag-start'): void
  (e: 'drag', x: number): void
  (e: 'drag-end'): void
}>()

// Refs
const groupRef = ref<{ getNode: () => Konva.Group } | null>(null)
const isHovered = ref(false)

// Computed configurations
const scrubberConfig = computed(() =>
  getScrubberConfig(props.x, props.dimensions, props.colors)
)

const groupConfig = computed(() => ({
  x: 0,
  y: 0,
  draggable: false, // We handle dragging manually via stage events
}))

const lineConfig = computed(() => ({
  ...scrubberConfig.value.line,
  opacity: props.isDragging ? 1 : 0.8,
}))

const handleConfig = computed(() => {
  const baseConfig = scrubberConfig.value.handle
  const scale = props.isDragging ? 1.2 : isHovered.value ? 1.1 : 1

  return {
    ...baseConfig,
    radius: baseConfig.radius * scale,
    hitStrokeWidth: 15, // Larger hit area for easier dragging
  }
})

// Helpers
function getStageContainer(): HTMLDivElement | null {
  const node = groupRef.value?.getNode()
  return node?.getStage()?.container() ?? null
}

// Event handlers
const handleMouseEnter = () => {
  isHovered.value = true
  const container = getStageContainer()
  if (container) container.style.cursor = 'grab'
}

const handleMouseLeave = () => {
  if (!props.isDragging) {
    isHovered.value = false
    const container = getStageContainer()
    if (container) container.style.cursor = 'default'
  }
}

const handleDragStart = (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
  e.evt?.preventDefault?.()

  const container = getStageContainer()
  if (container) container.style.cursor = 'grabbing'

  emit('drag-start')
}
</script>
