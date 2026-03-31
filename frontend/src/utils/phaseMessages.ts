import type { Message, PhaseContent } from '@/types/message';

const isPhaseMessage = (message: Message): message is Message & { type: 'phase'; content: PhaseContent } => {
  return message.type === 'phase';
};

const findPhaseLocations = (messages: Message[], phaseId: string): number[] => {
  const locations: number[] = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (!isPhaseMessage(message)) continue;
    if (message.content.phase_id === phaseId) {
      locations.push(index);
    }
  }

  return locations;
};

const pickCanonicalPhaseIndex = (messages: Message[], locations: number[]): number => {
  let bestIndex = locations[locations.length - 1];
  let bestScore = Number.NEGATIVE_INFINITY;

  for (const index of locations) {
    const message = messages[index];
    if (!isPhaseMessage(message)) continue;

    const stepCount = message.content.steps.length;
    const score = stepCount > 0 ? stepCount * 1000 + index : index;
    if (score >= bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  }

  return bestIndex;
};

const pruneDuplicatePhaseMessages = (messages: Message[], phaseId: string, keepIndex: number): void => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!isPhaseMessage(message)) continue;
    if (message.content.phase_id !== phaseId) continue;
    if (index === keepIndex) continue;
    messages.splice(index, 1);
  }
};

export const syncPhaseMessage = (
  messages: Message[],
  phaseContent: PhaseContent,
  createMessageId: () => string,
): PhaseContent => {
  const locations = findPhaseLocations(messages, phaseContent.phase_id);

  if (locations.length > 0) {
    const keepIndex = pickCanonicalPhaseIndex(messages, locations);
    const existingMessage = messages[keepIndex];
    if (!isPhaseMessage(existingMessage)) {
      throw new Error(`Expected phase message at index ${keepIndex}`);
    }

    existingMessage.content.phase_type = phaseContent.phase_type;
    existingMessage.content.label = phaseContent.label;
    existingMessage.content.status = phaseContent.status;
    existingMessage.content.order = phaseContent.order;
    existingMessage.content.icon = phaseContent.icon;
    existingMessage.content.color = phaseContent.color;
    existingMessage.content.total_phases = phaseContent.total_phases;
    existingMessage.content.skip_reason = phaseContent.skip_reason;
    existingMessage.content.timestamp = phaseContent.timestamp;
    pruneDuplicatePhaseMessages(messages, phaseContent.phase_id, keepIndex);
    return existingMessage.content;
  }

  messages.push({
    id: createMessageId(),
    type: 'phase',
    content: phaseContent,
  });

  return phaseContent;
};
