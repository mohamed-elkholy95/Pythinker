import type { PlanningPhase } from '@/types/event'

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
