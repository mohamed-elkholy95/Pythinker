import { ref, computed, type Ref } from 'vue'
import { startTakeover } from '@/api/agent'
import { showErrorToast } from '@/utils/toast'

const TAKEOVER_WAIT_REASONS = new Set(['captcha', 'login', '2fa', 'payment', 'verification'])

/**
 * Composable that encapsulates the one-click browser-takeover CTA logic.
 *
 * @param sessionId - Reactive ref to the current session ID.
 */
export function useTakeoverCta(sessionId: Ref<string | undefined>) {
  const showTakeoverCta = ref(false)
  const takeoverCtaReason = ref<string | undefined>(undefined)
  const takeoverStarting = ref(false)

  const clearTakeoverCta = () => {
    showTakeoverCta.value = false
    takeoverCtaReason.value = undefined
  }

  const setTakeoverCtaFromMetadata = (waitReason?: string, takeoverSuggestion?: string) => {
    const normalizedReason = (waitReason || '').trim().toLowerCase()
    const normalizedSuggestion = (takeoverSuggestion || '').trim().toLowerCase()
    const shouldShow =
      normalizedSuggestion === 'browser' || TAKEOVER_WAIT_REASONS.has(normalizedReason)

    showTakeoverCta.value = shouldShow
    takeoverCtaReason.value = shouldShow && normalizedReason ? normalizedReason : undefined
  }

  const takeoverCtaMessage = computed(() => {
    switch ((takeoverCtaReason.value || '').toLowerCase()) {
      case 'captcha':
        return 'Captcha detected. Take over the browser to continue.'
      case 'login':
        return 'Login required. Take over the browser to continue.'
      case '2fa':
        return '2FA verification required. Take over the browser to continue.'
      case 'payment':
        return 'Payment verification required. Take over the browser to continue.'
      case 'verification':
        return 'Manual verification required. Take over the browser to continue.'
      default:
        return 'The agent is waiting for your browser input. Take over to continue.'
    }
  })

  const handleStartTakeoverFromCta = async () => {
    if (!sessionId.value || takeoverStarting.value) return
    takeoverStarting.value = true
    try {
      const reason = takeoverCtaReason.value || 'manual'
      const status = await startTakeover(sessionId.value, reason)
      if (status.takeover_state !== 'takeover_active') {
        showErrorToast('Unable to start browser takeover. Please try again.')
        return
      }
      clearTakeoverCta()
      window.dispatchEvent(
        new CustomEvent('takeover', {
          detail: { sessionId: sessionId.value, active: true },
        }),
      )
    } catch {
      showErrorToast('Unable to start browser takeover. Please try again.')
    } finally {
      takeoverStarting.value = false
    }
  }

  return {
    showTakeoverCta,
    takeoverCtaReason,
    takeoverStarting,
    takeoverCtaMessage,
    clearTakeoverCta,
    setTakeoverCtaFromMetadata,
    handleStartTakeoverFromCta,
  }
}
