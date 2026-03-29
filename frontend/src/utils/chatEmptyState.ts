export interface ChatEmptyStateInput {
  sessionId?: string
  messageCount: number
  hasPendingInitialMessage: boolean
  isInitializing: boolean
  isLoading: boolean
  isSandboxInitializing: boolean
  isWaitingForSessionReady: boolean
  showSessionWarmupMessage: boolean
}

export function shouldShowEmptySessionState({
  sessionId,
  messageCount,
  hasPendingInitialMessage,
  isInitializing,
  isLoading,
  isSandboxInitializing,
  isWaitingForSessionReady,
  showSessionWarmupMessage,
}: ChatEmptyStateInput): boolean {
  if (!sessionId || sessionId === 'new') return false
  if (messageCount > 0) return false
  if (hasPendingInitialMessage) return false

  return !(
    isLoading ||
    isInitializing ||
    isSandboxInitializing ||
    isWaitingForSessionReady ||
    showSessionWarmupMessage
  )
}
