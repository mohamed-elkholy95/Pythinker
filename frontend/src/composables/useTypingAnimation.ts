import { ref, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export interface TypingAnimationOptions {
  /** Characters per second (default: 60) */
  speed?: number
  /** Delay before starting in ms (default: 0) */
  startDelay?: number
  /** Pause duration at punctuation in ms (default: 100) */
  punctuationPause?: number
  /** Whether to animate (if false, shows full text immediately) */
  animate?: boolean
}

export interface TypingAnimationState {
  /** Currently displayed text */
  displayedText: Ref<string>
  /** Whether animation is in progress */
  isTyping: Ref<boolean>
  /** Whether animation is complete */
  isComplete: Ref<boolean>
  /** Progress percentage (0-100) */
  progress: Ref<number>
  /** Start the animation */
  start: () => void
  /** Pause the animation */
  pause: () => void
  /** Resume the animation */
  resume: () => void
  /** Skip to end (show full text) */
  skip: () => void
  /** Reset to beginning */
  reset: () => void
}

/**
 * Composable for typing animation effect.
 * Renders text character by character with configurable speed.
 */
export function useTypingAnimation(
  fullText: Ref<string>,
  options: TypingAnimationOptions = {}
): TypingAnimationState {
  const {
    speed = 60,
    startDelay = 0,
    punctuationPause = 100,
    animate = true,
  } = options

  const displayedText = ref('')
  const isTyping = ref(false)
  const isComplete = ref(false)
  const isPaused = ref(false)

  let charIndex = 0
  let animationTimer: ReturnType<typeof setTimeout> | null = null
  let startDelayTimer: ReturnType<typeof setTimeout> | null = null

  const progress = ref(0)

  // Calculate delay for current character
  const getCharDelay = (char: string): number => {
    const baseDelay = 1000 / speed

    // Add pause after punctuation
    if (['.', '!', '?', '\n'].includes(char)) {
      return baseDelay + punctuationPause
    }
    if ([',', ';', ':'].includes(char)) {
      return baseDelay + punctuationPause / 2
    }

    return baseDelay
  }

  // Type next character
  const typeNextChar = () => {
    if (isPaused.value || charIndex >= fullText.value.length) {
      if (charIndex >= fullText.value.length) {
        isTyping.value = false
        isComplete.value = true
      }
      return
    }

    const char = fullText.value[charIndex]
    displayedText.value += char
    charIndex++
    progress.value = (charIndex / fullText.value.length) * 100

    if (charIndex < fullText.value.length) {
      const delay = getCharDelay(char)
      animationTimer = setTimeout(typeNextChar, delay)
    } else {
      isTyping.value = false
      isComplete.value = true
    }
  }

  // Start animation
  const start = () => {
    if (!animate || !fullText.value) {
      displayedText.value = fullText.value
      isComplete.value = true
      progress.value = 100
      return
    }

    reset()
    isTyping.value = true

    if (startDelay > 0) {
      startDelayTimer = setTimeout(typeNextChar, startDelay)
    } else {
      typeNextChar()
    }
  }

  // Pause animation
  const pause = () => {
    isPaused.value = true
    if (animationTimer) {
      clearTimeout(animationTimer)
      animationTimer = null
    }
  }

  // Resume animation
  const resume = () => {
    if (!isPaused.value || isComplete.value) return
    isPaused.value = false
    typeNextChar()
  }

  // Skip to end
  const skip = () => {
    clearTimers()
    displayedText.value = fullText.value
    charIndex = fullText.value.length
    progress.value = 100
    isTyping.value = false
    isComplete.value = true
    isPaused.value = false
  }

  // Reset to beginning
  const reset = () => {
    clearTimers()
    displayedText.value = ''
    charIndex = 0
    progress.value = 0
    isTyping.value = false
    isComplete.value = false
    isPaused.value = false
  }

  // Clear all timers
  const clearTimers = () => {
    if (animationTimer) {
      clearTimeout(animationTimer)
      animationTimer = null
    }
    if (startDelayTimer) {
      clearTimeout(startDelayTimer)
      startDelayTimer = null
    }
  }

  // Watch for text changes
  watch(fullText, (newText, oldText) => {
    if (newText !== oldText) {
      if (animate && isTyping.value) {
        // If new text is appended, continue from current position
        if (newText.startsWith(displayedText.value)) {
          // Text was appended, continue typing
          return
        }
      }
      // Text changed completely, reset
      if (animate) {
        start()
      } else {
        displayedText.value = newText
        progress.value = 100
        isComplete.value = true
      }
    }
  })

  // Cleanup on unmount
  onUnmounted(() => {
    clearTimers()
  })

  return {
    displayedText,
    isTyping,
    isComplete,
    progress,
    start,
    pause,
    resume,
    skip,
    reset,
  }
}

/**
 * Simple hook for one-shot typing animation
 */
export function useTypewriter(
  text: string,
  options: TypingAnimationOptions = {}
) {
  const textRef = ref(text)
  return useTypingAnimation(textRef, options)
}
