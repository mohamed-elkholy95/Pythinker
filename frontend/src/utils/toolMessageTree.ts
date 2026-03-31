import type { Message, StepContent, ToolContent } from '@/types/message';

export interface ToolMessageLocation {
  messageIndex: number;
  toolIndex?: number;
}

export interface SyncToolMessageOptions {
  createMessageId: () => string;
  lastStep?: StepContent;
}

const isToolMessage = (message: Message): message is Message & { type: 'tool'; content: ToolContent } => {
  return message.type === 'tool';
};

const isStepMessage = (message: Message): message is Message & { type: 'step'; content: StepContent } => {
  return message.type === 'step';
};

const getToolAtLocation = (messages: Message[], location: ToolMessageLocation): ToolContent => {
  const message = messages[location.messageIndex];
  if (isToolMessage(message)) {
    return message.content;
  }

  if (!isStepMessage(message) || location.toolIndex === undefined) {
    throw new Error(`Invalid tool location at message index ${location.messageIndex}`);
  }

  const tool = message.content.tools[location.toolIndex];
  if (!tool) {
    throw new Error(`Missing tool at step index ${location.toolIndex}`);
  }
  return tool;
};

const findToolLocations = (messages: Message[], toolCallId: string): ToolMessageLocation[] => {
  const locations: ToolMessageLocation[] = [];

  for (let messageIndex = 0; messageIndex < messages.length; messageIndex += 1) {
    const message = messages[messageIndex];

    if (isToolMessage(message) && message.content.tool_call_id === toolCallId) {
      locations.push({ messageIndex });
      continue;
    }

    if (!isStepMessage(message)) {
      continue;
    }

    for (let toolIndex = 0; toolIndex < message.content.tools.length; toolIndex += 1) {
      if (message.content.tools[toolIndex]?.tool_call_id === toolCallId) {
        locations.push({ messageIndex, toolIndex });
      }
    }
  }

  return locations;
};

const isStepLocation = (location: ToolMessageLocation): boolean => {
  return location.toolIndex !== undefined;
};

const pickCanonicalToolLocation = (locations: ToolMessageLocation[]): ToolMessageLocation => {
  const stepLocation = [...locations].reverse().find((location) => isStepLocation(location));
  if (stepLocation) {
    return stepLocation;
  }

  return locations[locations.length - 1];
};

const pruneDuplicateToolLocations = (
  messages: Message[],
  toolCallId: string,
  keepLocation: ToolMessageLocation,
): void => {
  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = messages[messageIndex];

    if (isToolMessage(message)) {
      if (message.content.tool_call_id !== toolCallId) continue;
      if (messageIndex === keepLocation.messageIndex && keepLocation.toolIndex === undefined) continue;
      messages.splice(messageIndex, 1);
      continue;
    }

    if (!isStepMessage(message)) {
      continue;
    }

    for (let toolIndex = message.content.tools.length - 1; toolIndex >= 0; toolIndex -= 1) {
      const tool = message.content.tools[toolIndex];
      if (tool.tool_call_id !== toolCallId) continue;
      if (messageIndex === keepLocation.messageIndex && toolIndex === keepLocation.toolIndex) continue;
      message.content.tools.splice(toolIndex, 1);
    }
  }
};

export const syncToolMessage = (
  messages: Message[],
  toolContent: ToolContent,
  options: SyncToolMessageOptions,
): ToolContent => {
  const locations = findToolLocations(messages, toolContent.tool_call_id);

  if (locations.length > 0) {
    const keepLocation = pickCanonicalToolLocation(locations);
    const existingTool = getToolAtLocation(messages, keepLocation);
    Object.assign(existingTool, toolContent);
    pruneDuplicateToolLocations(messages, toolContent.tool_call_id, keepLocation);
    return existingTool;
  }

  if (options.lastStep?.status === 'running') {
    options.lastStep.tools.push(toolContent);
    return toolContent;
  }

  messages.push({
    id: options.createMessageId(),
    type: 'tool',
    content: toolContent,
  });

  return toolContent;
};
