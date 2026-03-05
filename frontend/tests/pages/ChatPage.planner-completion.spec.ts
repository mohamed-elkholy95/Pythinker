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

  it('clears planning progress on completion', async () => {
    const isTaskCompleted = ref(false)
    const planningProgress = ref<{ phase: string; message: string; percent: number } | null>({
      phase: 'planning',
      message: 'Planning...',
      percent: 50,
    })

    watch(isTaskCompleted, (completed) => {
      if (!completed) return
      planningProgress.value = null
    })

    isTaskCompleted.value = true
    await nextTick()

    expect(planningProgress.value).toBeNull()
  })

  it('keeps planning card visible during a short plan-ready handoff', () => {
    const showSessionWarmupMessage = ref(false)
    const isToolPanelOpen = ref(false)
    const isTaskCompleted = ref(false)
    const responsePhase = ref<'streaming' | 'timed_out'>('streaming')
    const sessionResearchMode = ref<'deep_research' | 'fast_search'>('deep_research')
    const planningCardState = ref<{
      phase: string
      message: string
    } | null>(null)
    const planningHandoffState = ref<{
      title?: string
      phase: string
      message: string
    } | null>({
      title: 'Plan ready',
      phase: 'executing_setup',
      message: 'Starting execution from the approved plan.',
    })
    const planStepCount = ref(3)

    const activePlanningCardState = computed(() =>
      planningHandoffState.value ?? planningCardState.value
    )

    const showPlanningCard = computed(() =>
      !showSessionWarmupMessage.value &&
      !isToolPanelOpen.value &&
      !isTaskCompleted.value &&
      responsePhase.value !== 'timed_out' &&
      sessionResearchMode.value === 'deep_research' &&
      !!activePlanningCardState.value &&
      (!!planningHandoffState.value || planStepCount.value === 0)
    )

    expect(showPlanningCard.value).toBe(true)
  })

  it('clears plan-ready handoff after the timeout', () => {
    const planningHandoffState = ref<{
      title?: string
      phase: string
      message: string
      progressPercent?: number
    } | null>(null)
    let planningHandoffTimer: ReturnType<typeof setTimeout> | null = null

    const clearPlanningHandoff = () => {
      if (planningHandoffTimer) {
        clearTimeout(planningHandoffTimer)
        planningHandoffTimer = null
      }
      planningHandoffState.value = null
    }

    const startPlanningHandoff = () => {
      clearPlanningHandoff()
      planningHandoffState.value = {
        title: 'Plan ready',
        phase: 'executing_setup',
        message: 'Starting execution from the approved plan.',
        progressPercent: 100,
      }
      planningHandoffTimer = setTimeout(() => {
        planningHandoffTimer = null
        planningHandoffState.value = null
      }, 650)
    }

    startPlanningHandoff()
    expect(planningHandoffState.value?.title).toBe('Plan ready')

    vi.advanceTimersByTime(649)
    expect(planningHandoffState.value?.title).toBe('Plan ready')

    vi.advanceTimersByTime(1)
    expect(planningHandoffState.value).toBeNull()
  })
})

// ── PhaseStrip integration logic tests ──────────────────────────────

type PhaseStripPhase = 'planning' | 'verifying' | 'searching' | 'writing' | 'done'

describe('ChatPage - PhaseStrip computed state', () => {
  /**
   * Helper that mirrors the phaseStripPhase computed from ChatPage.vue.
   */
  function buildPhaseStripPhase(opts: {
    isTaskCompleted: boolean
    planningProgress: { phase: string } | null
    isLoading: boolean
    isSummaryStreaming: boolean
    hasRunningStep: boolean
    hasPlanSteps: boolean
  }): PhaseStripPhase | null {
    if (opts.isTaskCompleted) return 'done'
    const progress = opts.planningProgress
    if (progress) {
      const phaseMap: Record<string, PhaseStripPhase> = {
        received: 'planning',
        analyzing: 'planning',
        planning: 'planning',
        verifying: 'verifying',
        executing_setup: 'searching',
        finalizing: 'writing',
        waiting: 'searching',
      }
      return phaseMap[progress.phase] ?? 'planning'
    }
    if (!opts.isLoading) return null
    if (opts.isSummaryStreaming) return 'writing'
    if (opts.hasRunningStep || opts.hasPlanSteps) return 'searching'
    return null
  }

  it('maps planning progress phases to PhaseStrip phases', () => {
    const base = {
      isTaskCompleted: false,
      isLoading: true,
      isSummaryStreaming: false,
      hasRunningStep: false,
      hasPlanSteps: false,
    }
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'received' } })).toBe('planning')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'analyzing' } })).toBe('planning')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'planning' } })).toBe('planning')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'verifying' } })).toBe('verifying')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'executing_setup' } })).toBe('searching')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'finalizing' } })).toBe('writing')
    expect(buildPhaseStripPhase({ ...base, planningProgress: { phase: 'waiting' } })).toBe('searching')
  })

  it('returns done when task is completed', () => {
    expect(buildPhaseStripPhase({
      isTaskCompleted: true,
      planningProgress: { phase: 'planning' },
      isLoading: true,
      isSummaryStreaming: false,
      hasRunningStep: false,
      hasPlanSteps: false,
    })).toBe('done')
  })

  it('returns searching when steps are executing without planning progress', () => {
    expect(buildPhaseStripPhase({
      isTaskCompleted: false,
      planningProgress: null,
      isLoading: true,
      isSummaryStreaming: false,
      hasRunningStep: true,
      hasPlanSteps: true,
    })).toBe('searching')
  })

  it('returns writing when summary is streaming', () => {
    expect(buildPhaseStripPhase({
      isTaskCompleted: false,
      planningProgress: null,
      isLoading: true,
      isSummaryStreaming: true,
      hasRunningStep: false,
      hasPlanSteps: false,
    })).toBe('writing')
  })

  it('returns null when not loading and no planning progress', () => {
    expect(buildPhaseStripPhase({
      isTaskCompleted: false,
      planningProgress: null,
      isLoading: false,
      isSummaryStreaming: false,
      hasRunningStep: false,
      hasPlanSteps: false,
    })).toBeNull()
  })

  it('falls back to planning for unknown planning progress phases', () => {
    expect(buildPhaseStripPhase({
      isTaskCompleted: false,
      planningProgress: { phase: 'unknown_phase' },
      isLoading: true,
      isSummaryStreaming: false,
      hasRunningStep: false,
      hasPlanSteps: false,
    })).toBe('planning')
  })
})

describe('ChatPage - PhaseStrip step progress', () => {
  function buildStepProgress(
    steps: { status?: string }[] | undefined,
  ): { current: number; total: number } | null {
    if (!steps || steps.length === 0) return null
    const completed = steps.filter(
      s => s.status === 'completed' || s.status === 'failed' || s.status === 'skipped',
    ).length
    return { current: completed, total: steps.length }
  }

  it('returns null when no plan steps exist', () => {
    expect(buildStepProgress(undefined)).toBeNull()
    expect(buildStepProgress([])).toBeNull()
  })

  it('counts completed, failed, and skipped steps', () => {
    const steps = [
      { status: 'completed' },
      { status: 'failed' },
      { status: 'skipped' },
      { status: 'running' },
      { status: 'pending' },
    ]
    expect(buildStepProgress(steps)).toEqual({ current: 3, total: 5 })
  })

  it('returns 0 current when all steps are pending', () => {
    const steps = [{ status: 'pending' }, { status: 'pending' }]
    expect(buildStepProgress(steps)).toEqual({ current: 0, total: 2 })
  })
})

describe('ChatPage - PhaseStrip visibility', () => {
  function showPhaseStrip(opts: {
    isChatMode: boolean
    isLoading: boolean
    phaseStripPhase: PhaseStripPhase | null
    phaseStripStartTime: number
  }): boolean {
    return (
      !opts.isChatMode &&
      opts.isLoading &&
      opts.phaseStripPhase !== null &&
      opts.phaseStripStartTime > 0
    )
  }

  it('shows when agent is running with a valid phase', () => {
    expect(showPhaseStrip({
      isChatMode: false,
      isLoading: true,
      phaseStripPhase: 'planning',
      phaseStripStartTime: Date.now(),
    })).toBe(true)
  })

  it('hides in chat mode', () => {
    expect(showPhaseStrip({
      isChatMode: true,
      isLoading: true,
      phaseStripPhase: 'planning',
      phaseStripStartTime: Date.now(),
    })).toBe(false)
  })

  it('hides when not loading', () => {
    expect(showPhaseStrip({
      isChatMode: false,
      isLoading: false,
      phaseStripPhase: 'searching',
      phaseStripStartTime: Date.now(),
    })).toBe(false)
  })

  it('hides when phase is null', () => {
    expect(showPhaseStrip({
      isChatMode: false,
      isLoading: true,
      phaseStripPhase: null,
      phaseStripStartTime: Date.now(),
    })).toBe(false)
  })

  it('hides when start time is 0 (not yet started)', () => {
    expect(showPhaseStrip({
      isChatMode: false,
      isLoading: true,
      phaseStripPhase: 'planning',
      phaseStripStartTime: 0,
    })).toBe(false)
  })
})
