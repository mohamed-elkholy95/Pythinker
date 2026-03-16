/**
 * Composable for Lottie animations
 *
 * Provides lazy-loaded Lottie animations with:
 * - Reduced motion support
 * - Theme awareness
 * - Automatic cleanup
 * - Control methods (play, pause, stop, etc.)
 */
import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue'
import type { AnimationItem } from 'lottie-web'

// Lazy-load lottie-web
let lottiePromise: Promise<typeof import('lottie-web')> | null = null

async function getLottie() {
  if (!lottiePromise) {
    lottiePromise = import('lottie-web')
  }
  return (await lottiePromise).default
}

/**
 * Check if user prefers reduced motion
 */
function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export interface LottieOptions {
  /** Container element ref */
  container: Ref<HTMLElement | null>
  /** Animation data (JSON) or path to JSON file */
  animationData?: object
  /** Path to animation JSON file */
  path?: string
  /** Auto-play on mount */
  autoplay?: boolean
  /** Loop animation */
  loop?: boolean
  /** Initial playback speed */
  speed?: number
  /** Renderer type (svg recommended for quality, canvas for performance) */
  renderer?: 'svg'
  /** Respect reduced motion preference */
  respectReducedMotion?: boolean
}

export interface LottieState {
  /** Animation instance */
  animation: Ref<AnimationItem | null>
  /** Whether animation is loaded */
  isLoaded: Ref<boolean>
  /** Whether animation is playing */
  isPlaying: Ref<boolean>
  /** Whether animation is paused */
  isPaused: Ref<boolean>
  /** Current frame */
  currentFrame: Ref<number>
  /** Total frames */
  totalFrames: Ref<number>
  /** Animation duration in seconds */
  duration: Ref<number>
  /** Whether reduced motion is active */
  reducedMotion: Ref<boolean>

  // Control methods
  play: () => void
  pause: () => void
  stop: () => void
  setSpeed: (speed: number) => void
  goToAndPlay: (frame: number, isFrame?: boolean) => void
  goToAndStop: (frame: number, isFrame?: boolean) => void
  setDirection: (direction: 1 | -1) => void
  destroy: () => void
}

/**
 * Composable for Lottie animations
 */
export function useLottie(options: LottieOptions): LottieState {
  const {
    container,
    animationData,
    path,
    autoplay = true,
    loop = true,
    speed = 1,
    renderer = 'svg',
    respectReducedMotion = true,
  } = options

  // State
  const animation = ref<AnimationItem | null>(null)
  const isLoaded = ref(false)
  const isPlaying = ref(false)
  const isPaused = ref(true)
  const currentFrame = ref(0)
  const totalFrames = ref(0)
  const duration = ref(0)
  const reducedMotion = ref(prefersReducedMotion())

  // Media query listener for reduced motion
  let mediaQueryList: MediaQueryList | null = null

  const handleReducedMotionChange = (e: MediaQueryListEvent) => {
    reducedMotion.value = e.matches
    if (animation.value) {
      if (e.matches) {
        // Stop on first frame when reduced motion is enabled
        animation.value.goToAndStop(0, true)
      } else if (autoplay) {
        animation.value.play()
      }
    }
  }

  // Initialize animation
  const initAnimation = async () => {
    if (!container.value) return

    try {
      const lottie = await getLottie()

      const config = {
        container: container.value,
        renderer,
        loop,
        autoplay: respectReducedMotion && reducedMotion.value ? false : autoplay,
        rendererSettings: {
          preserveAspectRatio: 'xMidYMid slice',
          progressiveLoad: true,
        },
        animationData: undefined as object | undefined,
        path: undefined as string | undefined,
      }

      if (animationData) {
        config.animationData = animationData
      } else if (path) {
        config.path = path
      } else {
        console.error('useLottie: Either animationData or path is required')
        return
      }

      animation.value = lottie.loadAnimation(config)

      // Set up event listeners
      animation.value.addEventListener('DOMLoaded', () => {
        isLoaded.value = true
        totalFrames.value = animation.value?.totalFrames ?? 0
        duration.value = animation.value?.getDuration() ?? 0

        // Set initial speed
        if (speed !== 1) {
          animation.value?.setSpeed(speed)
        }

        // Handle reduced motion on load
        if (respectReducedMotion && reducedMotion.value) {
          animation.value?.goToAndStop(0, true)
        }
      })

      animation.value.addEventListener('enterFrame', () => {
        currentFrame.value = animation.value?.currentFrame ?? 0
      })

      animation.value.addEventListener('complete', () => {
        if (!loop) {
          isPlaying.value = false
          isPaused.value = true
        }
      })

      // Update playing state
      isPlaying.value = autoplay && !(respectReducedMotion && reducedMotion.value)
      isPaused.value = !isPlaying.value
    } catch (error) {
      console.error('Failed to initialize Lottie animation:', error)
    }
  }

  // Control methods
  const play = () => {
    if (animation.value && !(respectReducedMotion && reducedMotion.value)) {
      animation.value.play()
      isPlaying.value = true
      isPaused.value = false
    }
  }

  const pause = () => {
    if (animation.value) {
      animation.value.pause()
      isPlaying.value = false
      isPaused.value = true
    }
  }

  const stop = () => {
    if (animation.value) {
      animation.value.stop()
      isPlaying.value = false
      isPaused.value = true
      currentFrame.value = 0
    }
  }

  const setSpeed = (newSpeed: number) => {
    animation.value?.setSpeed(newSpeed)
  }

  const goToAndPlay = (frame: number, isFrame = true) => {
    if (animation.value && !(respectReducedMotion && reducedMotion.value)) {
      animation.value.goToAndPlay(frame, isFrame)
      isPlaying.value = true
      isPaused.value = false
    }
  }

  const goToAndStop = (frame: number, isFrame = true) => {
    if (animation.value) {
      animation.value.goToAndStop(frame, isFrame)
      isPlaying.value = false
      isPaused.value = true
    }
  }

  const setDirection = (direction: 1 | -1) => {
    animation.value?.setDirection(direction)
  }

  const destroy = () => {
    if (animation.value) {
      animation.value.destroy()
      animation.value = null
      isLoaded.value = false
      isPlaying.value = false
      isPaused.value = true
    }
  }

  // Lifecycle
  onMounted(() => {
    // Set up reduced motion listener
    if (typeof window !== 'undefined' && respectReducedMotion) {
      mediaQueryList = window.matchMedia('(prefers-reduced-motion: reduce)')
      mediaQueryList.addEventListener('change', handleReducedMotionChange)
    }

    // Initialize when container is available
    if (container.value) {
      initAnimation()
    }
  })

  // Watch for container changes
  watch(container, (newContainer) => {
    if (newContainer && !animation.value) {
      initAnimation()
    }
  })

  // Watch for animation data/path changes
  watch(
    () => [animationData, path],
    () => {
      if (animation.value) {
        destroy()
      }
      if (container.value) {
        initAnimation()
      }
    }
  )

  onUnmounted(() => {
    mediaQueryList?.removeEventListener('change', handleReducedMotionChange)
    destroy()
  })

  return {
    animation,
    isLoaded,
    isPlaying,
    isPaused,
    currentFrame,
    totalFrames,
    duration,
    reducedMotion,
    play,
    pause,
    stop,
    setSpeed,
    goToAndPlay,
    goToAndStop,
    setDirection,
    destroy,
  }
}

/**
 * Preload lottie-web library
 */
export async function preloadLottie(): Promise<void> {
  await getLottie()
}

/**
 * Check if reduced motion is preferred
 */
export { prefersReducedMotion }
