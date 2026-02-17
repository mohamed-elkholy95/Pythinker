export type StreamPhase = 'idle' | 'thinking' | 'summarizing' | 'summary_final';

export type StreamingViewType = 'live_preview' | 'terminal' | 'editor' | 'search' | 'generic' | 'report';

export const STREAMING_LABELS = {
  thinking: 'Thinking',
  summarizing_active: 'Composing report...',
  summarizing_final: 'Report complete',
  completed: 'Session complete',
  initializing: 'Initializing',
  waiting: 'Initializing',
} as const;

export const VALID_PHASE_TRANSITIONS: Record<StreamPhase, ReadonlyArray<StreamPhase>> = {
  idle: ['thinking', 'summarizing'],
  thinking: ['summarizing', 'idle'],
  summarizing: ['summary_final', 'idle'],
  summary_final: ['idle'],
};

export const STREAMING_STALE_TIMEOUT_MS = 30000;
export const STREAMING_FRAME_BATCH_MS = 16;
