import { describe, expect, it } from 'vitest'

import { getToolDisplay } from '../toolDisplay'

describe('toolDisplay', () => {
  it('uses Browsing for browser-family tools even when no function-specific label is available', () => {
    const display = getToolDisplay({
      name: 'browser_session',
      function: 'unknown_action',
    })

    expect(display.displayName).toBe('Browser Session')
    expect(display.actionLabel).toBe('Browsing')
    expect(display.description).toBe('Browsing')
  })
})
