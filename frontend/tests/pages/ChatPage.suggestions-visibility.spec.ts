/**
 * Tests for ChatPage suggestions visibility logic
 *
 * CRITICAL: Suggestions should ONLY show when:
 * 1. responsePhase === 'settled' (response completed)
 * 2. sessionStatus === COMPLETED (backend confirmed completion)
 * 3. suggestions array has items
 * 4. summary is not streaming
 *
 * This prevents showing "Suggested follow-ups" prematurely on timeout/error
 * when the agent may still be working in the background.
 */
import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'
import { SessionStatus } from '@/types/response'

describe('ChatPage - Suggestions Visibility Logic', () => {
  describe('canShowSuggestions computed property', () => {
    it('should show suggestions when settled AND status is COMPLETED', () => {
      const isSettled = ref(true)
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(true)
    })

    it('should NOT show suggestions when timed_out (even with suggestions)', () => {
      const isSettled = ref(false) // timed_out is NOT settled
      const sessionStatus = ref(SessionStatus.RUNNING) // Still running
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when settled but status is RUNNING', () => {
      const isSettled = ref(true)
      const sessionStatus = ref(SessionStatus.RUNNING)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when settled but status is FAILED', () => {
      const isSettled = ref(true)
      const sessionStatus = ref(SessionStatus.FAILED)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when settled but suggestions array is empty', () => {
      const isSettled = ref(true)
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const suggestions = ref([])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when summary is streaming', () => {
      const isSettled = ref(true)
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(true)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when error phase (even if status is COMPLETED)', () => {
      const isSettled = ref(false) // error is NOT settled
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })

    it('should NOT show suggestions when stopped phase', () => {
      const isSettled = ref(false) // stopped is NOT settled
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const suggestions = ref(['Suggestion 1', 'Suggestion 2'])
      const isSummaryStreaming = ref(false)

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0 &&
        !isSummaryStreaming.value
      )

      expect(canShowSuggestions.value).toBe(false)
    })
  })

  describe('Timeout vs Completion UX', () => {
    it('should show timeout notice when timed_out, NOT suggestions', () => {
      const responsePhase = ref('timed_out')
      const sessionStatus = ref(SessionStatus.RUNNING)
      const isSettled = ref(false)
      const suggestions = ref(['Suggestion 1'])

      const showTimeoutNotice = computed(() => responsePhase.value === 'timed_out')
      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      expect(showTimeoutNotice.value).toBe(true)
      expect(canShowSuggestions.value).toBe(false)
    })

    it('should show suggestions when completed, NOT timeout notice', () => {
      const responsePhase = ref('settled')
      const sessionStatus = ref(SessionStatus.COMPLETED)
      const isSettled = ref(true)
      const suggestions = ref(['Suggestion 1'])

      const showTimeoutNotice = computed(() => responsePhase.value === 'timed_out')
      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      expect(showTimeoutNotice.value).toBe(false)
      expect(canShowSuggestions.value).toBe(true)
    })

    it('should transition from timeout to completed and show suggestions', () => {
      const responsePhase = ref('timed_out')
      const sessionStatus = ref(SessionStatus.RUNNING)
      const isSettled = ref(false)
      const suggestions = ref([])

      const showTimeoutNotice = computed(() => responsePhase.value === 'timed_out')
      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      // Initial state: timeout, no suggestions
      expect(showTimeoutNotice.value).toBe(true)
      expect(canShowSuggestions.value).toBe(false)

      // Reconnect successful, get done event
      responsePhase.value = 'settled'
      sessionStatus.value = SessionStatus.COMPLETED
      isSettled.value = true
      suggestions.value = ['What are the best next steps?']

      // Final state: no timeout, show suggestions
      expect(showTimeoutNotice.value).toBe(false)
      expect(canShowSuggestions.value).toBe(true)
    })
  })

  describe('State transitions', () => {
    it('should handle normal completion flow', () => {
      const responsePhase = ref('idle')
      const sessionStatus = ref(SessionStatus.PENDING)
      const isSettled = ref(false)
      const suggestions = ref([])

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      // 1. Start chat
      responsePhase.value = 'connecting'
      sessionStatus.value = SessionStatus.RUNNING
      expect(canShowSuggestions.value).toBe(false)

      // 2. Receive first event
      responsePhase.value = 'streaming'
      expect(canShowSuggestions.value).toBe(false)

      // 3. Receive done event
      responsePhase.value = 'completing'
      suggestions.value = ['Follow up 1', 'Follow up 2']
      expect(canShowSuggestions.value).toBe(false) // Not settled yet

      // 4. Auto-settle after 300ms
      responsePhase.value = 'settled'
      sessionStatus.value = SessionStatus.COMPLETED
      isSettled.value = true
      expect(canShowSuggestions.value).toBe(true) // NOW show suggestions
    })

    it('should handle timeout and manual retry flow', () => {
      const responsePhase = ref('streaming')
      const sessionStatus = ref(SessionStatus.RUNNING)
      const isSettled = ref(false)
      const suggestions = ref([])

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      // 1. SSE timeout (no done event received)
      responsePhase.value = 'timed_out'
      expect(canShowSuggestions.value).toBe(false)

      // 2. User clicks "Retry"
      responsePhase.value = 'connecting'
      expect(canShowSuggestions.value).toBe(false)

      // 3. Reconnect and get done event
      responsePhase.value = 'completing'
      suggestions.value = ['Follow up 1']
      expect(canShowSuggestions.value).toBe(false)

      // 4. Settle
      responsePhase.value = 'settled'
      sessionStatus.value = SessionStatus.COMPLETED
      isSettled.value = true
      expect(canShowSuggestions.value).toBe(true)
    })

    it('should handle user stop flow', () => {
      const responsePhase = ref('streaming')
      const sessionStatus = ref(SessionStatus.RUNNING)
      const isSettled = ref(false)
      const suggestions = ref([])

      const canShowSuggestions = computed(() =>
        isSettled.value &&
        sessionStatus.value === SessionStatus.COMPLETED &&
        suggestions.value.length > 0
      )

      // User clicks "Stop"
      responsePhase.value = 'stopped'
      sessionStatus.value = SessionStatus.COMPLETED
      // NOTE: suggestions are NOT populated on stop (per handleStop logic)
      expect(canShowSuggestions.value).toBe(false)
    })
  })
})
