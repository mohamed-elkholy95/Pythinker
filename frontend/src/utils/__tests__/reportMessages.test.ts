import { describe, expect, it } from 'vitest';

import type { Message, ReportContent } from '@/types/message';

import { syncReportMessage } from '../reportMessages';

const createReport = (overrides: Partial<ReportContent> = {}): ReportContent => ({
  timestamp: 1,
  id: 'report-1',
  title: 'Final Report',
  content: 'Report body',
  lastModified: 1,
  ...overrides,
});

describe('syncReportMessage', () => {
  it('updates an existing report instead of appending a duplicate', () => {
    const messages: Message[] = [
      {
        id: 'report-message-1',
        type: 'report',
        content: createReport({
          title: 'Old title',
        }),
      },
    ];

    const synced = syncReportMessage(messages, createReport({
      title: 'New title',
      event_id: 'evt-1',
    }), () => 'report-message-2');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('report');
    expect((messages[0].content as ReportContent).title).toBe('New title');
    expect(synced).toBe(messages[0].content);
  });

  it('collapses duplicate report messages into one canonical entry', () => {
    const messages: Message[] = [
      {
        id: 'report-message-1',
        type: 'report',
        content: createReport({
          content: 'Older copy',
          event_id: 'evt-1',
        }),
      },
      {
        id: 'report-message-2',
        type: 'report',
        content: createReport({
          content: 'Latest copy',
          event_id: 'evt-1',
        }),
      },
    ];

    const synced = syncReportMessage(messages, createReport({
      content: 'Newest copy',
      event_id: 'evt-1',
    }), () => 'report-message-3');

    expect(messages).toHaveLength(1);
    expect(messages[0].type).toBe('report');
    expect((messages[0].content as ReportContent).content).toBe('Newest copy');
    expect(synced).toBe(messages[0].content);
  });
});
