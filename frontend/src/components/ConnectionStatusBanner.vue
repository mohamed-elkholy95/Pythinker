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

// Severity levels for styling
type Severity = 'info' | 'warning' | 'error'

const severity = computed((): Severity => {
  if (isCircuitOpen.value || hasUnrecoverableError.value) return 'error'
  if (isHalfOpen.value || props.isDegraded) return 'warning'
  return 'info'
})

// Display state
const isVisible = computed(() => {
  const hasRetryProgress = (props.retryAttempt ?? 0) > 0
  return isCircuitOpen.value || isHalfOpen.value || props.isDegraded || hasUnrecoverableError.value || hasRetryProgress
})

const statusMessage = computed(() => {
  if (isCircuitOpen.value) {
    const seconds = Math.ceil(resetTimeRemaining.value / 1000)
    return `Service unavailable \u00b7 retrying in ${seconds}s`
  }
  if (isHalfOpen.value) {
    return 'Verifying connection\u2026'
  }
  if (props.isDegraded) {
    return 'Slow response \u2014 still waiting'
  }
  if (hasUnrecoverableError.value) {
    const error = errorSummary.value.mostRecentError
    return error?.message || 'Something went wrong'
  }
  if (props.retryAttempt && props.maxRetries) {
    // Only show attempt count after 3+ retries (less anxiety for quick recoveries)
    if (props.retryAttempt >= 3) {
      return `Reconnecting \u00b7 attempt ${props.retryAttempt} of ${props.maxRetries}`
    }
    return 'Reconnecting\u2026'
  }
  return 'Connecting\u2026'
})

// Show progress bar during retry countdown
const showProgress = computed(() => {
  return (props.retryDelayMs && props.retryDelayMs > 0) || isCircuitOpen.value
})

// Progress bar percentage (100% → 0% as countdown ticks)
const progressPercent = computed(() => {
  if (isCircuitOpen.value && resetTimeRemaining.value > 0) {
    // For circuit breaker, use the reset time
    return Math.min(100, (countdown.value / Math.ceil(resetTimeRemaining.value / 1000)) * 100)
  }
  if (props.retryDelayMs && props.retryDelayMs > 0) {
    return 100 // Full bar — CSS animation handles the countdown
  }
  return 0
})

const showRefreshButton = computed(() => {
  return hasUnrecoverableError.value || (isCircuitOpen.value && resetTimeRemaining.value > 10000)
})

const showDismiss = computed(() => {
  return !isCircuitOpen.value && (hasUnrecoverableError.value || props.isDegraded)
})

// Update countdown
watch(resetTimeRemaining, (newVal) => {
  countdown.value = Math.ceil(newVal / 1000)
})

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
  errorReporter.clearErrors()
  emit('dismiss')
}

onUnmounted(() => {
  stopCountdown()
})
</script>

<template>
  <Transition name="banner-slide">
    <div
      v-if="isVisible"
      class="connection-banner"
      :class="`banner-${severity}`"
      role="status"
      aria-live="polite"
    >
      <!-- Progress bar (bottom edge of banner) -->
      <div
        v-if="showProgress"
        class="banner-progress"
        :class="`progress-${severity}`"
        :style="{
          '--progress': `${progressPercent}%`,
          '--duration': retryDelayMs ? `${retryDelayMs}ms` : '0ms'
        }"
      />

      <div class="banner-body">
        <!-- Spinner / Status indicator -->
        <div class="banner-indicator" :class="`indicator-${severity}`">
          <svg
            v-if="severity !== 'error'"
            class="banner-spinner"
            viewBox="0 0 16 16"
            fill="none"
          >
            <circle
              cx="8" cy="8" r="6"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-dasharray="28"
              stroke-dashoffset="8"
            />
          </svg>
          <svg
            v-else
            class="banner-icon-static"
            viewBox="0 0 16 16"
            fill="none"
          >
            <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5" />
            <path d="M8 4.5v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            <circle cx="8" cy="11.5" r="0.75" fill="currentColor" />
          </svg>
        </div>

        <!-- Message -->
        <span class="banner-message">{{ statusMessage }}</span>

        <!-- Actions -->
        <div class="banner-actions">
          <button
            v-if="showRefreshButton"
            class="banner-btn banner-btn-primary"
            @click="handleRefresh"
          >
            Retry now
          </button>
          <button
            v-if="showDismiss"
            class="banner-btn banner-btn-ghost"
            @click="handleDismiss"
            aria-label="Dismiss"
          >
            <svg viewBox="0 0 12 12" fill="none" width="12" height="12">
              <path d="M2.5 2.5l7 7M9.5 2.5l-7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.connection-banner {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  min-width: 280px;
  max-width: 480px;
  border-radius: 10px;
  overflow: hidden;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.12),
    0 1px 4px rgba(0, 0, 0, 0.08);
}

.banner-body {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
}

/* ── Severity variants ───────────────────────────── */
.banner-info {
  background: color-mix(in srgb, var(--background-surface, #fff) 85%, var(--function-info, #3b82f6));
  border: 1px solid color-mix(in srgb, var(--border-color, #e5e5e5) 70%, var(--function-info, #3b82f6));
  color: var(--text-primary, #111);
}

.banner-warning {
  background: color-mix(in srgb, var(--background-surface, #fff) 85%, var(--function-warning, #f79009));
  border: 1px solid color-mix(in srgb, var(--border-color, #e5e5e5) 70%, var(--function-warning, #f79009));
  color: var(--text-primary, #111);
}

.banner-error {
  background: color-mix(in srgb, var(--background-surface, #fff) 85%, var(--function-error, #ef4444));
  border: 1px solid color-mix(in srgb, var(--border-color, #e5e5e5) 70%, var(--function-error, #ef4444));
  color: var(--text-primary, #111);
}

/* ── Indicator (spinner / icon) ──────────────────── */
.banner-indicator {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.indicator-info { color: var(--function-info, #3b82f6); }
.indicator-warning { color: var(--function-warning, #f79009); }
.indicator-error { color: var(--function-error, #ef4444); }

.banner-spinner {
  width: 16px;
  height: 16px;
  animation: spin 0.8s linear infinite;
}

.banner-icon-static {
  width: 16px;
  height: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Message ─────────────────────────────────────── */
.banner-message {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--text-secondary, #555);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Actions ─────────────────────────────────────── */
.banner-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.banner-btn {
  border: none;
  cursor: pointer;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s ease;
  line-height: 1;
}

.banner-btn-primary {
  padding: 5px 10px;
  background: var(--function-info, #3b82f6);
  color: #fff;
}

.banner-btn-primary:hover {
  filter: brightness(1.1);
}

.banner-btn-ghost {
  padding: 4px;
  background: transparent;
  color: var(--text-tertiary, #999);
  display: flex;
  align-items: center;
  justify-content: center;
}

.banner-btn-ghost:hover {
  color: var(--text-primary, #111);
  background: var(--background-hover, rgba(0, 0, 0, 0.04));
}

/* ── Progress bar ────────────────────────────────── */
.banner-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  width: var(--progress, 100%);
  transition: width 1s linear;
}

/* Animate from 100% to 0% over the retry delay */
.banner-progress[style*="--duration"] {
  animation: progress-drain var(--duration) linear forwards;
}

.progress-info { background: var(--function-info, #3b82f6); }
.progress-warning { background: var(--function-warning, #f79009); }
.progress-error { background: var(--function-error, #ef4444); }

@keyframes progress-drain {
  from { width: 100%; }
  to { width: 0%; }
}

/* ── Transition ──────────────────────────────────── */
.banner-slide-enter-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.banner-slide-leave-active {
  transition: all 0.2s ease-in;
}

.banner-slide-enter-from {
  transform: translateX(-50%) translateY(16px);
  opacity: 0;
}

.banner-slide-leave-to {
  transform: translateX(-50%) translateY(8px);
  opacity: 0;
}
</style>
