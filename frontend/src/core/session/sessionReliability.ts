export interface SessionReliabilitySummary {
  autoRetryCount: number
  fallbackPollAttempts: number
  staleDetectionCount: number
  duplicateEventDrops: number
  maxQueueDepth: number
  averageFlushBatchSize: number
  maxChunkProcessingDurationMs: number
}

export type SessionReliabilityCounter =
  | 'autoRetryCount'
  | 'fallbackPollAttempts'
  | 'staleDetectionCount'
  | 'duplicateEventDrops'

interface SessionReliabilityAccumulator extends Omit<SessionReliabilitySummary, 'averageFlushBatchSize'> {
  flushBatchCount: number
  flushBatchSizeTotal: number
}

export const createSessionReliabilityAccumulator = (): SessionReliabilityAccumulator => ({
  autoRetryCount: 0,
  fallbackPollAttempts: 0,
  staleDetectionCount: 0,
  duplicateEventDrops: 0,
  maxQueueDepth: 0,
  maxChunkProcessingDurationMs: 0,
  flushBatchCount: 0,
  flushBatchSizeTotal: 0,
})

export const incrementSessionReliabilityCounter = (
  accumulator: SessionReliabilityAccumulator,
  counter: SessionReliabilityCounter,
): void => {
  accumulator[counter] += 1
}

export const recordSessionQueueDepth = (
  accumulator: SessionReliabilityAccumulator,
  queueDepth: number,
): void => {
  accumulator.maxQueueDepth = Math.max(accumulator.maxQueueDepth, queueDepth)
}

export const recordSessionFlushBatchSize = (
  accumulator: SessionReliabilityAccumulator,
  batchSize: number,
): void => {
  accumulator.flushBatchCount += 1
  accumulator.flushBatchSizeTotal += batchSize
}

export const recordSessionChunkProcessingDuration = (
  accumulator: SessionReliabilityAccumulator,
  durationMs: number,
): void => {
  accumulator.maxChunkProcessingDurationMs = Math.max(
    accumulator.maxChunkProcessingDurationMs,
    durationMs,
  )
}

export const snapshotSessionReliability = (
  accumulator: SessionReliabilityAccumulator,
): SessionReliabilitySummary => ({
  autoRetryCount: accumulator.autoRetryCount,
  fallbackPollAttempts: accumulator.fallbackPollAttempts,
  staleDetectionCount: accumulator.staleDetectionCount,
  duplicateEventDrops: accumulator.duplicateEventDrops,
  maxQueueDepth: accumulator.maxQueueDepth,
  averageFlushBatchSize: accumulator.flushBatchCount === 0
    ? 0
    : accumulator.flushBatchSizeTotal / accumulator.flushBatchCount,
  maxChunkProcessingDurationMs: accumulator.maxChunkProcessingDurationMs,
})

export const hasSessionReliabilitySignals = (
  summary: SessionReliabilitySummary,
): boolean => {
  return summary.autoRetryCount > 0
    || summary.fallbackPollAttempts > 0
    || summary.staleDetectionCount > 0
    || summary.duplicateEventDrops > 0
    || summary.maxQueueDepth > 0
    || summary.averageFlushBatchSize > 0
    || summary.maxChunkProcessingDurationMs > 0
}

export const serializeSessionReliabilitySummary = (
  summary: SessionReliabilitySummary,
): string => {
  return JSON.stringify(summary)
}
