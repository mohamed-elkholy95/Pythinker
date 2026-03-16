<template>
  <div class="absolute inset-0 bg-black/90 flex items-center justify-center overflow-hidden">
    <!-- Loading spinner -->
    <div v-if="isImageLoading" class="absolute inset-0 flex items-center justify-center z-10">
      <div class="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
    </div>

    <!-- Screenshot image -->
    <img
      v-if="src"
      :src="src"
      class="max-w-full max-h-full object-contain transition-opacity duration-200"
      :class="isImageLoading ? 'opacity-0' : 'opacity-100'"
      @load="onImageLoad"
      @error="onImageError"
      alt="Session screenshot"
      draggable="false"
    />

    <!-- No screenshot placeholder -->
    <div v-else class="text-white/50 text-sm">
      No screenshot available
    </div>

    <!-- Metadata overlay -->
    <div
      v-if="metadata"
      class="absolute bottom-0 left-0 right-0 px-3 py-2 bg-gradient-to-t from-black/70 to-transparent"
    >
      <div class="flex items-center justify-between text-white/80 text-xs">
        <div class="flex items-center gap-2">
          <span v-if="metadata.tool_name" class="bg-white/20 px-1.5 py-0.5 rounded">
            {{ metadata.tool_name }}
          </span>
          <span v-if="metadata.function_name" class="text-white/60">
            {{ metadata.function_name }}
          </span>
        </div>
        <span class="text-white/50">
          {{ formattedTime }}
        </span>
      </div>
    </div>

    <!-- Replay badge -->
    <div class="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-1 bg-black/50 rounded-full">
      <span class="w-2 h-2 rounded-full bg-gray-400" />
      <span class="text-white/70 text-[10px] font-medium uppercase tracking-wider">Replay</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ScreenshotMetadata } from '@/types/screenshot'

const props = defineProps<{
  src: string
  metadata: ScreenshotMetadata | null
}>()

const isImageLoading = ref(false)
const imageError = ref(false)

const formattedTime = computed(() => {
  if (!props.metadata?.timestamp) return ''
  const date = new Date(props.metadata.timestamp * 1000)
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
})

const onImageLoad = () => {
  isImageLoading.value = false
  imageError.value = false
}

const onImageError = () => {
  isImageLoading.value = false
  imageError.value = true
}

watch(() => props.src, (newSrc) => {
  if (newSrc) {
    isImageLoading.value = true
    imageError.value = false
  }
})
</script>
