import { describe, expect, it } from 'vitest';

import { normalizeUserMessageForDedup } from '../userMessageDedup';

describe('normalizeUserMessageForDedup', () => {
  it('trims and normalizes CRLF', () => {
    expect(normalizeUserMessageForDedup('  hello\r\nworld  ')).toBe('hello\nworld');
  });

  it('collapses horizontal whitespace within a line', () => {
    expect(normalizeUserMessageForDedup('a  \t b')).toBe('a b');
  });

  it('treats formatting variants as equal after normalization', () => {
    const a = 'line one\nline two';
    const b = 'line one\r\nline two\n';
    expect(normalizeUserMessageForDedup(a)).toBe(normalizeUserMessageForDedup(b));
  });
});
