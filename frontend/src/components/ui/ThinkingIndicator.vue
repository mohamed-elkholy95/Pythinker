<template>
  <div class="flex items-center gap-2">
    <div class="thinking-shape" :class="currentShape"></div>
    <span v-if="props.showText" class="text-sm font-medium text-black dark:text-white">Thinking</span>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  showText?: boolean
}>(), {
  showText: true
})

const shapes = ['circle', 'diamond', 'cube'] as const
type Shape = typeof shapes[number]

const currentShapeIndex = ref(0)
const currentShape = ref<Shape>('circle')

let intervalId: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  intervalId = setInterval(() => {
    currentShapeIndex.value = (currentShapeIndex.value + 1) % shapes.length
    currentShape.value = shapes[currentShapeIndex.value]
  }, 800)
})

onUnmounted(() => {
  if (intervalId) {
    clearInterval(intervalId)
  }
})
</script>

<style scoped>
.thinking-shape {
  width: 10px;
  height: 10px;
  background: linear-gradient(135deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  background-size: 200% 200%;
  animation: shimmer 1.5s ease-in-out infinite;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Circle */
.thinking-shape.circle {
  border-radius: 50%;
}

/* Diamond */
.thinking-shape.diamond {
  border-radius: 2px;
  transform: rotate(45deg) scale(0.85);
}

/* Cube */
.thinking-shape.cube {
  border-radius: 2px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
