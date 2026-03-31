import { describe, expect, it } from 'vitest';

import type { Message, MessageContent, StepContent, ToolContent } from '@/types/message';

import { syncToolMessage } from '../toolMessageTree';

const createTool = (overrides: Partial<ToolContent> = {}): ToolContent => ({
  timestamp: 1,
  tool_call_id: 'tool-1',
  name: 'skill_invoke',
  function: 'skill_invoke',
  args: {},
  status: 'calling',
  ...overrides,
});

const countToolOccurrences = (messages: Message[], toolCallId: string): number => {
  let count = 0;

  for (const message of messages) {
    if (message.type === 'tool' && (message.content as ToolContent).tool_call_id === toolCallId) {
      count += 1;
      continue;
    }

    if (message.type === 'step') {
      const step = message.content as StepContent;
      count += step.tools.filter((tool) => tool.tool_call_id === toolCallId).length;
    }
  }

  return count;
};

describe('syncToolMessage', () => {
  it('updates an existing top-level tool instead of appending a duplicate', () => {
    const messages: Message[] = [
      {
        id: 'user-1',
        type: 'user',
        content: {
          timestamp: 0,
          event_id: 'evt-user-1',
          content: 'Hello',
        } as MessageContent,
      },
      {
        id: 'tool-message-1',
        type: 'tool',
        content: createTool({
          status: 'running',
          stdout: 'old',
        }),
      },
    ];

    const synced = syncToolMessage(messages, createTool({
      status: 'called',
      stdout: 'new',
    }), {
      createMessageId: () => 'tool-message-2',
    });

    expect(messages).toHaveLength(2);
    expect(countToolOccurrences(messages, 'tool-1')).toBe(1);
    expect(messages[1].type).toBe('tool');
    expect((messages[1].content as ToolContent).stdout).toBe('new');
    expect(synced).toBe(messages[1].content);
  });

  it('updates an existing step tool instead of creating a standalone duplicate', () => {
    const step: StepContent = {
      timestamp: 2,
      id: 'step-1',
      description: 'Run skill',
      status: 'running',
      tools: [createTool({ status: 'running', stderr: 'old' })],
    };

    const messages: Message[] = [
      {
        id: 'step-message-1',
        type: 'step',
        content: step,
      },
    ];

    const synced = syncToolMessage(messages, createTool({
      status: 'called',
      stderr: 'new',
    }), {
      createMessageId: () => 'tool-message-2',
      lastStep: step,
    });

    expect(messages).toHaveLength(1);
    expect(countToolOccurrences(messages, 'tool-1')).toBe(1);
    expect(step.tools[0].stderr).toBe('new');
    expect(synced).toBe(step.tools[0]);
  });

  it('collapses duplicate top-level tool messages into one canonical entry', () => {
    const messages: Message[] = [
      {
        id: 'tool-message-1',
        type: 'tool',
        content: createTool({
          status: 'running',
          stdout: 'older-top-level',
        }),
      },
      {
        id: 'tool-message-2',
        type: 'tool',
        content: createTool({
          status: 'called',
          stdout: 'latest-top-level',
        }),
      },
    ];

    const synced = syncToolMessage(messages, createTool({
      status: 'called',
      stdout: 'latest-top-level',
    }), {
      createMessageId: () => 'tool-message-2',
    });

    expect(messages).toHaveLength(1);
    expect(countToolOccurrences(messages, 'tool-1')).toBe(1);
    expect(messages[0].type).toBe('tool');
    expect((messages[0].content as ToolContent).stdout).toBe('latest-top-level');
    expect(synced).toBe(messages[0].content);
  });

  it('prefers the step-contained tool when both step and top-level copies exist', () => {
    const stepTool = createTool({
      status: 'running',
      stdout: 'step-canonical',
    });
    const step: StepContent = {
      timestamp: 2,
      id: 'step-1',
      description: 'Run skill',
      status: 'running',
      tools: [stepTool],
    };

    const topLevelTool = createTool({
      status: 'running',
      stdout: 'top-level-duplicate',
    });

    const messages: Message[] = [
      {
        id: 'step-message-1',
        type: 'step',
        content: step,
      },
      {
        id: 'tool-message-1',
        type: 'tool',
        content: topLevelTool,
      },
    ];

    const synced = syncToolMessage(messages, createTool({
      status: 'called',
      stdout: 'latest',
    }), {
      createMessageId: () => 'tool-message-2',
    });

    expect(messages).toHaveLength(1);
    expect(countToolOccurrences(messages, 'tool-1')).toBe(1);
    expect(step.tools).toHaveLength(1);
    expect(step.tools[0].stdout).toBe('latest');
    expect(messages[0].type).toBe('step');
    expect(synced).toBe(step.tools[0]);
  });
});
