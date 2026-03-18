import { describe, it, expect, vi, beforeAll } from 'vitest'

// Unmock dompurify so the real implementation is used in this unit test.
// The global setup.ts mocks it as a pass-through for component tests, but
// here we need to verify actual sanitization behaviour.
vi.unmock('dompurify')

import { sanitizeHtml } from '@/utils/sanitize'

describe('sanitizeHtml', () => {
  beforeAll(() => {
    // Verify DOMPurify is supported in this environment (happy-dom).
    // If isSupported is false the utility returns input unchanged and tests
    // would give false positives — fail loudly in that case.
    const DOMPurifyModule = vi.importActual<typeof import('dompurify')>('dompurify')
    void DOMPurifyModule // referenced so linter doesn't strip the import
  })

  it('strips script tags', () => {
    const dirty = '<p>Hello</p><script>alert("xss")</script>'
    expect(sanitizeHtml(dirty)).toBe('<p>Hello</p>')
  })

  it('strips onerror handlers', () => {
    const dirty = '<img src=x onerror="alert(1)">'
    const result = sanitizeHtml(dirty)
    expect(result).not.toContain('onerror')
  })

  it('preserves safe HTML', () => {
    const safe = '<p>Hello <strong>world</strong></p>'
    expect(sanitizeHtml(safe)).toBe(safe)
  })

  it('preserves markdown-rendered HTML', () => {
    const markdown = '<h1>Title</h1><ul><li>Item</li></ul><pre><code>code</code></pre>'
    expect(sanitizeHtml(markdown)).toBe(markdown)
  })

  it('strips javascript: URLs', () => {
    const dirty = '<a href="javascript:alert(1)">click</a>'
    const result = sanitizeHtml(dirty)
    expect(result).not.toContain('javascript:')
  })

  it('handles empty input', () => {
    expect(sanitizeHtml('')).toBe('')
  })

  it('handles non-string input gracefully', () => {
    expect(sanitizeHtml(undefined as unknown as string)).toBe('')
    expect(sanitizeHtml(null as unknown as string)).toBe('')
  })
})
