import { describe, expect, it } from 'vitest';

import type { ToolProgressEventData } from '@/types/event';

import { buildTimelineEntryFromToolProgress } from '../toolProgressTimeline';

const makeProgressEvent = (overrides: Partial<ToolProgressEventData> = {}): ToolProgressEventData => ({
  event_id: overrides.event_id || 'evt-progress-1',
  timestamp: overrides.timestamp || 1710000000,
  tool_call_id: overrides.tool_call_id || 'tool-search-1',
  tool_name: overrides.tool_name || 'search',
  function_name: overrides.function_name || 'info_search_web',
  progress_percent: overrides.progress_percent || 50,
  current_step: overrides.current_step || 'Previewing result 1',
  steps_completed: overrides.steps_completed || 1,
  steps_total: overrides.steps_total || 3,
  elapsed_ms: overrides.elapsed_ms || 1200,
  estimated_remaining_ms: overrides.estimated_remaining_ms,
  checkpoint_data: overrides.checkpoint_data,
});

describe('buildTimelineEntryFromToolProgress', () => {
  it('builds a synthetic timeline entry for sandbox checkpoints', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {
        action: 'navigate',
        action_function: 'browser_navigate',
        url: 'https://example.com/article',
        step: 1,
      },
    }));

    expect(entry).not.toBeNull();
    expect(entry?.tool_call_id).toBe('tool-progress:tool-search-1:1');
    expect(entry?.function).toBe('browser_navigate');
    expect(entry?.args.url).toBe('https://example.com/article');
    expect(entry?.display_command).toBe('Previewing result 1');
  });

  it('returns null when the progress event has no usable checkpoint details', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {
        note: 'background update',
      },
    }));

    expect(entry).toBeNull();
  });

  it('falls back to the parent function name when checkpoint action_function is absent', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      function_name: 'browser_agent_run',
      checkpoint_data: {
        action: 'wait',
        url: 'https://example.com/loading',
      },
    }));

    expect(entry?.function).toBe('browser_agent_run');
    expect(entry?.command_category).toBe('browse');
  });

  it('uses backend-provided command_category from checkpoint_data', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {
        action: 'search',
        action_function: 'info_search_web',
        query: 'test',
        step: 1,
        command_category: 'search',
      },
    }));

    expect(entry?.command_category).toBe('search');
  });

  it('builds entry from coordinate-based checkpoint (no URL)', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      function_name: 'browser_agent_run',
      checkpoint_data: {
        action: 'click_element',
        action_function: 'browser_agent_run',
        coordinate_x: 200,
        coordinate_y: 450,
        index: 5,
        step: 3,
        command_category: 'browse',
      },
    }));

    expect(entry).not.toBeNull();
    expect(entry?.args.coordinate_x).toBe(200);
    expect(entry?.args.coordinate_y).toBe(450);
    expect(entry?.tool_call_id).toBe('tool-progress:tool-search-1:5');
    expect(entry?.command_category).toBe('browse');
  });

  it('builds entry from query-only checkpoint', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {
        action: 'search',
        action_function: 'wide_research',
        query: 'AI hardware 2026',
        step: 1,
        command_category: 'search',
      },
    }));

    expect(entry).not.toBeNull();
    expect(entry?.args.query).toBe('AI hardware 2026');
    expect(entry?.command_category).toBe('search');
  });

  it('returns null for empty checkpoint object', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {},
    }));

    expect(entry).toBeNull();
  });

  it('returns null when checkpoint_data is null', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: null,
    }));

    expect(entry).toBeNull();
  });

  it('uses index 0 when neither index nor step is present', () => {
    const entry = buildTimelineEntryFromToolProgress(makeProgressEvent({
      checkpoint_data: {
        action: 'navigate',
        url: 'https://example.com',
      },
    }));

    expect(entry?.tool_call_id).toBe('tool-progress:tool-search-1:0');
  });
});
