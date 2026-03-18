import { beforeEach, describe, expect, it } from 'vitest'
import { useResearchWorkflow } from '@/composables/useResearchWorkflow'
import type {
  CheckpointSavedEventData,
  DeepResearchEventData,
  PhaseTransitionEventData,
  StreamEventData,
  WideResearchEventData,
} from '@/types/event'

const baseDeepEvent = (overrides: Partial<DeepResearchEventData> = {}): DeepResearchEventData => ({
  event_id: 'deep-1',
  timestamp: 100,
  research_id: 'research-1',
  status: 'started',
  total_queries: 3,
  completed_queries: 0,
  queries: [],
  auto_run: false,
  ...overrides,
})

const baseWideEvent = (overrides: Partial<WideResearchEventData> = {}): WideResearchEventData => ({
  event_id: 'wide-1',
  timestamp: 200,
  research_id: 'wide-1',
  topic: 'Agent architecture',
  status: 'pending',
  total_queries: 4,
  completed_queries: 0,
  sources_found: 0,
  search_types: ['info', 'news'],
  ...overrides,
})

describe('useResearchWorkflow', () => {
  const workflow = useResearchWorkflow()

  beforeEach(() => {
    workflow.reset()
  })

  it('applies phase_transition events to active and per-research state', () => {
    const transition: PhaseTransitionEventData = {
      event_id: 'phase-1',
      timestamp: 123,
      phase: 'phase_1',
      research_id: 'research-1',
      source: 'deep_research',
    }

    workflow.handlePhaseTransitionEvent(transition)

    expect(workflow.activePhase.value).toBe('phase_1')
    expect(workflow.activePhaseLabel.value).toBe('Phase 1: Fundamentals')

    const deepState = workflow.getDeepResearchState('research-1', 'started')
    expect(deepState.phase).toBe('phase_1')
    expect(deepState.phase_label).toBe('Phase 1: Fundamentals')
  })

  it('records checkpoint_saved events and attaches them to the active deep research', () => {
    workflow.handleDeepResearchEvent(baseDeepEvent())

    const checkpoint: CheckpointSavedEventData = {
      event_id: 'checkpoint-1',
      timestamp: 321,
      phase: 'phase_2',
      notes_preview: 'Compared implementation approaches',
      source_count: 6,
      research_id: 'research-1',
    }

    workflow.handleCheckpointSavedEvent(checkpoint)

    expect(workflow.checkpoints.value).toHaveLength(1)
    expect(workflow.checkpoints.value[0].phase).toBe('phase_2')
    expect(workflow.checkpoints.value[0].source_count).toBe(6)

    const deepState = workflow.getDeepResearchState('research-1', 'started')
    expect(deepState.checkpoints).toHaveLength(1)
    expect(deepState.checkpoints[0].notes_preview).toContain('implementation')
  })

  it('updates reflection state from reflection stream chunks', () => {
    workflow.handleDeepResearchEvent(baseDeepEvent())

    const reflectionChunk: StreamEventData = {
      event_id: 'stream-1',
      timestamp: 500,
      phase: 'reflection',
      is_final: false,
      content: 'LEARNED: Identified the bottleneck in query fan-out\nNEXT: Increase parallelism safely',
    }

    workflow.handleStreamEvent(reflectionChunk)

    expect(workflow.latestReflection.value?.learned).toContain('bottleneck')
    expect(workflow.latestReflection.value?.next_step).toContain('Increase parallelism safely')

    workflow.handleStreamEvent({
      ...reflectionChunk,
      event_id: 'stream-2',
      is_final: true,
      content: '',
    })

    const deepState = workflow.getDeepResearchState('research-1', 'started')
    expect(deepState.latest_reflection?.learned).toContain('bottleneck')
  })

  it('maps wide research status updates to phase-aware overlay state', () => {
    workflow.handleWideResearchEvent(baseWideEvent({ status: 'pending' }))
    expect(workflow.wideOverlayState.value?.phase).toBe('planning')

    workflow.handleWideResearchEvent(
      baseWideEvent({
        event_id: 'wide-2',
        status: 'searching',
        completed_queries: 2,
        total_queries: 4,
        sources_found: 8,
      }),
    )
    expect(workflow.wideOverlayState.value?.phase).toBe('executing')

    workflow.handleWideResearchEvent(
      baseWideEvent({
        event_id: 'wide-3',
        status: 'aggregating',
        completed_queries: 4,
      }),
    )
    expect(workflow.wideOverlayState.value?.phase).toBe('summarizing')
  })
})
