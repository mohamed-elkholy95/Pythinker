import { describe, expect, it } from 'vitest'
import type { Message, ReportContent, StepContent } from '@/types/message'
import {
  isStructuredSummaryAssistantMessage,
  shouldNestAssistantMessageInStep,
  shouldShowAssistantHeaderForMessage,
} from '@/utils/assistantMessageLayout'

const makeStep = (status: StepContent['status']): StepContent => ({
  id: 'step-1',
  description: 'Composing final report',
  status,
  tools: [],
  timestamp: 1700000000,
})

const makeStepMessage = (status: StepContent['status']): Message => ({
  id: `step-${status}`,
  type: 'step',
  content: makeStep(status),
})

const makeAssistantMessage = (id: string, text: string): Message => ({
  id,
  type: 'assistant',
  content: {
    content: text,
    timestamp: 1700000001,
  },
})

const makeReportMessage = (): Message => ({
  id: 'report-1',
  type: 'report',
  content: {
    id: 'report-1',
    title: 'GLM-5 vs Claude Models',
    content: '# Report',
    lastModified: Date.now(),
    timestamp: 1700000002,
  } as ReportContent,
})

const structuredSummaryText = `I have completed a comprehensive comparison of GLM-5 against Claude Sonnet 4.5 and Opus 4.6.

The report covers:

**Model Specifications:** Architecture details, parameter counts, context windows, and licensing differences.

**Performance Benchmarks:** Intelligence Index rankings, SWE-bench, and Terminal-Bench comparisons.

**Pricing Analysis:** Cost structures for deployment and API pricing tiers.

**Use Case Recommendations:** When to choose each model for customization, multimodal capabilities, and reasoning tasks.

You can find the detailed report below.`

describe('assistantMessageLayout', () => {
  describe('isStructuredSummaryAssistantMessage', () => {
    it('detects long sectioned summary content', () => {
      expect(isStructuredSummaryAssistantMessage(structuredSummaryText)).toBe(true)
    })

    it('ignores short inline narration', () => {
      expect(isStructuredSummaryAssistantMessage('Checked files and proceeding to next step.')).toBe(false)
    })
  })

  describe('shouldNestAssistantMessageInStep', () => {
    it('nests structured summaries by default to keep timeline continuity', () => {
      expect(shouldNestAssistantMessageInStep(structuredSummaryText, makeStep('running'))).toBe(true)
    })

    it('allows only explicit final-summary breakout to render outside step thread', () => {
      expect(
        shouldNestAssistantMessageInStep(structuredSummaryText, makeStep('running'), {
          allowStandaloneSummary: true,
        }),
      ).toBe(false)
    })

    it('still nests assistant text when the step is completed', () => {
      expect(shouldNestAssistantMessageInStep('Quick update', makeStep('completed'))).toBe(true)
    })

    it('does not nest into pending/non-active steps', () => {
      expect(shouldNestAssistantMessageInStep('Quick update', makeStep('pending'))).toBe(false)
    })

    it('nests short narration into active running steps', () => {
      expect(shouldNestAssistantMessageInStep('Reading the next source now.', makeStep('running'))).toBe(true)
    })
  })

  describe('shouldShowAssistantHeaderForMessage', () => {
    it('shows header for summary block after steps before report preview', () => {
      const messages: Message[] = [
        makeStepMessage('completed'),
        makeAssistantMessage('assistant-summary', structuredSummaryText),
        makeReportMessage(),
      ]

      expect(shouldShowAssistantHeaderForMessage(messages, 1)).toBe(true)
    })

    it('hides header for short inline assistant text after a step', () => {
      const messages: Message[] = [
        makeStepMessage('completed'),
        makeAssistantMessage('assistant-inline', 'Done.'),
      ]

      expect(shouldShowAssistantHeaderForMessage(messages, 1)).toBe(false)
    })

    it('hides repeated header for consecutive assistant messages', () => {
      const messages: Message[] = [
        makeAssistantMessage('assistant-1', 'First response.'),
        makeAssistantMessage('assistant-2', 'Second response.'),
      ]

      expect(shouldShowAssistantHeaderForMessage(messages, 1)).toBe(false)
    })
  })
})
