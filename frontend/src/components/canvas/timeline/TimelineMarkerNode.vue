<template>
  <v-circle
    :config="markerConfig"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
    @click="handleClick"
    @tap="handleClick"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TimelineMarker, TimelineDimensions } from '@/composables/useKonvaTimeline'
import { getMarkerConfig } from '@/composables/useKonvaTimeline'

interface Props {
  marker: TimelineMarker
  dimensions: TimelineDimensions
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'hover', markerId: string | null): void
  (e: 'click', markerId: string): void
}>()

// Computed marker configuration
const markerConfig = computed(() => ({
  ...getMarkerConfig(props.marker, props.dimensions),
  // Enable pointer cursor
  hitStrokeWidth: 10,
}))

// Event handlers
const handleMouseEnter = () => {
  emit('hover', props.marker.id)
}

const handleMouseLeave = () => {
  emit('hover', null)
}

const handleClick = () => {
  emit('click', props.marker.id)
}
</script>

<style scoped>
/* Cursor is handled by Konva, no CSS needed */
</style>
