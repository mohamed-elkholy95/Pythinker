import type { ToolProgressEventData } from '@/types/event';
import type { ToolContent } from '@/types/message';

type CheckpointRecord = Record<string, unknown>;

const _stringValue = (value: unknown): string | undefined => {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined;
};

const _numberValue = (value: unknown): number | undefined => {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
};

const _extractArgs = (checkpoint: CheckpointRecord): Record<string, unknown> => {
  const args: Record<string, unknown> = {};
  const keys = ['url', 'index', 'coordinate_x', 'coordinate_y', 'x', 'y', 'action', 'step', 'query'];

  for (const key of keys) {
    const value = checkpoint[key];
    if (value !== undefined && value !== null && value !== '') {
      args[key] = value;
    }
  }

  return args;
};

export function buildTimelineEntryFromToolProgress(data: ToolProgressEventData): ToolContent | null {
  if (!data.checkpoint_data || typeof data.checkpoint_data !== 'object') return null;

  const checkpoint = data.checkpoint_data as CheckpointRecord;
  const actionFunction = _stringValue(checkpoint.action_function) || data.function_name;
  const actionUrl = _stringValue(checkpoint.url);
  const hasCoordinates =
    _numberValue(checkpoint.coordinate_x) !== undefined && _numberValue(checkpoint.coordinate_y) !== undefined;
  const actionName = _stringValue(checkpoint.action);
  const actionQuery = _stringValue(checkpoint.query);

  if (!actionUrl && !hasCoordinates && !actionName && !actionQuery) {
    return null;
  }

  // Scope synthetic ID to parent tool call + checkpoint index so subsequent
  // checkpoints for the same browse step upsert rather than accumulate.
  const index = _numberValue(checkpoint.index) ?? _numberValue(checkpoint.step) ?? 0;
  const syntheticId = `tool-progress:${data.tool_call_id}:${index}`;

  return {
    tool_call_id: syntheticId,
    event_id: data.event_id,
    name: data.tool_name,
    function: actionFunction,
    args: _extractArgs(checkpoint),
    status: 'called',
    timestamp: data.timestamp,
    display_command: data.current_step,
    command_summary: data.current_step,
    command_category: _stringValue(checkpoint.command_category)
      || (actionFunction.includes('browser') || actionFunction.includes('playwright') ? 'browse' : undefined),
    progress_percent: data.progress_percent,
    current_step: data.current_step,
    elapsed_ms: data.elapsed_ms,
    checkpoint_data: data.checkpoint_data,
  };
}
