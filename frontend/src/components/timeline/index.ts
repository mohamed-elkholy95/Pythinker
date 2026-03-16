// Timeline Replay System Components
// These components work together to provide a full timeline replay experience

export { default as TimelineContainer } from './TimelineContainer.vue'
export { default as TimelineHeader } from './TimelineHeader.vue'
export { default as TimelineControls } from './TimelineControls.vue'
export { default as TimelineProgressFooter } from './TimelineProgressFooter.vue'
export { default as TimelinePlayer } from './TimelinePlayer.vue'
export { default as TimelineMarker } from './TimelineMarker.vue'
export { default as TypedText } from './TypedText.vue'

// Re-export composables for convenience
export {
  useTimeline,
  formatTime,
  formatTimestamp,
  type TimelineMode,
  type TimelineState,
} from '@/composables/useTimeline'

export {
  useTimelineKeyboard,
  getKeyboardShortcuts,
} from '@/composables/useTimelineKeyboard'

export {
  useTypingAnimation,
  useTypewriter,
} from '@/composables/useTypingAnimation'
