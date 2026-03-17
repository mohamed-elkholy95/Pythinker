<template>
  <span class="typed-text">
    <span>{{ displayedText }}</span>
    <span
      v-if="showCursor && isTyping"
      class="cursor"
      :class="{ 'animate-blink': !isTyping }"
    >|</span>
  </span>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTypingAnimation } from '@/composables/useTypingAnimation'

interface Props {
  /** Text to display with typing effect */
  text: string
  /** Characters per second (default: 60) */
  speed?: number
  /** Delay before starting in ms */
  delay?: number
  /** Whether to show cursor */
  showCursor?: boolean
  /** Whether to animate (false = show immediately) */
  animate?: boolean
  /** Auto-start animation on mount */
  autoStart?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  speed: 60,
  delay: 0,
  showCursor: true,
  animate: true,
  autoStart: true,
})

const emit = defineEmits<{
  start: []
  complete: []
  skip: []
}>()

const textRef = ref(props.text)

// Watch for text prop changes
watch(() => props.text, (newText) => {
  textRef.value = newText
})

const {
  displayedText,
  isTyping,
  isComplete,
  start,
  skip,
  reset,
} = useTypingAnimation(textRef, {
  speed: props.speed,
  startDelay: props.delay,
  animate: props.animate,
})

// Watch for completion
watch(isComplete, (complete) => {
  if (complete) {
    emit('complete')
  }
})

// Auto-start on mount
onMounted(() => {
  if (props.autoStart && props.animate) {
    emit('start')
    start()
  } else if (!props.animate) {
    // Show full text immediately
    skip()
  }
})

// Expose methods for parent control
defineExpose({
  start,
  skip,
  reset,
  isTyping,
  isComplete,
})
</script>

<style scoped>
.typed-text {
  white-space: pre-wrap;
}

.cursor {
  display: inline-block;
  margin-left: 1px;
  font-weight: normal;
}

@keyframes blink {
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
    opacity: 0;
  }
}

.animate-blink {
  animation: blink 1s step-end infinite;
}
</style>
