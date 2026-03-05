import type { PlanningPhase } from '@/types/event'
import { STREAMING_FRAME_BATCH_MS } from '@/constants/streamingPresentation'

export interface PlanningProgressState {
  phase: PlanningPhase
  message: string
  percent: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
}

export interface PlanningCardState {
  phase: PlanningPhase
  message: string
  progressPercent?: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
}

export interface BuildPlanningCardStateArgs {
  planningProgress: PlanningProgressState | null
  isThinkingStreaming: boolean
  thinkingText: string
}

export const PLANNING_PHASES = [
  'received',
  'analyzing',
  'planning',
  'verifying',
  'executing_setup',
  'finalizing',
  'waiting',
] as const satisfies readonly PlanningPhase[]

const DEFAULT_THINKING_PREVIEW_MAX_CHARS = 220

function truncateSentence(text: string, maxChars: number): string {
  const truncated = text.slice(0, maxChars)
  const lastSpaceIdx = truncated.lastIndexOf(' ')
  const wordSafe = lastSpaceIdx >= Math.floor(maxChars * 0.6)
    ? truncated.slice(0, lastSpaceIdx)
    : truncated

  return `${wordSafe.trimEnd()}...`
}

export function summarizeThinkingText(text: string, maxChars: number = DEFAULT_THINKING_PREVIEW_MAX_CHARS): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''

  const safeMaxChars = Math.max(1, maxChars)
  if (normalized.length <= safeMaxChars) return normalized

  const sentences = normalized
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)

  const preferredSentence = sentences[0] ?? normalized
  if (preferredSentence.length <= safeMaxChars) {
    return preferredSentence
  }

  return truncateSentence(preferredSentence, safeMaxChars)
}

export function normalizePlanningPhase(phase: string | null | undefined): PlanningPhase {
  if (phase && PLANNING_PHASES.includes(phase as PlanningPhase)) {
    return phase as PlanningPhase
  }
  return 'received'
}

export function createPlanningPreviewBatcher(
  onFlush: (nextText: string) => void,
  delayMs: number = STREAMING_FRAME_BATCH_MS,
) {
  let previewTimer: ReturnType<typeof setTimeout> | null = null
  let pendingText: string | null = null
  let hasFlushedPreview = false

  const cancelPending = (): void => {
    if (previewTimer !== null) {
      clearTimeout(previewTimer)
      previewTimer = null
    }
    pendingText = null
  }

  const flushPending = (): void => {
    previewTimer = null
    if (pendingText === null) return
    const nextText = pendingText
    pendingText = null
    hasFlushedPreview = true
    onFlush(nextText)
  }

  const push = (nextText: string): void => {
    const normalized = nextText || ''

    if (!hasFlushedPreview) {
      hasFlushedPreview = true
      onFlush(normalized)
      return
    }

    pendingText = normalized
    if (previewTimer !== null) return
    previewTimer = setTimeout(flushPending, delayMs)
  }

  const reset = (nextText: string = ''): void => {
    cancelPending()
    hasFlushedPreview = nextText.length > 0
    onFlush(nextText)
  }

  const dispose = (): void => {
    cancelPending()
  }

  return {
    push,
    reset,
    cancelPending,
    dispose,
  }
}

export function buildPlanningCardState(args: BuildPlanningCardStateArgs): PlanningCardState | null {
  const { planningProgress, isThinkingStreaming, thinkingText } = args

  if (planningProgress) {
    return {
      phase: planningProgress.phase,
      message: planningProgress.message,
      progressPercent: planningProgress.percent,
      complexityCategory: planningProgress.complexityCategory,
    }
  }

  if (!isThinkingStreaming) {
    return null
  }

  const thinkingPreview = summarizeThinkingText(thinkingText)
  if (!thinkingPreview) {
    return null
  }

  return {
    phase: 'received',
    message: thinkingPreview,
    progressPercent: undefined,
    complexityCategory: undefined,
  }
}
