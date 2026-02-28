import { describe, expect, it } from 'vitest';

import type { Message, StepContent, ToolContent } from '@/types/message';

import { isToolResultMissing, normalizeTransientTools } from '../sessionFinalization';

const makeTool = (toolCallId: string, status: ToolContent['status'], result?: unknown): ToolContent => ({
  tool_call_id: toolCallId,
  name: 'test_tool',
  function: 'test_function',
  args: {},
  status,
  timestamp: 1,
  content: result === undefined ? undefined : { result } as ToolContent['content'],
});

describe('sessionFinalization', () => {
  it('normalizes transient tools to interrupted across all stores', () => {
    const directTool = makeTool('direct', 'calling');
    const stepToolRunning = makeTool('step-running', 'running');
    const stepToolTerminal = makeTool('step-terminal', 'called');

    const messages: Message[] = [
      { id: 'm1', type: 'tool', content: directTool },
      {
        id: 'm2',
        type: 'step',
        content: {
          id: 'step-1',
          description: 'step',
          status: 'running',
          timestamp: 1,
          tools: [stepToolRunning, stepToolTerminal],
        } as StepContent,
      },
    ];

    const timeline = [
      makeTool('timeline-running', 'running'),
      makeTool('timeline-called', 'called'),
    ];
    const lastTool = makeTool('last-tool', 'calling');
    const lastNoMessageTool = makeTool('last-no-message', 'running');

    normalizeTransientTools({
      messages,
      toolTimeline: timeline,
      lastTool,
      lastNoMessageTool,
    });

    expect(directTool.status).toBe('interrupted');
    expect(stepToolRunning.status).toBe('interrupted');
    expect(stepToolTerminal.status).toBe('called');
    expect(timeline[0].status).toBe('interrupted');
    expect(timeline[1].status).toBe('called');
    expect(lastTool.status).toBe('interrupted');
    expect(lastNoMessageTool.status).toBe('interrupted');
  });

  it('detects tools with missing result payloads', () => {
    expect(isToolResultMissing(makeTool('a', 'interrupted'))).toBe(true);
    expect(isToolResultMissing(makeTool('b', 'called', ''))).toBe(true);
    expect(isToolResultMissing(makeTool('c', 'called', { ok: true }))).toBe(false);
  });
});
