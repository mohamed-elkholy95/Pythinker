import { describe, expect, it } from 'vitest';

import type { Message, PhaseContent } from '@/types/message';

import { syncPhaseMessage } from '../phaseMessages';

const createPhase = (overrides: Partial<PhaseContent> = {}): PhaseContent => ({
  timestamp: 1,
  phase_id: 'phase-1',
  phase_type: 'planning',
  label: 'Planning',
  status: 'started',
  steps: [],
  ...overrides,
});

describe('syncPhaseMessage', () => {
  it('updates an existing phase instead of appending a duplicate', () => {
    const messages: Message[] = [
      {
        id: 'phase-message-1',
        type: 'phase',
        content: createPhase({
          status: 'started',
          label: 'Old label',
        }),
      },
    ];

    const synced = syncPhaseMessage(messages, createPhase({
      status: 'completed',
      label: 'New label',
      skip_reason: 'done',
    }), () => 'phase-message-2');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('phase');
    expect((messages[0].content as PhaseContent).status).toBe('completed');
    expect((messages[0].content as PhaseContent).label).toBe('New label');
    expect((messages[0].content as PhaseContent).skip_reason).toBe('done');
    expect(synced).toBe(messages[0].content);
  });

  it('keeps the phase copy that already owns nested steps', () => {
    const messages: Message[] = [
      {
        id: 'phase-message-1',
        type: 'phase',
        content: createPhase({
          label: 'Empty shell',
        }),
      },
      {
        id: 'phase-message-2',
        type: 'phase',
        content: createPhase({
          label: 'Step owner',
          steps: [
            {
              timestamp: 2,
              id: 'step-1',
              description: 'Research',
              status: 'running',
              tools: [],
            },
          ],
        }),
      },
    ];

    const synced = syncPhaseMessage(messages, createPhase({
      label: 'Latest label',
      status: 'skipped',
    }), () => 'phase-message-3');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('phase');
    expect((messages[0].content as PhaseContent).label).toBe('Latest label');
    expect((messages[0].content as PhaseContent).steps).toHaveLength(1);
    expect(synced).toBe(messages[0].content);
  });
});
