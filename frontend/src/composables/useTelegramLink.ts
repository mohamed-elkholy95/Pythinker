import { computed, onUnmounted, ref } from 'vue'
import { generateLinkCode, getLinkedChannels } from '@/api/channelLinks'
import type { LinkedChannel } from '@/api/channelLinks'

export interface UseTelegramLinkOptions {
  /** Called when polling detects a successful link. */
  onLinkSuccess?: () => void
}

/**
 * Shared Telegram link-flow lifecycle composable.
 *
 * Manages: code generation, countdown timer, clipboard copy,
 * deep-link opening, 5-second poll for link detection, and cleanup.
 */
export function useTelegramLink(options: UseTelegramLinkOptions = {}) {
  // ── Reactive state ──────────────────────────────────────────
  const linkedChannels = ref<LinkedChannel[]>([])
  const isGenerating = ref(false)
  const bindCommand = ref<string | null>(null)
  const botUrl = ref<string | null>(null)
  const deepLinkUrl = ref<string | null>(null)
  const countdown = ref(0)
  const maxSeconds = ref(1800)
  const isCopied = ref(false)
  const error = ref<string | null>(null)
  const feedback = ref<string | null>(null)

  // ── Timers ──────────────────────────────────────────────────
  let countdownInterval: ReturnType<typeof setInterval> | null = null
  let pollInterval: ReturnType<typeof setInterval> | null = null
  let copyTimeout: ReturnType<typeof setTimeout> | null = null
  let feedbackTimeout: ReturnType<typeof setTimeout> | null = null

  // ── Computed ────────────────────────────────────────────────
  const isTelegramLinked = computed(() =>
    linkedChannels.value.some((c) => c.channel === 'telegram'),
  )

  const telegramChannel = computed(() =>
    linkedChannels.value.find((c) => c.channel === 'telegram') ?? null,
  )

  const senderDisplay = computed(() => {
    const senderId = telegramChannel.value?.sender_id || ''
    const parts = senderId.split('|')
    if (parts.length > 1 && parts[1]) return `@${parts[1]}`
    return senderId || ''
  })

  const linkedAt = computed(() => {
    const tg = telegramChannel.value
    if (!tg?.linked_at) return ''
    return new Date(tg.linked_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  })

  const activeCommand = computed(() => {
    if (bindCommand.value) return bindCommand.value
    return ''
  })

  const botHandle = computed(() => {
    if (!botUrl.value) return '@pythinker_bot'
    const trimmed = botUrl.value.trim().replace(/\/+$/, '')
    return `@${trimmed.split('/').pop() || 'pythinker_bot'}`
  })

  const countdownProgress = computed(() => {
    if (maxSeconds.value <= 0) return 0
    return countdown.value / maxSeconds.value
  })

  const countdownUrgent = computed(() => countdown.value <= 60)

  const hasDraft = computed(() => bindCommand.value !== null)

  // ── Helpers ─────────────────────────────────────────────────
  const setFeedback = (message: string, durationMs = 4000) => {
    feedback.value = message
    if (feedbackTimeout) clearTimeout(feedbackTimeout)
    feedbackTimeout = setTimeout(() => {
      feedback.value = null
    }, durationMs)
  }

  const formatCountdown = (seconds: number) => {
    const safe = Math.max(seconds, 0)
    const m = Math.floor(safe / 60)
    const s = safe % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  // ── Core actions ────────────────────────────────────────────
  const loadChannels = async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) error.value = null
    try {
      linkedChannels.value = await getLinkedChannels()
      if (isTelegramLinked.value) clearDraft('linked')
    } catch {
      if (!opts.silent) error.value = 'Unable to load channel status.'
    }
  }

  const clearDraft = (reason: 'manual' | 'expired' | 'linked' | 'none' = 'none') => {
    if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null }
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
    bindCommand.value = null
    botUrl.value = null
    deepLinkUrl.value = null
    countdown.value = 0
    isCopied.value = false

    if (reason === 'expired') setFeedback('Link expired. Generate a new one.')
    if (reason === 'linked') {
      setFeedback('Telegram linked successfully.')
      options.onLinkSuccess?.()
    }
  }

  const startCountdown = () => {
    if (countdownInterval) clearInterval(countdownInterval)
    countdownInterval = setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0) clearDraft('expired')
    }, 1000)
  }

  const startPolling = () => {
    if (pollInterval) clearInterval(pollInterval)
    pollInterval = setInterval(() => {
      void loadChannels({ silent: true })
    }, 5000)
  }

  const openDeepLink = () => {
    // Prefer ?start= deep link for auto-send behaviour.
    const targetUrl = deepLinkUrl.value || botUrl.value
    if (!targetUrl) {
      error.value = 'Telegram link is unavailable. Try again.'
      return
    }
    const popup = window.open(targetUrl, '_blank', 'noopener,noreferrer')
    setFeedback(
      popup
        ? 'Telegram opened. Send the bind command in your chat.'
        : 'Popup blocked. Copy the command and send it manually.',
    )
  }

  const generate = async () => {
    isGenerating.value = true
    error.value = null
    feedback.value = null
    try {
      const result = await generateLinkCode('telegram')
      clearDraft('none')
      bindCommand.value = result.bind_command || `:bind ${result.code}`
      botUrl.value = result.bot_url || null
      deepLinkUrl.value = result.deep_link_url || result.bot_url || null
      countdown.value = result.expires_in_seconds
      maxSeconds.value = result.expires_in_seconds
      startCountdown()
      openDeepLink()
      startPolling()
    } catch {
      error.value = 'Failed to generate Telegram link code.'
    } finally {
      isGenerating.value = false
    }
  }

  const copyCommand = async () => {
    const cmd = activeCommand.value
    if (!cmd) return
    try {
      await navigator.clipboard.writeText(cmd)
      isCopied.value = true
      setFeedback('Bind command copied.')
      if (copyTimeout) clearTimeout(copyTimeout)
      copyTimeout = setTimeout(() => { isCopied.value = false }, 2000)
    } catch {
      error.value = 'Failed to copy command.'
    }
  }

  // ── Cleanup ─────────────────────────────────────────────────
  onUnmounted(() => {
    if (countdownInterval) clearInterval(countdownInterval)
    if (pollInterval) clearInterval(pollInterval)
    if (copyTimeout) clearTimeout(copyTimeout)
    if (feedbackTimeout) clearTimeout(feedbackTimeout)
  })

  return {
    // State
    linkedChannels,
    isGenerating,
    bindCommand,
    botUrl,
    deepLinkUrl,
    countdown,
    maxSeconds,
    isCopied,
    error,
    feedback,

    // Computed
    isTelegramLinked,
    telegramChannel,
    senderDisplay,
    linkedAt,
    activeCommand,
    botHandle,
    countdownProgress,
    countdownUrgent,
    hasDraft,

    // Actions
    loadChannels,
    generate,
    clearDraft,
    openDeepLink,
    copyCommand,
    formatCountdown,
    setFeedback,
  }
}
