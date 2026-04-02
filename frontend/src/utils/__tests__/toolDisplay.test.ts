import { describe, expect, it } from 'vitest';

import { getToolDisplay } from '../toolDisplay';

describe('toolDisplay', () => {
  it('maps terminal functions onto the shell tool key', () => {
    const display = getToolDisplay({ name: 'terminal', function: 'terminal' });

    expect(display.toolKey).toBe('shell');
    expect(display.displayName).toBe('Terminal');
  });
});
