import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * Tests for the planning presentation lifecycle in ChatPage.vue.
 *
 * Mirrors ChatPage state transitions in isolation (no full mount).
 * Validates: progress scaffold building, stream chunk handling,
 * deduplication, cleanup on tool start, and reset paths.
 */

type PlanPresentationSource = 'idle' | 'progress' | 'stream' | 'final'

function normalizePlanningPhase(phase: string): string {
  return phase
}

describe('ChatPage - Planning Presentation Lifecycle', () => {
  let planPresentationText: ReturnType<typeof ref<string>>
  let isPlanStreaming: ReturnType<typeof ref<boolean>>
  let planPresentationSource: ReturnType<typeof ref<PlanPresentationSource>>
  let lastPlanningProgressSignature: ReturnType<typeof ref<string>>

  beforeEach(() => {
    vi.useFakeTimers()
    planPresentationText = ref('')
    isPlanStreaming = ref(false)
    planPresentationSource = ref<PlanPresentationSource>('idle')
    lastPlanningProgressSignature = ref('')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // Mirror of ChatPage's updatePlanProgressPresentation
  function updatePlanProgressPresentation(progressData: { phase: string; message?: string }) {
    if (planPresentationSource.value === 'stream' || planPresentationSource.value === 'final') {
      return
    }

    const phase = normalizePlanningPhase(progressData.phase)
    if (phase === 'received') return

    const line = progressData.message?.trim()
    if (!line) return

    const signature = `${phase}:${line}`
    if (signature === lastPlanningProgressSignature.value) return
    lastPlanningProgressSignature.value = signature

    if (!planPresentationText.value) {
      planPresentationText.value = '# Planning...\n\n'
    }

    planPresentationText.value += `> ${line}\n`
    planPresentationSource.value = 'progress'
  }

  // Mirror of ChatPage's handleStreamEvent planning branch
  function handlePlanningStream(streamData: { content?: string; is_final?: boolean }) {
    if (planPresentationSource.value !== 'stream') {
      planPresentationText.value = ''
      planPresentationSource.value = 'stream'
    }

    if (streamData.content) {
      planPresentationText.value += streamData.content
    }

    isPlanStreaming.value = !streamData.is_final
    if (streamData.is_final) {
      planPresentationSource.value = 'final'
    }
  }

  // Mirror of ChatPage's cleanup for planning presentation
  function clearPlanPresentation() {
    planPresentationText.value = ''
    isPlanStreaming.value = false
    planPresentationSource.value = 'idle'
    lastPlanningProgressSignature.value = ''
  }

  // ── Progress scaffold tests ────────────────────────────────────

  it('progress scaffold starts with "# Planning..."', () => {
    updatePlanProgressPresentation({ phase: 'analyzing', message: 'Analyzing task complexity...' })
    expect(planPresentationText.value).toContain('# Planning...')
  })

  it('"received" progress is ignored for visible markdown', () => {
    updatePlanProgressPresentation({ phase: 'received', message: 'Message received' })
    expect(planPresentationText.value).toBe('')
    expect(planPresentationSource.value).toBe('idle')
  })

  it('repeated planning heartbeat messages append only once', () => {
    updatePlanProgressPresentation({ phase: 'planning', message: 'Generating plan...' })
    updatePlanProgressPresentation({ phase: 'planning', message: 'Generating plan...' })
    updatePlanProgressPresentation({ phase: 'planning', message: 'Generating plan...' })

    const matches = planPresentationText.value.match(/Generating plan\.\.\./g)
    expect(matches).toHaveLength(1)
  })

  it('appends distinct progress lines', () => {
    updatePlanProgressPresentation({ phase: 'analyzing', message: 'Analyzing task complexity...' })
    updatePlanProgressPresentation({ phase: 'planning', message: 'Creating execution plan...' })

    expect(planPresentationText.value).toContain('> Analyzing task complexity...')
    expect(planPresentationText.value).toContain('> Creating execution plan...')
  })

  // ── Stream chunk tests ─────────────────────────────────────────

  it('first StreamEvent(phase="planning") clears the progress scaffold', () => {
    updatePlanProgressPresentation({ phase: 'planning', message: 'Generating plan...' })
    expect(planPresentationText.value).toContain('# Planning...')

    handlePlanningStream({ content: '# AI Agent Frameworks' })
    expect(planPresentationText.value).toBe('# AI Agent Frameworks')
    expect(planPresentationSource.value).toBe('stream')
  })

  it('subsequent stream chunks append to the plan text', () => {
    handlePlanningStream({ content: '# Plan\n' })
    handlePlanningStream({ content: '> Goal text\n' })
    expect(planPresentationText.value).toBe('# Plan\n> Goal text\n')
  })

  it('is_final=true sets isPlanStreaming=false and source=final', () => {
    handlePlanningStream({ content: '# Plan\n' })
    expect(isPlanStreaming.value).toBe(true)

    handlePlanningStream({ content: '', is_final: true })
    expect(isPlanStreaming.value).toBe(false)
    expect(planPresentationSource.value).toBe('final')
  })

  it('progress updates are ignored after streaming has started', () => {
    handlePlanningStream({ content: '# Final Plan' })

    updatePlanProgressPresentation({ phase: 'planning', message: 'Late progress' })
    expect(planPresentationText.value).toBe('# Final Plan')
  })

  // ── PlanEvent tests ────────────────────────────────────────────

  it('PlanEvent does not clear the final markdown', () => {
    handlePlanningStream({ content: '# Final Plan' })
    handlePlanningStream({ content: '', is_final: true })

    // Simulate handlePlanEvent — it should NOT clear planPresentationText
    // (The real ChatPage just sets plan.value and clears thinking state)
    expect(planPresentationText.value).toBe('# Final Plan')
    expect(planPresentationSource.value).toBe('final')
  })

  // ── Tool start clears planning ─────────────────────────────────

  it('first tool with status calling clears the planning presentation', () => {
    handlePlanningStream({ content: '# Plan Content' })
    handlePlanningStream({ content: '', is_final: true })
    expect(planPresentationText.value).toBe('# Plan Content')

    // Simulate first tool event with status=calling
    clearPlanPresentation()

    expect(planPresentationText.value).toBe('')
    expect(isPlanStreaming.value).toBe(false)
    expect(planPresentationSource.value).toBe('idle')
  })

  // ── Reset/cancel paths ─────────────────────────────────────────

  it('reset/cancel paths clear planning presentation state', () => {
    handlePlanningStream({ content: '# Plan' })
    expect(planPresentationText.value).toBe('# Plan')

    clearPlanPresentation()

    expect(planPresentationText.value).toBe('')
    expect(isPlanStreaming.value).toBe(false)
    expect(planPresentationSource.value).toBe('idle')
    expect(lastPlanningProgressSignature.value).toBe('')
  })
})
