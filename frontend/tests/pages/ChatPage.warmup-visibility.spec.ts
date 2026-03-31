import { computed, ref } from 'vue'
import { describe, expect, it } from 'vitest'

describe('ChatPage - Warmup Visibility', () => {
  const createShowSessionWarmupMessage = () => {
    const hasPrompt = ref(true)
    const sessionInitTimedOut = ref(false)
    const isToolPanelPainted = ref(false)
    const isLoading = ref(true)
    const isSandboxInitializing = ref(false)
    const isWaitingForSessionReady = ref(false)
    const isInitializing = ref(false)

    const showSessionWarmupMessage = computed(() => {
      if (!hasPrompt.value) return false
      if (sessionInitTimedOut.value) return true
      if (isToolPanelPainted.value) return false

      return (
        isLoading.value ||
        isSandboxInitializing.value ||
        isWaitingForSessionReady.value ||
        isInitializing.value
      )
    })

    return {
      showSessionWarmupMessage,
      hasPrompt,
      sessionInitTimedOut,
      isToolPanelPainted,
      isLoading,
      isSandboxInitializing,
      isWaitingForSessionReady,
      isInitializing,
    }
  }

  it('keeps the warmup message visible while the tool panel is still closed', () => {
    const state = createShowSessionWarmupMessage()

    expect(state.showSessionWarmupMessage.value).toBe(true)

    state.isLoading.value = false
    state.isSandboxInitializing.value = true

    expect(state.showSessionWarmupMessage.value).toBe(true)
  })

  it('hides the warmup message on the first painted frame of the tool panel', () => {
    const state = createShowSessionWarmupMessage()

    state.isToolPanelPainted.value = true

    expect(state.showSessionWarmupMessage.value).toBe(false)
  })

  it('still shows the timeout state even if the tool panel has not opened yet', () => {
    const state = createShowSessionWarmupMessage()

    state.isLoading.value = false
    state.sessionInitTimedOut.value = true

    expect(state.showSessionWarmupMessage.value).toBe(true)
  })
})
