import { describe, expect, it } from 'vitest'

import { stripLeakedToolCallMarkup } from '../messageSanitizer'

describe('messageSanitizer', () => {
  describe('stripLeakedToolCallMarkup', () => {
    it('returns empty string for null input', () => {
      expect(stripLeakedToolCallMarkup(null)).toBe('')
    })

    it('returns empty string for undefined input', () => {
      expect(stripLeakedToolCallMarkup(undefined)).toBe('')
    })

    it('returns empty string for empty string input', () => {
      expect(stripLeakedToolCallMarkup('')).toBe('')
    })

    it('preserves clean text unchanged', () => {
      const text = 'Got it! I will research AI trends.'
      expect(stripLeakedToolCallMarkup(text)).toBe(text)
    })

    it('strips leaked tool_call block markup', () => {
      const text =
        'Got it! I will research the latest AI/ML engineering roadmaps for you. ' +
        ' adaptor {"tool":"Browser","params":{"task":"research"}} adaptor'
      const result = stripLeakedToolCallMarkup(text)
      expect(result).not.toContain(' adaptor')
      expect(result).toContain('roadmaps for you.')
    })

    it('strips orphaned tool_call closing tags', () => {
      const text = 'Processing complete.  adaptor/function_call>'
      const result = stripLeakedToolCallMarkup(text)
      expect(result).not.toContain(' adaptor')
      expect(result).not.toContain('/function_call>')
    })
  })

  describe('trailing raw tool payload stripping', () => {
    it('strips multi-key JSON payload with word-boundary keys', () => {
      const text =
        "Got it! I'll research best practices for professional code setup. " +
        '{"query": "setup best practices", "top_n": 10, "source": "web"}'

      expect(stripLeakedToolCallMarkup(text)).toBe(
        "Got it! I'll research best practices for professional code setup.",
      )
    })

    it('strips single-key JSON payload with structural key-colon pattern', () => {
      const text =
        'Let me search for that. {"query": "AI trends 2025"}'
      expect(stripLeakedToolCallMarkup(text)).toBe('Let me search for that.')
    })

    it('does NOT strip legitimate prose containing "furniture"', () => {
      // "url" is a payload key but "furniture" contains "url" as substring.
      // Word-boundary matching should prevent this false positive.
      const text = 'Check out our new {furniture: "couch", price: "$200"} catalog'
      expect(stripLeakedToolCallMarkup(text)).toBe(
        'Check out our new {furniture: "couch", price: "$200"} catalog',
      )
    })

    it('does NOT strip legitimate prose containing "multitasking"', () => {
      // "task" is a payload key but "multitasking" contains "task" as substring.
      const text = 'Tips for {multitasking: "effective", priority: "high"} at work'
      expect(stripLeakedToolCallMarkup(text)).toBe(
        'Tips for {multitasking: "effective", priority: "high"} at work',
      )
    })

    it('does NOT strip array with word "query" in prose context', () => {
      // The array contains "query results" which is prose, not a JSON key.
      const text = 'Results are: [10, "query results", 30]'
      expect(stripLeakedToolCallMarkup(text)).toBe('Results are: [10, "query results", 30]')
    })

    it('strips short fragment tail below threshold', () => {
      // Fragments shorter than 8 chars should be left alone
      const text = 'Done. {a:1}'
      expect(stripLeakedToolCallMarkup(text)).toBe('Done. {a:1}')
    })

    it('strips tool + arguments key-colon JSON even with mixed chars', () => {
      const text =
        'I will research this now. {"tool": "search", "arguments": {"q": "test"}}'
      expect(stripLeakedToolCallMarkup(text)).toBe('I will research this now.')
    })

    it('handles array-style payload with multiple keys', () => {
      const text =
        'Starting research. [{"tool": "browser", "url": "https://example.com", "task": "scrape"}]'
      expect(stripLeakedToolCallMarkup(text)).toBe('Starting research.')
    })
  })
})
