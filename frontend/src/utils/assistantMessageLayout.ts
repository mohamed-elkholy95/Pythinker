import type { AttachmentsContent, Message, MessageContent } from '../types/message';
import { stripLeakedToolCallMarkup } from './messageSanitizer';

const STRUCTURED_SUMMARY_MIN_LENGTH = 160;
const INLINE_TOOL_CALL_PLACEHOLDER_RE = /^\s*\[\[(?:TOOL_CALL|FUNCTION_CALL):[\s\S]*\]\]\s*$/i;
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

export const hasRenderableAssistantContent = (text: string | null | undefined): boolean => {
  if (!text) return false;
  if (INLINE_TOOL_CALL_PLACEHOLDER_RE.test(text)) return false;

  return stripLeakedToolCallMarkup(text).trim().length > 0;
};

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

export const findRenderableAssistantMessageIdInCurrentTurn = (
  messages: Message[],
): string | null => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type === 'user') break;
    if (message.type !== 'assistant') continue;

    const assistantText = (message.content as MessageContent).content || '';
    if (hasRenderableAssistantContent(assistantText)) {
      return message.id;
    }
  }

  return null;
};

/**
 * Returns true when an assistant message is sandwiched between step/tool messages
 * (i.e. it is a mid-execution step result, not the final handoff to the user).
 *
 * These messages should be completely hidden — they break the visual continuity
 * of the step timeline and surface intermediate artefacts like Reliability Notices
 * that belong only in the final delivered answer.
 */
export const isMidExecutionStepResult = (messages: Message[], messageIndex: number): boolean => {
  const current = messages[messageIndex];
  if (!current || current.type !== 'assistant') return false;

  const prev = messages[messageIndex - 1];
  const next = messages[messageIndex + 1];

  const prevIsActivity = prev?.type === 'step' || prev?.type === 'tool' || prev?.type === 'phase';
  const nextIsActivity = next?.type === 'step' || next?.type === 'tool' || next?.type === 'phase';

  // Suppress when sandwiched between agent activity events — the next step/tool
  // makes it clear the agent is still working, not delivering a final answer.
  return prevIsActivity && nextIsActivity;
};

export const hasVisibleAgentActivityInCurrentTurn = (
  messages: Message[],
): boolean => {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type === 'user') break;

    if (message.type === 'assistant') {
      const assistantText = (message.content as MessageContent).content || '';
      if (hasRenderableAssistantContent(assistantText)) {
        return true;
      }
      continue;
    }

    if (message.type === 'attachments') {
      const attachmentsContent = message.content as AttachmentsContent;
      if (attachmentsContent.role === 'assistant') {
        return true;
      }
      continue;
    }

    if (
      message.type === 'step' ||
      message.type === 'tool' ||
      message.type === 'report' ||
      message.type === 'skill_delivery' ||
      message.type === 'thought' ||
      message.type === 'phase'
    ) {
      return true;
    }
  }

  return false;
};

/**
 * Controls when the assistant brand row (bot icon + Pythinker wordmark)
 * should be shown for assistant messages in the chat timeline.
 */
export const shouldShowAssistantHeaderForMessage = (
  messages: Message[],
  messageIndex: number,
  options?: {
    activeAssistantMessageId?: string | null;
    showFloatingThinkingIndicator?: boolean;
  },
): boolean => {
  const currentMessage = messages[messageIndex];
  if (!currentMessage || currentMessage.type !== 'assistant') return false;

  const assistantText = (currentMessage.content as MessageContent).content || '';
  if (!hasRenderableAssistantContent(assistantText)) return false;

  if (options?.showFloatingThinkingIndicator && currentMessage.id === options.activeAssistantMessageId) {
    return false;
  }

  const previousMessage = messages[messageIndex - 1];
  if (!previousMessage) return true;

  // Collapse consecutive assistant headers to avoid repeated chrome.
  if (previousMessage.type === 'assistant') return false;

  // For step/tool transitions, show header only for summary/report hand-off text.
  if (previousMessage.type === 'step' || previousMessage.type === 'tool') {
    const nextMessage = messages[messageIndex + 1];
    const transitionsIntoReport = nextMessage?.type === 'report';

    return isStructuredSummaryAssistantMessage(stripLeakedToolCallMarkup(assistantText)) || transitionsIntoReport;
  }

  return true;
};
