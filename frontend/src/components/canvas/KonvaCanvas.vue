<template>
  <div
    ref="containerRef"
    class="konva-canvas-container"
    :style="containerStyle"
    role="img"
    :aria-label="ariaLabel"
  >
    <v-stage
      ref="stageRef"
      :config="stageConfig"
      @mousedown="handleMouseDown"
      @mouseup="handleMouseUp"
      @mousemove="handleMouseMove"
      @touchstart="handleTouchStart"
      @touchend="handleTouchEnd"
      @touchmove="handleTouchMove"
      @wheel="handleWheel"
    >
      <slot :width="width" :height="height" :colors="colors" />
    </v-stage>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import type Konva from 'konva'
import { useThemeColors } from '@/utils/themeColors'

interface Props {
  /** Fixed width or 'auto' for responsive */
  width?: number | 'auto'
  /** Fixed height or 'auto' for responsive */
  height?: number | 'auto'
  /** Minimum width when responsive */
  minWidth?: number
  /** Minimum height when responsive */
  minHeight?: number
  /** Accessibility label */
  ariaLabel?: string
  /** Enable touch events */
  enableTouch?: boolean
  /** Enable wheel events */
  enableWheel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  width: 'auto',
  height: 'auto',
  minWidth: 100,
  minHeight: 50,
  ariaLabel: 'Canvas visualization',
  enableTouch: true,
  enableWheel: true,
})

const emit = defineEmits<{
  (e: 'resize', width: number, height: number): void
  (e: 'mousedown', event: Konva.KonvaEventObject<MouseEvent>): void
  (e: 'mouseup', event: Konva.KonvaEventObject<MouseEvent>): void
  (e: 'mousemove', event: Konva.KonvaEventObject<MouseEvent>): void
  (e: 'touchstart', event: Konva.KonvaEventObject<TouchEvent>): void
  (e: 'touchend', event: Konva.KonvaEventObject<TouchEvent>): void
  (e: 'touchmove', event: Konva.KonvaEventObject<TouchEvent>): void
  (e: 'wheel', event: Konva.KonvaEventObject<WheelEvent>): void
}>()

// Refs
const containerRef = ref<HTMLElement | null>(null)
const stageRef = ref<{ getNode: () => Konva.Stage } | null>(null)

// Responsive dimensions
const containerWidth = ref(0)
const containerHeight = ref(0)

// Theme colors
const { colors } = useThemeColors()

// Computed dimensions
const width = computed(() => {
  if (typeof props.width === 'number') return props.width
  return Math.max(containerWidth.value, props.minWidth)
})

const height = computed(() => {
  if (typeof props.height === 'number') return props.height
  return Math.max(containerHeight.value, props.minHeight)
})

// Stage configuration
const stageConfig = computed(() => ({
  width: width.value,
  height: height.value,
}))

// Container style
const containerStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : '100%',
  height: typeof props.height === 'number' ? `${props.height}px` : '100%',
}))

// Resize observer
let resizeObserver: ResizeObserver | null = null

const updateSize = () => {
  if (!containerRef.value) return

  const rect = containerRef.value.getBoundingClientRect()
  const newWidth = Math.floor(rect.width)
  const newHeight = Math.floor(rect.height)

  if (newWidth !== containerWidth.value || newHeight !== containerHeight.value) {
    containerWidth.value = newWidth
    containerHeight.value = newHeight
    emit('resize', newWidth, newHeight)
  }
}

// Event handlers with normalization
const handleMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
  emit('mousedown', e)
}

const handleMouseUp = (e: Konva.KonvaEventObject<MouseEvent>) => {
  emit('mouseup', e)
}

const handleMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
  emit('mousemove', e)
}

const handleTouchStart = (e: Konva.KonvaEventObject<TouchEvent>) => {
  if (!props.enableTouch) return
  emit('touchstart', e)
}

const handleTouchEnd = (e: Konva.KonvaEventObject<TouchEvent>) => {
  if (!props.enableTouch) return
  emit('touchend', e)
}

const handleTouchMove = (e: Konva.KonvaEventObject<TouchEvent>) => {
  if (!props.enableTouch) return
  emit('touchmove', e)
}

const handleWheel = (e: Konva.KonvaEventObject<WheelEvent>) => {
  if (!props.enableWheel) return
  emit('wheel', e)
}

// Lifecycle
onMounted(() => {
  if (typeof props.width === 'number' && typeof props.height === 'number') {
    // Fixed dimensions, no need for resize observer
    containerWidth.value = props.width
    containerHeight.value = props.height
    return
  }

  // Set up resize observer for responsive sizing
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateSize()
    })
    resizeObserver.observe(containerRef.value)
    updateSize()
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()

  // Destroy Konva stage to prevent memory leaks
  if (stageRef.value) {
    const stage = stageRef.value.getNode()
    stage.destroy()
  }
})

// Watch for prop changes
watch(
  () => [props.width, props.height],
  () => {
    if (typeof props.width === 'number' && typeof props.height === 'number') {
      containerWidth.value = props.width
      containerHeight.value = props.height
    }
  }
)

// Expose methods and properties
defineExpose({
  getStage: () => stageRef.value?.getNode(),
  getContainer: () => containerRef.value,
  width,
  height,
  colors,
  refresh: updateSize,
})
</script>

<style scoped>
.konva-canvas-container {
  position: relative;
  overflow: hidden;
}

.konva-canvas-container :deep(canvas) {
  display: block;
}
</style>
