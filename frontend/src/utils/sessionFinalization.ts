import type { Message, StepContent, ToolContent } from '@/types/message';

export const isTransientToolStatus = (status: ToolContent['status']): boolean => {
  return status === 'calling' || status === 'running';
};

export const isToolResultMissing = (tool?: ToolContent): boolean => {
  const payload = tool?.content as { result?: unknown } | undefined;
  const result = payload?.result;

  if (result === undefined || result === null) return true;
  if (typeof result === 'string' && result.trim().length === 0) return true;
  return false;
};

const markToolInterrupted = (tool?: ToolContent) => {
  if (!tool || !isTransientToolStatus(tool.status)) return;
  tool.status = 'interrupted';
};

export const normalizeTransientTools = ({
  messages,
  toolTimeline,
  lastTool,
  lastNoMessageTool,
}: {
  messages: Message[];
  toolTimeline: ToolContent[];
  lastTool?: ToolContent;
  lastNoMessageTool?: ToolContent;
}): void => {
  markToolInterrupted(lastTool);
  markToolInterrupted(lastNoMessageTool);

  for (const timelineTool of toolTimeline) {
    markToolInterrupted(timelineTool);
  }

  for (const message of messages) {
    if (message.type === 'tool') {
      markToolInterrupted(message.content as ToolContent);
      continue;
    }

    if (message.type === 'step') {
      const step = message.content as StepContent;
      for (const stepTool of step.tools) {
        markToolInterrupted(stepTool);
      }
    }
  }
};
