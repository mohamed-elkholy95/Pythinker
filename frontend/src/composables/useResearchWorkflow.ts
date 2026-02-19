import { computed, readonly, ref } from 'vue'
import { useWideResearchGlobal } from '@/composables/useWideResearch'
import type {
  CheckpointSavedEventData,
  PhaseTransitionEventData,
  StreamEventData,
  WideResearchEventData,
} from '@/types/event'
import type {
  ResearchCheckpointSummary,
  ResearchReflectionSummary,
  WideResearchState,
} from '@/types/message'

const PHASE_LABELS: Record<string, string> = {
  planning: 'Planning',
  executing: 'Executing',
  summarizing: 'Summarizing',
  compilation: 'Compiling',
  completed: 'Completed',
  phase_1: 'Phase 1: Fundamentals',
  phase_2: 'Phase 2: Use Cases',
  phase_3: 'Phase 3: Best Practices',
}

const inferWidePhase = (status: WideResearchEventData['status']): string | null => {
  switch (status) {
    case 'pending':
      return 'planning'
    case 'searching':
      return 'executing'
    case 'aggregating':
      return 'summarizing'
    case 'completed':
      return 'completed'
    case 'failed':
      return 'summarizing'
    default:
      return null
  }
}

const toPhaseLabel = (phase: string | null | undefined): string | null => {
  if (!phase) return null
  if (phase in PHASE_LABELS) {
    return PHASE_LABELS[phase]
  }
  return phase
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const parseReflection = (content: string): ResearchReflectionSummary | null => {
  const trimmed = content.trim()
  if (!trimmed) return null

  const learnedMatch = trimmed.match(/LEARNED:\s*(.+)/i)
  const nextMatch = trimmed.match(/NEXT:\s*(.+)/i)

  const learned = learnedMatch?.[1]?.trim() ?? trimmed.split('\n')[0]?.trim() ?? ''
  if (!learned) return null

  const nextStep = nextMatch?.[1]?.trim()

  return {
    learned,
    next_step: nextStep || undefined,
    timestamp: Math.floor(Date.now() / 1000),
  }
}

export function useResearchWorkflow() {
  const wideResearch = useWideResearchGlobal()

  const widePhase = ref<string | null>(null)
  const sessionPhase = ref<string | null>(null)
  const checkpoints = ref<ResearchCheckpointSummary[]>([])
  const latestReflection = ref<ResearchReflectionSummary | null>(null)
  const reflectionBuffer = ref('')

  const activePhase = computed(() => widePhase.value ?? sessionPhase.value)
  const activePhaseLabel = computed(() => toPhaseLabel(activePhase.value))

  const wideOverlayState = computed<WideResearchState | null>(() => {
    const state = wideResearch.overlayState.value
    if (!state) return null

    const phase = widePhase.value ?? state.phase ?? null
    return {
      ...state,
      phase: phase ?? undefined,
      phase_label: toPhaseLabel(phase) ?? undefined,
    }
  })

  const setSessionPhase = (phase: string | null | undefined) => {
    if (!phase || phase === 'thinking') return
    sessionPhase.value = phase
  }

  const handleWideResearchEvent = (data: WideResearchEventData) => {
    if (data.status === 'pending') {
      wideResearch.startResearch({
        research_id: data.research_id,
        topic: data.topic,
        search_types: data.search_types,
        aggregation_strategy: data.aggregation_strategy,
      })
    } else if (data.status === 'searching' || data.status === 'aggregating') {
      wideResearch.updateProgress({
        research_id: data.research_id,
        total_queries: data.total_queries,
        completed_queries: data.completed_queries,
        sources_found: data.sources_found,
        current_query: data.current_query,
      })
    } else if (data.status === 'completed') {
      wideResearch.completeResearch({
        research_id: data.research_id,
        sources_count: data.sources_found,
        errors: data.errors,
      })
    } else if (data.status === 'failed') {
      wideResearch.failResearch(data.research_id, data.errors?.[0] || 'Research failed')
    }

    const nextPhase = inferWidePhase(data.status)
    if (nextPhase) {
      widePhase.value = nextPhase
      setSessionPhase(nextPhase)
    }
  }

  const handlePhaseTransitionEvent = (data: PhaseTransitionEventData) => {
    setSessionPhase(data.phase)

    if (data.source === 'wide_research') {
      widePhase.value = data.phase
    }
  }

  const handleCheckpointSavedEvent = (data: CheckpointSavedEventData) => {
    const checkpoint: ResearchCheckpointSummary = {
      phase: data.phase,
      notes_preview: data.notes_preview,
      source_count: data.source_count,
      timestamp: data.timestamp,
    }

    checkpoints.value = [...checkpoints.value, checkpoint]
    setSessionPhase(data.phase)
  }

  const handleStreamEvent = (data: StreamEventData) => {
    if (data.phase === 'reflection') {
      reflectionBuffer.value += data.content
      const parsed = parseReflection(reflectionBuffer.value)
      if (parsed) {
        latestReflection.value = parsed
      }
      if (data.is_final) {
        reflectionBuffer.value = ''
      }
      return
    }

    if (data.phase && data.phase !== 'thinking') {
      setSessionPhase(data.phase)
      if (data.phase === 'summarizing' && wideResearch.overlayState.value) {
        widePhase.value = 'summarizing'
      }
      if (data.phase === 'completed' && wideResearch.overlayState.value) {
        widePhase.value = 'completed'
      }
    }
  }

  const reset = () => {
    wideResearch.clearResearch()
    widePhase.value = null
    sessionPhase.value = null
    checkpoints.value = []
    latestReflection.value = null
    reflectionBuffer.value = ''
  }

  return {
    wideOverlayState,
    wideIsActive: wideResearch.isActive,
    activePhase: readonly(activePhase),
    activePhaseLabel: readonly(activePhaseLabel),
    checkpoints: readonly(checkpoints),
    latestReflection: readonly(latestReflection),

    handleWideResearchEvent,
    handlePhaseTransitionEvent,
    handleCheckpointSavedEvent,
    handleStreamEvent,
    reset,
  }
}
