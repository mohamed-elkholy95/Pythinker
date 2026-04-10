import { describe, expect, it } from 'vitest'

import type { AttachmentsContent, Message, MessageContent, StepContent } from '@/types/message'

import {
  findRenderableAssistantMessageIdInCurrentTurn,
  hasVisibleAgentActivityInCurrentTurn,
  shouldShowAssistantHeaderForMessage,
} from '../assistantMessageLayout'

const createAssistantMessage = (id: string, content: string): Message => ({
  id,
  type: 'assistant',
  content: {
    timestamp: 1,
    content,
  } as MessageContent,
})

const createUserMessage = (id: string, content: string): Message => ({
  id,
  type: 'user',
  content: {
    timestamp: 1,
    content,
  } as MessageContent,
})

const createStepMessage = (id: string, description: string): Message => ({
  id,
  type: 'step',
  content: {
    timestamp: 1,
    id,
    description,
    status: 'running',
    tools: [],
  } as StepContent,
})

const createAssistantAttachmentMessage = (id: string): Message => ({
  id,
  type: 'attachments',
  content: {
    timestamp: 1,
    role: 'assistant',
    attachments: [],
  } as AttachmentsContent,
})

describe('findRenderableAssistantMessageIdInCurrentTurn', () => {
  it('ignores assistant messages from earlier turns', () => {
    const messages: Message[] = [
      createAssistantMessage('assistant-old', 'Previous answer'),
      createUserMessage('user-latest', 'New request'),
    ]

    expect(findRenderableAssistantMessageIdInCurrentTurn(messages)).toBeNull()
  })

  it('returns the latest renderable assistant message in the current turn', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createAssistantMessage('assistant-placeholder', '[[TOOL_CALL: buffered]]'),
      createAssistantMessage('assistant-current', 'Working on it now.'),
    ]

    expect(findRenderableAssistantMessageIdInCurrentTurn(messages)).toBe('assistant-current')
  })
})

describe('shouldShowAssistantHeaderForMessage', () => {
  it('hides the active assistant header while the floating thinking indicator is visible', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createAssistantMessage('assistant-current', 'Working on it now.'),
    ]

    expect(
      shouldShowAssistantHeaderForMessage(messages, 1, {
        activeAssistantMessageId: 'assistant-current',
        showFloatingThinkingIndicator: true,
      }),
    ).toBe(false)
  })

  it('keeps the assistant header visible once the floating thinking indicator is gone', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createAssistantMessage('assistant-current', 'Working on it now.'),
    ]

    expect(
      shouldShowAssistantHeaderForMessage(messages, 1, {
        activeAssistantMessageId: 'assistant-current',
        showFloatingThinkingIndicator: false,
      }),
    ).toBe(true)
  })
})

describe('hasVisibleAgentActivityInCurrentTurn', () => {
  it('returns true when the current turn already has an assistant response', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createAssistantMessage('assistant-current', 'Working on it now.'),
    ]

    expect(hasVisibleAgentActivityInCurrentTurn(messages)).toBe(true)
  })

  it('returns true when the current turn already has a step', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createStepMessage('step-current', 'Research sources'),
    ]

    expect(hasVisibleAgentActivityInCurrentTurn(messages)).toBe(true)
  })

  it('ignores assistant activity from earlier turns', () => {
    const messages: Message[] = [
      createAssistantMessage('assistant-old', 'Previous answer'),
      createUserMessage('user-latest', 'New request'),
    ]

    expect(hasVisibleAgentActivityInCurrentTurn(messages)).toBe(false)
  })

  it('counts assistant attachment rows as visible current-turn activity', () => {
    const messages: Message[] = [
      createUserMessage('user-latest', 'New request'),
      createAssistantAttachmentMessage('attachments-current'),
    ]

    expect(hasVisibleAgentActivityInCurrentTurn(messages)).toBe(true)
  })
})
