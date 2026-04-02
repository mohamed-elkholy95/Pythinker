import { describe, expect, it } from 'vitest';

import { detectContentType } from '../streaming';

describe('detectContentType', () => {
  it('classifies terminal tools as terminal content', () => {
    expect(detectContentType('terminal')).toBe('terminal');
  });

  it('keeps shell and code execution tools on the terminal path', () => {
    expect(detectContentType('shell_exec')).toBe('terminal');
    expect(detectContentType('code_execute')).toBe('terminal');
  });
});
