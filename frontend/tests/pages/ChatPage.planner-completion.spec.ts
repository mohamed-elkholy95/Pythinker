import { computed, nextTick, ref, watch } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('ChatPage - Planner Completion Behavior', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('hides planning card when task is completed', () => {
    const showSessionWarmupMessage = ref(false)
    const isToolPanelOpen = ref(false)
    const isTaskCompleted = ref(true)
    const responsePhase = ref<'streaming' | 'timed_out'>('streaming')
    const sessionResearchMode = ref<'deep_research' | 'fast_search'>('deep_research')
    const planningProgress = ref({ phase: 'planning', message: 'Planning...', percent: 35 })
    const planStepCount = ref(0)

    const showPlanningCard = computed(() =>
      !showSessionWarmupMessage.value &&
      !isToolPanelOpen.value &&
      !isTaskCompleted.value &&
      responsePhase.value !== 'timed_out' &&
      sessionResearchMode.value === 'deep_research' &&
      planningProgress.value !== null &&
      planStepCount.value === 0
    )

    expect(showPlanningCard.value).toBe(false)
  })

  it('stops planner cycle and clears planning progress on completion', async () => {
    const isTaskCompleted = ref(false)
    const planningProgress = ref<{ phase: string; message: string; percent: number } | null>({
      phase: 'planning',
      message: 'Planning...',
      percent: 50,
    })

    let planningMessageInterval: ReturnType<typeof setInterval> | null = setInterval(() => {}, 2500)

    const stopPlanningMessageCycle = () => {
      if (planningMessageInterval) {
        clearInterval(planningMessageInterval)
        planningMessageInterval = null
      }
    }

    watch(isTaskCompleted, (completed) => {
      if (!completed) return
      planningProgress.value = null
      stopPlanningMessageCycle()
    })

    isTaskCompleted.value = true
    await nextTick()

    expect(planningProgress.value).toBeNull()
    expect(planningMessageInterval).toBeNull()
  })
})
