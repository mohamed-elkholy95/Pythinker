<template>
  <div
    ref="containerRef"
    class="lottie-animation"
    :class="[sizeClass, { 'is-loading': !isLoaded }]"
    :style="customSizeStyle"
    :aria-label="ariaLabel"
    role="img"
  >
    <!-- Loading skeleton -->
    <div v-if="!isLoaded" class="lottie-skeleton">
      <slot name="loading">
        <div class="skeleton-pulse"></div>
      </slot>
    </div>

    <!-- Fallback for reduced motion -->
    <slot v-if="reducedMotion && isLoaded" name="reduced-motion">
      <!-- Default: show first frame (handled by useLottie) -->
    </slot>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useLottie } from '@/composables/useLottie'
import type { AnimationKey } from '@/assets/animations'
import { loadAnimation } from '@/assets/animations'

// Predefined sizes for the animation container
type SizeKey = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl'

interface Props {
  /** Animation key from registry */
  animation?: AnimationKey
  /** Custom animation data (JSON object) */
  animationData?: object
  /** Custom animation path */
  animationPath?: string
  /** Predefined size */
  size?: SizeKey
  /** Custom width (overrides size) */
  width?: number
  /** Custom height (overrides size) */
  height?: number
  /** Auto-play animation */
  autoplay?: boolean
  /** Loop animation */
  loop?: boolean
  /** Playback speed */
  speed?: number
  /** Accessibility label */
  ariaLabel?: string
  /** Respect reduced motion preference */
  respectReducedMotion?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  autoplay: true,
  loop: true,
  speed: 1,
  ariaLabel: 'Animation',
  respectReducedMotion: true,
})

// Container ref
const containerRef = ref<HTMLElement | null>(null)

// Animation data state
const loadedAnimationData = ref<object | null>(null)

// Load animation from registry if using animation key
watch(
  () => props.animation,
  async (animationKey) => {
    if (animationKey) {
      try {
        const data = await loadAnimation(animationKey)
        loadedAnimationData.value = data
      } catch (error) {
        console.error(`Failed to load animation: ${animationKey}`, error)
      }
    }
  },
  { immediate: true }
)

// Determine animation source
const effectiveAnimationData = computed(() => {
  if (props.animationData) return props.animationData
  if (loadedAnimationData.value) return loadedAnimationData.value
  return undefined
})

const effectivePath = computed(() => {
  if (effectiveAnimationData.value) return undefined
  return props.animationPath
})

// Initialize Lottie
const {
  isLoaded,
  isPlaying,
  reducedMotion,
  play,
  pause,
  stop,
  setSpeed,
  goToAndPlay,
  goToAndStop,
} = useLottie({
  container: containerRef,
  animationData: effectiveAnimationData.value,
  path: effectivePath.value,
  autoplay: props.autoplay,
  loop: props.loop,
  speed: props.speed,
  respectReducedMotion: props.respectReducedMotion,
})

// Watch for animation data changes
watch(effectiveAnimationData, (newData) => {
  if (newData && containerRef.value) {
    // useLottie will handle reinitialization via its watch
  }
})

// Size classes and styles
const sizeClass = computed(() => {
  if (props.width || props.height) return ''
  return `size-${props.size}`
})

const customSizeStyle = computed(() => {
  if (props.width || props.height) {
    return {
      width: props.width ? `${props.width}px` : undefined,
      height: props.height ? `${props.height}px` : undefined,
    }
  }
  return undefined
})

// Expose control methods
defineExpose({
  play,
  pause,
  stop,
  setSpeed,
  goToAndPlay,
  goToAndStop,
  isPlaying,
  isLoaded,
  reducedMotion,
})
</script>

<style scoped>
.lottie-animation {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

/* Predefined sizes */
.size-xs {
  width: 24px;
  height: 24px;
}

.size-sm {
  width: 32px;
  height: 32px;
}

.size-md {
  width: 48px;
  height: 48px;
}

.size-lg {
  width: 64px;
  height: 64px;
}

.size-xl {
  width: 80px;
  height: 80px;
}

.size-2xl {
  width: 120px;
  height: 120px;
}

/* Loading skeleton */
.lottie-skeleton {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.skeleton-pulse {
  width: 60%;
  height: 60%;
  border-radius: 50%;
  background: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.06) 0%,
    rgba(0, 0, 0, 0.1) 50%,
    rgba(0, 0, 0, 0.06) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
}

:global(.dark) .skeleton-pulse {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.04) 100%
  );
  background-size: 200% 100%;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

/* Hide skeleton when loaded */
.lottie-animation:not(.is-loading) .lottie-skeleton {
  display: none;
}

/* SVG styling */
.lottie-animation :deep(svg) {
  width: 100% !important;
  height: 100% !important;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .skeleton-pulse {
    animation: none;
  }
}
</style>
