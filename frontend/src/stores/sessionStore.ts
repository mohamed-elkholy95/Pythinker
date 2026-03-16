/**
 * Session store — manages chat session state globally via Pinia.
 *
 * Consolidates session-related state (messages, plan, steps, files, sources)
 * into a single Pinia store. Composables like useChat become thin facades.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  Message,
  StepContent,
  SourceCitation,
} from '../types/message'
import type { PlanEventData, StepEventData } from '../types/event'

// ── Memory Caps ─────────────────────────────────────────────────────
const MAX_MESSAGES_IN_MEMORY = 500
const MAX_STEPS_IN_MEMORY = 200

// ── Interfaces ──────────────────────────────────────────────────────

/** Lightweight file reference for session-scoped file tracking. */
export interface SessionFile {
  id: string
  name: string
  path: string
  size?: number
  mime_type?: string
  created_at?: number
}

export const useSessionStore = defineStore('session', () => {
  // ── State ────────────────────────────────────────────────────────
  const sessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const title = ref<string>('')
  const plan = ref<PlanEventData | null>(null)
  const agentMode = ref<string>('auto')
  const isProcessing = ref<boolean>(false)
  const steps = ref<StepContent[]>([])
  const currentStepId = ref<string | null>(null)
  const files = ref<SessionFile[]>([])
  const sources = ref<SourceCitation[]>([])

  // ── Computed ─────────────────────────────────────────────────────
  const messageCount = computed(() => messages.value.length)
  const hasActivePlan = computed(() => plan.value !== null)
  const completedSteps = computed(() =>
    steps.value.filter((s) => s.status === 'completed'),
  )
  const isIdle = computed(() => !isProcessing.value)

  // ── Actions ──────────────────────────────────────────────────────

  function resetSession() {
    sessionId.value = null
    messages.value = []
    title.value = ''
    plan.value = null
    agentMode.value = 'auto'
    isProcessing.value = false
    steps.value = []
    currentStepId.value = null
    files.value = []
    sources.value = []
  }

  function addMessage(msg: Message) {
    messages.value.push(msg)
    if (messages.value.length > MAX_MESSAGES_IN_MEMORY) {
      messages.value = messages.value.slice(-MAX_MESSAGES_IN_MEMORY)
    }
  }

  function updateMessage(id: string, data: Partial<Message>) {
    const idx = messages.value.findIndex((m) => m.id === id)
    if (idx !== -1) {
      messages.value[idx] = { ...messages.value[idx], ...data }
    }
  }

  function setTitle(newTitle: string) {
    title.value = newTitle
  }

  function setPlan(newPlan: PlanEventData | null) {
    plan.value = newPlan
    if (newPlan?.steps) {
      // Sync plan steps into the steps array
      for (const step of newPlan.steps) {
        updateStep(step.id, step)
      }
    }
  }

  function updateStep(stepId: string, data: Partial<StepEventData>) {
    const idx = steps.value.findIndex((s) => s.id === stepId)
    if (idx !== -1) {
      steps.value[idx] = { ...steps.value[idx], ...data } as StepContent
    } else {
      // Insert new step from plan event data
      steps.value.push({
        id: stepId,
        description: data.description ?? '',
        status: data.status ?? 'pending',
        tools: [],
        timestamp: data.timestamp ?? Date.now(),
        phase_id: data.phase_id ?? null,
        step_type: data.step_type ?? null,
      })
      if (steps.value.length > MAX_STEPS_IN_MEMORY) {
        steps.value = steps.value.slice(-MAX_STEPS_IN_MEMORY)
      }
    }

    // Track the currently executing step
    if (data.status === 'started' || data.status === 'running') {
      currentStepId.value = stepId
    } else if (
      currentStepId.value === stepId &&
      (data.status === 'completed' || data.status === 'failed' || data.status === 'skipped')
    ) {
      currentStepId.value = null
    }
  }

  function addFile(file: SessionFile) {
    // Avoid duplicates by ID
    const exists = files.value.some((f) => f.id === file.id)
    if (!exists) {
      files.value.push(file)
    }
  }

  function addSource(source: SourceCitation) {
    // Avoid duplicate sources by URL
    const exists = sources.value.some((s) => s.url === source.url)
    if (!exists) {
      sources.value.push(source)
    }
  }

  return {
    // State
    sessionId,
    messages,
    title,
    plan,
    agentMode,
    isProcessing,
    steps,
    currentStepId,
    files,
    sources,
    // Computed
    messageCount,
    hasActivePlan,
    completedSteps,
    isIdle,
    // Actions
    resetSession,
    addMessage,
    updateMessage,
    setTitle,
    setPlan,
    updateStep,
    addFile,
    addSource,
  }
})
