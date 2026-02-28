import { computed, readonly, ref } from 'vue'
import { useWideResearchGlobal } from '@/composables/useWideResearch'
import type {
  CheckpointSavedEventData,
  DeepResearchEventData,
  PhaseTransitionEventData,
  StreamEventData,
  WideResearchEventData,
  WorkspaceEventData,
} from '@/types/event'
import type {
  ResearchCheckpointSummary,
  ResearchReflectionSummary,
  WideResearchState,
} from '@/types/message'

export interface WorkspaceInfo {
  initialized: boolean
  workspacePath: string | null
  workspaceType: string | null
  structure: Record<string, string> | null
  deliverablesCount: number
}

export interface DeepResearchWorkflowState {
  research_id: string
  status: string
  total_queries: number
  completed_queries: number
  auto_run: boolean
  phase: string | null
  phase_label: string | null
  checkpoints: ResearchCheckpointSummary[]
  latest_reflection: ResearchReflectionSummary | null
}

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
  const activeDeepResearchId = ref<string | null>(null)
  const deepResearchStates = ref<Record<string, DeepResearchWorkflowState>>({})
  const checkpoints = ref<ResearchCheckpointSummary[]>([])
  const latestReflection = ref<ResearchReflectionSummary | null>(null)
  const reflectionBuffer = ref('')

  const workspaceInfo = ref<WorkspaceInfo>({
    initialized: false,
    workspacePath: null,
    workspaceType: null,
    structure: null,
    deliverablesCount: 0,
  })

  const activePhase = computed(() => widePhase.value ?? sessionPhase.value)
  const activePhaseLabel = computed(() => toPhaseLabel(activePhase.value))

  const getDeepResearchState = (
    researchId: string,
    fallbackStatus: string = 'started',
  ): DeepResearchWorkflowState => {
    const existing = deepResearchStates.value[researchId]
    if (existing) {
      return existing
    }

    const initialState: DeepResearchWorkflowState = {
      research_id: researchId,
      status: fallbackStatus,
      total_queries: 0,
      completed_queries: 0,
      auto_run: false,
      phase: null,
      phase_label: null,
      checkpoints: [],
      latest_reflection: null,
    }
    deepResearchStates.value = {
      ...deepResearchStates.value,
      [researchId]: initialState,
    }
    return initialState
  }

  const updateDeepResearchState = (
    researchId: string,
    updater: (state: DeepResearchWorkflowState) => DeepResearchWorkflowState,
    fallbackStatus: string = 'started',
  ): DeepResearchWorkflowState => {
    const nextState = updater(getDeepResearchState(researchId, fallbackStatus))
    deepResearchStates.value = {
      ...deepResearchStates.value,
      [researchId]: nextState,
    }
    return nextState
  }

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

  const handleDeepResearchEvent = (data: DeepResearchEventData) => {
    activeDeepResearchId.value = data.research_id

    updateDeepResearchState(
      data.research_id,
      (state) => ({
        ...state,
        status: data.status,
        total_queries: data.total_queries ?? state.total_queries,
        completed_queries: data.completed_queries ?? state.completed_queries,
        auto_run: data.auto_run ?? state.auto_run,
      }),
      data.status,
    )
  }

  const handlePhaseTransitionEvent = (data: PhaseTransitionEventData) => {
    setSessionPhase(data.phase)

    if (data.source === 'wide_research') {
      widePhase.value = data.phase
      return
    }

    if (data.research_id) {
      activeDeepResearchId.value = data.research_id
      updateDeepResearchState(data.research_id, (state) => ({
        ...state,
        phase: data.phase,
        phase_label: data.label ?? toPhaseLabel(data.phase),
      }))
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

    const researchId = data.research_id ?? activeDeepResearchId.value
    if (researchId) {
      activeDeepResearchId.value = researchId
      updateDeepResearchState(researchId, (state) => ({
        ...state,
        phase: data.phase,
        phase_label: toPhaseLabel(data.phase),
        checkpoints: [...state.checkpoints, checkpoint],
      }))
    }
  }

  const handleStreamEvent = (data: StreamEventData) => {
    if (data.phase === 'reflection') {
      reflectionBuffer.value += data.content
      const parsed = parseReflection(reflectionBuffer.value)
      if (parsed) {
        latestReflection.value = parsed
        const researchId = activeDeepResearchId.value
        if (researchId) {
          updateDeepResearchState(researchId, (state) => ({
            ...state,
            latest_reflection: parsed,
          }))
        }
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

  const handleWorkspaceEvent = (data: WorkspaceEventData) => {
    if (data.action === 'initialized') {
      workspaceInfo.value = {
        initialized: true,
        workspacePath: data.workspace_path ?? null,
        workspaceType: data.workspace_type ?? null,
        structure: data.structure ?? null,
        deliverablesCount: 0,
      }
    } else if (data.action === 'deliverables_ready') {
      workspaceInfo.value = {
        ...workspaceInfo.value,
        deliverablesCount: data.deliverables_count ?? 0,
      }
    }
  }

  const reset = () => {
    wideResearch.clearResearch()
    widePhase.value = null
    sessionPhase.value = null
    activeDeepResearchId.value = null
    deepResearchStates.value = {}
    checkpoints.value = []
    latestReflection.value = null
    reflectionBuffer.value = ''
    workspaceInfo.value = {
      initialized: false,
      workspacePath: null,
      workspaceType: null,
      structure: null,
      deliverablesCount: 0,
    }
  }

  return {
    wideOverlayState,
    wideIsActive: wideResearch.isActive,
    activePhase: readonly(activePhase),
    activePhaseLabel: readonly(activePhaseLabel),
    activeDeepResearchId: readonly(activeDeepResearchId),
    deepResearchStates: readonly(deepResearchStates),
    checkpoints: readonly(checkpoints),
    latestReflection: readonly(latestReflection),
    workspaceInfo: readonly(workspaceInfo),

    handleWideResearchEvent,
    handleDeepResearchEvent,
    handlePhaseTransitionEvent,
    handleCheckpointSavedEvent,
    handleStreamEvent,
    handleWorkspaceEvent,
    getDeepResearchState,
    reset,
  }
}
