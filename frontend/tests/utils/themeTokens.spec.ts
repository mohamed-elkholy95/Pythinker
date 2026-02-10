import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

describe('theme tokens', () => {
  it('defines shared spacing, radius, and typography tokens used by tool views', () => {
    const css = readFileSync('src/assets/theme.css', 'utf-8');
    const requiredTokens = [
      '--space-1:',
      '--space-2:',
      '--space-3:',
      '--space-4:',
      '--space-6:',
      '--space-8:',
      '--space-12:',
      '--radius-sm:',
      '--radius-md:',
      '--radius-lg:',
      '--text-xs:',
      '--text-sm:',
      '--text-base:',
      '--font-normal:',
      '--font-medium:',
      '--font-semibold:',
    ];

    for (const token of requiredTokens) {
      expect(css.includes(token)).toBe(true);
    }
  });
});
