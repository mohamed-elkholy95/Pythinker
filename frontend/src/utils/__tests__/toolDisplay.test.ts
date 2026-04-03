import { describe, expect, it } from 'vitest'

import { getToolDisplay, getToolLiveLabel } from '../toolDisplay'

describe('toolDisplay', () => {
  it('maps terminal functions onto the shell tool key', () => {
    const display = getToolDisplay({ name: 'terminal', function: 'terminal' })

    expect(display.toolKey).toBe('shell')
    expect(display.displayName).toBe('Terminal')
  })

  it('uses Browsing for browser-family tools even when no function-specific label is available', () => {
    const display = getToolDisplay({
      name: 'browser_session',
      function: 'unknown_action',
    })

    expect(display.displayName).toBe('Browser Session')
    expect(display.actionLabel).toBe('Browsing')
    expect(display.description).toBe('Browsing')
  })

  it('prefers the live step text over the generic working fallback', () => {
    expect(
      getToolLiveLabel({
        current_step: 'Analyze findings and compile structured beginner guide report with citations',
      }),
    ).toBe('Analyze findings and compile structured beginner guide report with citations')
  })

  it('falls back to display_command when the live step is missing', () => {
    expect(
      getToolLiveLabel({
        display_command: 'Searching best prompt engineering courses guides for beginners 2026',
      }),
    ).toBe('Searching best prompt engineering courses guides for beginners 2026')
  })
})
