import { onMounted, onUnmounted, ref } from 'vue'
import type { TimelineState } from './useTimeline'

export interface TimelineKeyboardOptions {
  /** Enable keyboard shortcuts (default: true) */
  enabled?: boolean
  /** Step size for Shift+Arrow (default: 10) */
  jumpStep?: number
  /** Speed presets for number keys 1-4 (default: [0.5, 1, 2, 4]) */
  speedPresets?: number[]
}

/**
 * Composable for timeline keyboard shortcuts.
 *
 * Shortcuts:
 * - Space: Play/Pause toggle
 * - Left Arrow: Step backward
 * - Right Arrow: Step forward
 * - Shift + Left: Jump backward 10 events
 * - Shift + Right: Jump forward 10 events
 * - Home: Jump to start
 * - End: Jump to end / Jump to live
 * - 1-4: Set playback speed (0.5x, 1x, 2x, 4x)
 * - L: Jump to live mode
 * - Escape: Stop playback
 */
export function useTimelineKeyboard(
  timeline: TimelineState,
  options: TimelineKeyboardOptions = {}
) {
  const {
    enabled = true,
    jumpStep = 10,
    speedPresets = [0.5, 1, 2, 4],
  } = options

  const isEnabled = ref(enabled)

  // Track if we're in an input element to avoid conflicts
  const isInInputElement = (event: KeyboardEvent): boolean => {
    const target = event.target as HTMLElement
    if (!target) return false

    const tagName = target.tagName.toLowerCase()
    const isEditable = target.isContentEditable

    return (
      tagName === 'input' ||
      tagName === 'textarea' ||
      tagName === 'select' ||
      isEditable
    )
  }

  const handleKeyDown = (event: KeyboardEvent) => {
    if (!isEnabled.value) return

    // Don't handle shortcuts when in input elements
    if (isInInputElement(event)) return

    const { key, shiftKey } = event

    switch (key) {
      case ' ':
        // Space: Play/Pause toggle
        event.preventDefault()
        if (timeline.isPlaying.value) {
          timeline.pause()
        } else {
          timeline.play()
        }
        break

      case 'ArrowLeft':
        event.preventDefault()
        if (shiftKey) {
          // Shift + Left: Jump backward
          const newIndex = Math.max(0, timeline.currentIndex.value - jumpStep)
          timeline.seek(newIndex)
        } else {
          // Left: Step backward
          timeline.stepBackward()
        }
        break

      case 'ArrowRight':
        event.preventDefault()
        if (shiftKey) {
          // Shift + Right: Jump forward
          const maxIndex = Math.max(0, (timeline as any).events?.value?.length - 1 || 0)
          const newIndex = Math.min(maxIndex, timeline.currentIndex.value + jumpStep)
          timeline.seek(newIndex)
        } else {
          // Right: Step forward
          timeline.stepForward()
        }
        break

      case 'Home':
        // Home: Jump to start
        event.preventDefault()
        timeline.seek(0)
        break

      case 'End':
        // End: Jump to live
        event.preventDefault()
        timeline.jumpToLive()
        break

      case 'l':
      case 'L':
        // L: Jump to live mode
        event.preventDefault()
        timeline.jumpToLive()
        break

      case 'Escape':
        // Escape: Stop playback
        event.preventDefault()
        timeline.stop()
        break

      case '1':
      case '2':
      case '3':
      case '4':
        // Number keys 1-4: Set playback speed
        event.preventDefault()
        {
          const speedIndex = parseInt(key) - 1
          if (speedIndex >= 0 && speedIndex < speedPresets.length) {
            timeline.setSpeed(speedPresets[speedIndex])
          }
        }
        break
    }
  }

  onMounted(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleKeyDown)
    }
  })

  onUnmounted(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', handleKeyDown)
    }
  })

  return {
    /** Whether keyboard shortcuts are enabled */
    isEnabled,

    /** Enable keyboard shortcuts */
    enable: () => {
      isEnabled.value = true
    },

    /** Disable keyboard shortcuts */
    disable: () => {
      isEnabled.value = false
    },

    /** Toggle keyboard shortcuts */
    toggle: () => {
      isEnabled.value = !isEnabled.value
    },
  }
}

/**
 * Get a formatted list of keyboard shortcuts for display in UI
 */
export function getKeyboardShortcuts(): Array<{ key: string; description: string }> {
  return [
    { key: 'Space', description: 'Play / Pause' },
    { key: '←', description: 'Step backward' },
    { key: '→', description: 'Step forward' },
    { key: 'Shift + ←', description: 'Jump backward 10 events' },
    { key: 'Shift + →', description: 'Jump forward 10 events' },
    { key: 'Home', description: 'Jump to start' },
    { key: 'End', description: 'Jump to live' },
    { key: 'L', description: 'Jump to live mode' },
    { key: '1', description: 'Speed 0.5x' },
    { key: '2', description: 'Speed 1x' },
    { key: '3', description: 'Speed 2x' },
    { key: '4', description: 'Speed 4x' },
    { key: 'Esc', description: 'Stop playback' },
  ]
}
