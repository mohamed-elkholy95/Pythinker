<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { getSseCircuitBreaker } from '@/composables/useCircuitBreaker'
import { getErrorReporter } from '@/composables/useErrorReporter'

const props = defineProps<{
  sessionId?: string
  retryAttempt?: number
  maxRetries?: number
  retryDelayMs?: number
  isDegraded?: boolean
}>()

const emit = defineEmits<{
  (e: 'refresh'): void
  (e: 'dismiss'): void
}>()

const circuitBreaker = getSseCircuitBreaker()
const errorReporter = getErrorReporter()

// Local state
const countdown = ref(0)
let countdownInterval: ReturnType<typeof setInterval> | null = null

// Circuit breaker state
const circuitState = computed(() => circuitBreaker.state.value)
const resetTimeRemaining = computed(() => circuitBreaker.resetTimeRemaining.value)
const isCircuitOpen = computed(() => circuitState.value === 'open')
const isHalfOpen = computed(() => circuitState.value === 'half-open')

// Error summary
const errorSummary = computed(() => errorReporter.summary.value)
const hasUnrecoverableError = computed(() => errorSummary.value.unrecoverableCount > 0)

// Display state
const isVisible = computed(() => {
  const hasRetryProgress = (props.retryAttempt ?? 0) > 0
  return isCircuitOpen.value || isHalfOpen.value || props.isDegraded || hasUnrecoverableError.value || hasRetryProgress
})

const statusMessage = computed(() => {
  if (isCircuitOpen.value) {
    const seconds = Math.ceil(resetTimeRemaining.value / 1000)
    return `Backend temporarily unavailable. Retrying in ${seconds}s...`
  }
  if (isHalfOpen.value) {
    return 'Testing connection...'
  }
  if (props.isDegraded) {
    return 'Stream may be slow. Waiting for response...'
  }
  if (hasUnrecoverableError.value) {
    const error = errorSummary.value.mostRecentError
    return error?.message || 'An error occurred'
  }
  if (props.retryAttempt && props.maxRetries) {
    return `Reconnecting... (attempt ${props.retryAttempt}/${props.maxRetries})`
  }
  return 'Connecting...'
})

const statusIcon = computed(() => {
  if (isCircuitOpen.value) return '⚠️'
  if (isHalfOpen.value) return '🔄'
  if (props.isDegraded) return '⏳'
  if (hasUnrecoverableError.value) return '❌'
  return '🔄'
})

const statusClass = computed(() => {
  if (isCircuitOpen.value) return 'status-error'
  if (isHalfOpen.value) return 'status-warning'
  if (props.isDegraded) return 'status-warning'
  if (hasUnrecoverableError.value) return 'status-error'
  return 'status-info'
})

const showRefreshButton = computed(() => {
  return hasUnrecoverableError.value || (isCircuitOpen.value && resetTimeRemaining.value > 10000)
})

// Update countdown
watch(resetTimeRemaining, (newVal) => {
  countdown.value = Math.ceil(newVal / 1000)
})

// Start countdown interval
function startCountdown() {
  if (countdownInterval) return
  countdownInterval = setInterval(() => {
    if (countdown.value > 0) {
      countdown.value -= 1
    }
  }, 1000)
}

function stopCountdown() {
  if (countdownInterval) {
    clearInterval(countdownInterval)
    countdownInterval = null
  }
}

// Watch circuit state to start/stop countdown
watch(isCircuitOpen, (isOpen) => {
  if (isOpen) {
    countdown.value = Math.ceil(resetTimeRemaining.value / 1000)
    startCountdown()
  } else {
    stopCountdown()
  }
}, { immediate: true })

function handleRefresh() {
  circuitBreaker.forceClose()
  emit('refresh')
}

function handleDismiss() {
  // Clear errors from the reporter so the banner actually goes away.
  // Without this, unrecoverable errors persist in the reporter and
  // the banner stays visible even after the user clicks dismiss.
  errorReporter.clearErrors()
  emit('dismiss')
}

onUnmounted(() => {
  stopCountdown()
})
</script>

<template>
  <Transition name="slide-down">
    <div v-if="isVisible" class="connection-status-banner" :class="statusClass">
      <div class="status-content">
        <span class="status-icon">{{ statusIcon }}</span>
        <span class="status-message">{{ statusMessage }}</span>
        <div v-if="retryDelayMs && retryDelayMs > 0" class="retry-info">
          Next retry in {{ Math.ceil(retryDelayMs / 1000) }}s
        </div>
      </div>
      <div class="status-actions">
        <button
          v-if="showRefreshButton"
          class="refresh-button"
          @click="handleRefresh"
        >
          Refresh &amp; Resume
        </button>
        <button
          v-if="!isCircuitOpen"
          class="dismiss-button"
          @click="handleDismiss"
          title="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.connection-status-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.status-info {
  background-color: #e6f7ff;
  border-bottom: 1px solid #91d5ff;
  color: #0050b3;
}

.status-warning {
  background-color: #fffbe6;
  border-bottom: 1px solid #ffe58f;
  color: #ad8b00;
}

.status-error {
  background-color: #fff2f0;
  border-bottom: 1px solid #ffccc7;
  color: #cf1322;
}

.status-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-icon {
  font-size: 16px;
}

.status-message {
  font-weight: 500;
}

.retry-info {
  font-size: 12px;
  opacity: 0.8;
  margin-left: 8px;
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-button {
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background-color: #1890ff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.refresh-button:hover {
  background-color: #40a9ff;
}

.dismiss-button {
  padding: 4px 8px;
  font-size: 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.dismiss-button:hover {
  opacity: 1;
}

/* Transitions */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
