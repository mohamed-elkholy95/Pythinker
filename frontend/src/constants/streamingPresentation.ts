export type StreamPhase = 'idle' | 'planning' | 'thinking' | 'summarizing' | 'summary_final';

export type StreamingViewType = 'live_preview' | 'terminal' | 'editor' | 'search' | 'generic' | 'report';

export const STREAMING_LABELS = {
  thinking: 'Thinking',
  planning_active: 'Creating plan...',
  planning_final: 'Plan ready',
  summarizing_active: 'Writing report...',
  summarizing_final: 'Report complete',
  completed: 'Session complete',
  initializing: 'Initializing',
  waiting: 'Initializing',
} as const;

export const THINKING_ROTATING_LABELS = [
  'Thinking',
  'Analyzing',
  'Reasoning',
  'Processing',
  'Exploring',
  'Researching',
  'Evaluating',
  'Pondering',
] as const;

export const THINKING_ROTATION_INTERVAL_MS = 3000;

export const VALID_PHASE_TRANSITIONS: Record<StreamPhase, ReadonlyArray<StreamPhase>> = {
  idle: ['planning', 'thinking', 'summarizing'],
  planning: ['thinking', 'idle', 'summarizing', 'summary_final'],
  thinking: ['summarizing', 'idle'],
  summarizing: ['summary_final', 'idle'],
  summary_final: ['idle'],
};

export const STREAMING_STALE_TIMEOUT_MS = 30000;
export const STREAMING_FRAME_BATCH_MS = 16;
