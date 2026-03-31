import { describe, expect, it } from 'vitest';

import type { Message, SkillDeliveryContent } from '@/types/message';

import { syncSkillDeliveryMessage } from '../skillDeliveryMessages';

const createSkillDelivery = (overrides: Partial<SkillDeliveryContent> = {}): SkillDeliveryContent => ({
  timestamp: 1,
  package_id: 'pkg-1',
  name: 'Research',
  description: 'Research skill package',
  version: '1.0.0',
  icon: 'icon.svg',
  category: 'research',
  file_tree: {},
  files: [],
  ...overrides,
});

describe('syncSkillDeliveryMessage', () => {
  it('updates an existing skill delivery instead of appending a duplicate', () => {
    const messages: Message[] = [
      {
        id: 'skill-message-1',
        type: 'skill_delivery',
        content: createSkillDelivery({
          description: 'Old description',
        }),
      },
    ];

    const synced = syncSkillDeliveryMessage(messages, createSkillDelivery({
      description: 'New description',
    }), () => 'skill-message-2');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('skill_delivery');
    expect((messages[0].content as SkillDeliveryContent).description).toBe('New description');
    expect(synced).toBe(messages[0].content);
  });

  it('collapses duplicate skill delivery messages into one canonical entry', () => {
    const messages: Message[] = [
      {
        id: 'skill-message-1',
        type: 'skill_delivery',
        content: createSkillDelivery({
          description: 'Older copy',
        }),
      },
      {
        id: 'skill-message-2',
        type: 'skill_delivery',
        content: createSkillDelivery({
          description: 'Newest copy',
        }),
      },
    ];

    const synced = syncSkillDeliveryMessage(messages, createSkillDelivery({
      description: 'Latest description',
    }), () => 'skill-message-3');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('skill_delivery');
    expect((messages[0].content as SkillDeliveryContent).description).toBe('Latest description');
    expect(synced).toBe(messages[0].content);
  });
});
