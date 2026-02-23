import { describe, expect, it } from 'vitest'
import { computed, ref } from 'vue'
import { SessionStatus } from '@/types/response'

describe('ChatPage - Task Progress Bar Visibility', () => {
  const createShowTaskProgressBar = () => {
    const showSessionWarmupMessage = ref(false)
    const isToolPanelOpen = ref(false)
    const receivedDoneEvent = ref(false)
    const sessionStatus = ref<SessionStatus | undefined>(SessionStatus.RUNNING)
    const planStepCount = ref(0)
    const hasLastNoMessageTool = ref(false)
    const isInitializing = ref(false)
    const isSandboxInitializing = ref(false)

    const isTaskCompleted = computed(() =>
      receivedDoneEvent.value || sessionStatus.value === SessionStatus.COMPLETED
    )

    const showTaskProgressBar = computed(() =>
      !showSessionWarmupMessage.value &&
      !isToolPanelOpen.value &&
      !isTaskCompleted.value &&
      (
        planStepCount.value > 0 ||
        hasLastNoMessageTool.value ||
        isInitializing.value ||
        isSandboxInitializing.value
      )
    )

    return {
      showTaskProgressBar,
      receivedDoneEvent,
      sessionStatus,
      planStepCount,
      hasLastNoMessageTool,
      isInitializing,
      isSandboxInitializing,
    }
  }

  it('shows progress bar while task is active and plan steps exist', () => {
    const state = createShowTaskProgressBar()
    state.planStepCount.value = 2

    expect(state.showTaskProgressBar.value).toBe(true)
  })

  it('hides progress bar immediately when done event is received', () => {
    const state = createShowTaskProgressBar()
    state.planStepCount.value = 2
    state.hasLastNoMessageTool.value = true
    state.receivedDoneEvent.value = true

    expect(state.showTaskProgressBar.value).toBe(false)
  })

  it('hides progress bar for restored completed sessions', () => {
    const state = createShowTaskProgressBar()
    state.planStepCount.value = 3
    state.hasLastNoMessageTool.value = true
    state.isInitializing.value = true
    state.isSandboxInitializing.value = true
    state.sessionStatus.value = SessionStatus.COMPLETED

    expect(state.showTaskProgressBar.value).toBe(false)
  })
})
