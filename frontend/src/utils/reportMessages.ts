import type { Message, ReportContent } from '@/types/message';

const isReportMessage = (message: Message): message is Message & { type: 'report'; content: ReportContent } => {
  return message.type === 'report';
};

const findReportLocations = (messages: Message[], reportId: string, eventId?: string): number[] => {
  const locations: number[] = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (!isReportMessage(message)) continue;

    const content = message.content;
    if (content.id === reportId || (eventId && content.event_id === eventId)) {
      locations.push(index);
    }
  }

  return locations;
};

const pruneDuplicateReports = (messages: Message[], reportId: string, eventId: string | undefined, keepIndex: number): void => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!isReportMessage(message)) continue;

    const content = message.content;
    const matches = content.id === reportId || (eventId && content.event_id === eventId);
    if (!matches || index === keepIndex) continue;
    messages.splice(index, 1);
  }
};

export const syncReportMessage = (
  messages: Message[],
  reportContent: ReportContent,
  createMessageId: () => string,
): ReportContent => {
  const locations = findReportLocations(messages, reportContent.id, reportContent.event_id);

  if (locations.length > 0) {
    const keepIndex = locations[locations.length - 1];
    const existingMessage = messages[keepIndex];
    if (!isReportMessage(existingMessage)) {
      throw new Error(`Expected report message at index ${keepIndex}`);
    }

    existingMessage.content = reportContent;
    pruneDuplicateReports(messages, reportContent.id, reportContent.event_id, keepIndex);
    return reportContent;
  }

  messages.push({
    id: createMessageId(),
    type: 'report',
    content: reportContent,
  });

  return reportContent;
};
