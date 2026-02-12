import type { Message, MessageContent, StepContent } from '../types/message';

const STRUCTURED_SUMMARY_MIN_LENGTH = 160;
const REPORT_HANDOFF_CUE_PATTERNS: ReadonlyArray<RegExp> = [
  /\breport\s+covers\b/i,
  /\bdetailed\s+report\b/i,
  /\bfinal\s+report\b/i,
  /\byou\s+can\s+find\s+.*\breport\b/i,
  /\b(completed|finished)\b.{0,80}\b(comparison|analysis|research|report)\b/i,
];
const REPORT_SECTION_STRUCTURE_PATTERNS: ReadonlyArray<RegExp> = [
  /(^|\n)\s*#{1,6}\s+/m,
  /(^|\n)\s*\*\*[^*\n]{3,80}:\*\*/m,
  /(^|\n)\s*[-*]\s+\*\*[^*\n]{3,80}\*\*/m,
];

/**
 * Detects structured summary-style assistant text that should be displayed as
 * a standalone assistant block instead of being nested in a step timeline.
 */
export const isStructuredSummaryAssistantMessage = (text: string): boolean => {
  const normalized = text.trim();
  if (!normalized || normalized.length < STRUCTURED_SUMMARY_MIN_LENGTH) {
    return false;
  }

  const hasHandoffCue = REPORT_HANDOFF_CUE_PATTERNS.some((pattern) => pattern.test(normalized));
  if (!hasHandoffCue) return false;

  return REPORT_SECTION_STRUCTURE_PATTERNS.some((pattern) => pattern.test(normalized));
};

/**
 * Determines whether assistant text should be rendered inline inside the
 * currently running step thread.
 */
export const shouldNestAssistantMessageInStep = (
  text: string,
  stepContent?: StepContent,
  options?: { allowStandaloneSummary?: boolean },
): boolean => {
  const normalized = text.trim();
  if (!normalized || !stepContent) return false;

  // Inline narration belongs to active step threads (running/completed).
  if (stepContent.status !== 'running' && stepContent.status !== 'completed') return false;

  // Only the final summary handoff is allowed to be standalone.
  if (options?.allowStandaloneSummary) return false;

  return true;
};

/**
 * Controls when the assistant brand row (bot icon + Pythinker wordmark)
 * should be shown for assistant messages in the chat timeline.
 */
export const shouldShowAssistantHeaderForMessage = (
  messages: Message[],
  messageIndex: number,
): boolean => {
  const currentMessage = messages[messageIndex];
  if (!currentMessage || currentMessage.type !== 'assistant') return false;

  const previousMessage = messages[messageIndex - 1];
  if (!previousMessage) return true;

  // Collapse consecutive assistant headers to avoid repeated chrome.
  if (previousMessage.type === 'assistant') return false;

  // For step/tool transitions, show header only for summary/report hand-off text.
  if (previousMessage.type === 'step' || previousMessage.type === 'tool') {
    const assistantText = ((currentMessage.content as MessageContent).content || '').trim();
    const nextMessage = messages[messageIndex + 1];
    const transitionsIntoReport = nextMessage?.type === 'report';

    return isStructuredSummaryAssistantMessage(assistantText) || transitionsIntoReport;
  }

  return true;
};
