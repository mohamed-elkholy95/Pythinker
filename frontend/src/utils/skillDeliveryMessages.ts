import type { Message, SkillDeliveryContent } from '@/types/message';

const isSkillDeliveryMessage = (
  message: Message,
): message is Message & { type: 'skill_delivery'; content: SkillDeliveryContent } => {
  return message.type === 'skill_delivery';
};

const findSkillDeliveryLocations = (messages: Message[], packageId: string): number[] => {
  const locations: number[] = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (!isSkillDeliveryMessage(message)) continue;
    if (message.content.package_id === packageId) {
      locations.push(index);
    }
  }

  return locations;
};

const pruneDuplicateSkillDeliveries = (
  messages: Message[],
  packageId: string,
  keepIndex: number,
): void => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!isSkillDeliveryMessage(message)) continue;
    if (message.content.package_id !== packageId) continue;
    if (index === keepIndex) continue;
    messages.splice(index, 1);
  }
};

export const syncSkillDeliveryMessage = (
  messages: Message[],
  skillDelivery: SkillDeliveryContent,
  createMessageId: () => string,
): SkillDeliveryContent => {
  const locations = findSkillDeliveryLocations(messages, skillDelivery.package_id);

  if (locations.length > 0) {
    const keepIndex = locations[locations.length - 1];
    const existingMessage = messages[keepIndex];
    if (!isSkillDeliveryMessage(existingMessage)) {
      throw new Error(`Expected skill_delivery message at index ${keepIndex}`);
    }

    Object.assign(existingMessage.content, skillDelivery);
    pruneDuplicateSkillDeliveries(messages, skillDelivery.package_id, keepIndex);
    return existingMessage.content;
  }

  messages.push({
    id: createMessageId(),
    type: 'skill_delivery',
    content: skillDelivery,
  });

  return skillDelivery;
};
