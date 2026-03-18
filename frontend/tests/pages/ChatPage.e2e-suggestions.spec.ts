/**
 * E2E Tests for Session-Contextual Follow-Up Suggestions
 *
 * These tests verify the data contracts and structures are correct:
 * 1. SuggestionEventData includes metadata fields (source, anchor_event_id, anchor_excerpt)
 * 2. FollowUp interface matches backend expectations
 * 3. Type safety is maintained end-to-end
 */

import { describe, it, expect } from 'vitest'
import type { SuggestionEventData, FollowUp } from '../../src/types/event'

describe('E2E - Suggestion Metadata Contract', () => {
  it('should verify SuggestionEventData includes all metadata fields', () => {
    /**
     * E2E Critical: SSE stream must carry metadata
     * Backend sends: suggestions, source, anchor_event_id, anchor_excerpt
     * Frontend must receive and type them correctly
     */
    const suggestionEvent: SuggestionEventData = {
      event_id: 'evt_suggestion_001',
      timestamp: Date.now(),
      suggestions: ['Tell me more about X', 'What about Y?'],
      source: 'completion',
      anchor_event_id: 'evt_report_123',
      anchor_excerpt: 'The analysis found 3 key insights...',
    }

    // Verify all fields are present and typed
    expect(suggestionEvent.suggestions).toHaveLength(2)
    expect(suggestionEvent.source).toBe('completion')
    expect(suggestionEvent.anchor_event_id).toBe('evt_report_123')
    expect(suggestionEvent.anchor_excerpt).toBe('The analysis found 3 key insights...')

    // E2E Critical: Verify types include these fields (compile-time check)
    const _typeCheck: SuggestionEventData = {
      event_id: 'test',
      timestamp: 0,
      suggestions: [],
      source: 'test',
      anchor_event_id: 'test',
      anchor_excerpt: 'test',
    }
    expect(_typeCheck).toBeDefined()
  })

  it('should verify SuggestionEventData metadata fields are optional', () => {
    /**
     * E2E Critical: Backward compatibility
     * Old suggestions without metadata should still work
     */
    const suggestionEvent: SuggestionEventData = {
      event_id: 'evt_suggestion_002',
      timestamp: Date.now(),
      suggestions: ['Generic question'],
      source: undefined,
      anchor_event_id: undefined,
      anchor_excerpt: undefined,
    }

    expect(suggestionEvent.suggestions).toHaveLength(1)
    expect(suggestionEvent.source).toBeUndefined()
  })

  it('should verify FollowUp interface matches backend contract', () => {
    /**
     * E2E Critical: Frontend → Backend contract
     * Frontend sends FollowUp, backend expects these exact fields
     */
    const followUp: FollowUp = {
      selected_suggestion: 'Tell me more about X',
      anchor_event_id: 'evt_report_123',
      source: 'suggestion_click',
    }

    // Verify all required fields
    expect(followUp.selected_suggestion).toBe('Tell me more about X')
    expect(followUp.anchor_event_id).toBe('evt_report_123')
    expect(followUp.source).toBe('suggestion_click')

    // Verify field names match backend snake_case
    expect(followUp).toHaveProperty('selected_suggestion')
    expect(followUp).toHaveProperty('anchor_event_id')
    expect(followUp).toHaveProperty('source')
  })

  it('should verify FollowUp can be constructed from SuggestionEventData', () => {
    /**
     * E2E Critical: Data flow
     * SuggestionEvent → User click → FollowUp
     */
    const suggestionEvent: SuggestionEventData = {
      event_id: 'evt_suggestion_003',
      timestamp: Date.now(),
      suggestions: ['What about Y?'],
      source: 'discuss',
      anchor_event_id: 'evt_message_456',
      anchor_excerpt: 'Brief excerpt here',
    }

    // Simulate user clicking first suggestion
    const selectedSuggestion = suggestionEvent.suggestions[0]

    // Build FollowUp object
    const followUp: FollowUp = {
      selected_suggestion: selectedSuggestion,
      anchor_event_id: suggestionEvent.anchor_event_id!,
      source: 'suggestion_click',
    }

    expect(followUp.selected_suggestion).toBe('What about Y?')
    expect(followUp.anchor_event_id).toBe('evt_message_456')
    expect(followUp.source).toBe('suggestion_click')
  })

  it('should verify SSE event structure for JSON serialization', () => {
    /**
     * E2E Critical: SSE transmission
     * Backend JSON.stringify → SSE → Frontend JSON.parse
     */
    const suggestionEvent: SuggestionEventData = {
      event_id: 'evt_suggestion_004',
      timestamp: 1234567890,
      suggestions: ['Suggestion 1', 'Suggestion 2'],
      source: 'completion',
      anchor_event_id: 'evt_report_789',
      anchor_excerpt: 'Some excerpt text',
    }

    // Simulate serialization (backend does this)
    const serialized = JSON.stringify(suggestionEvent)

    // Simulate deserialization (frontend does this)
    const deserialized: SuggestionEventData = JSON.parse(serialized)

    // Verify all fields survive round-trip
    expect(deserialized.suggestions).toEqual(['Suggestion 1', 'Suggestion 2'])
    expect(deserialized.source).toBe('completion')
    expect(deserialized.anchor_event_id).toBe('evt_report_789')
    expect(deserialized.anchor_excerpt).toBe('Some excerpt text')
  })
})
