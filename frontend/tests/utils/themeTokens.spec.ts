import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import {
  getCurrentThemeMode,
  getThemeColors,
  THEME_COLORS,
} from '@/utils/themeColors'

// ---------------------------------------------------------------------------
// Static: CSS token existence
// ---------------------------------------------------------------------------

describe('theme CSS tokens', () => {
  it('light mode: defines shared spacing, radius, and typography tokens', () => {
    const css = readFileSync('src/assets/theme.css', 'utf-8')
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
    ]

    for (const token of requiredTokens) {
      expect(css, `Missing token: ${token}`).toContain(token)
    }
  })

  it('dark mode: defines all required semantic color tokens', () => {
    const css = readFileSync('src/assets/theme.css', 'utf-8')
    // Isolate the dark section to avoid false-positives from the light section
    const darkSectionStart = css.indexOf(":root[data-theme='dark']")
    expect(darkSectionStart, 'Dark mode section not found in theme.css').toBeGreaterThan(-1)
    const darkSection = css.slice(darkSectionStart)

    const darkTokens = [
      '--bolt-elements-textPrimary:',
      '--bolt-elements-textSecondary:',
      '--background-main:',
      '--border-main:',
      '--code-block-bg:',
      '--terminal-bg:',
      '--function-success:',
      '--function-error:',
      '--function-warning:',
      '--function-success-border:',
      '--function-success-tsp:',
    ]
    for (const token of darkTokens) {
      expect(darkSection, `Missing dark-mode token: ${token}`).toContain(token)
    }
  })

  it('global.css declares color-scheme for both light and dark modes', () => {
    const css = readFileSync('src/assets/global.css', 'utf-8')
    expect(css).toContain('color-scheme: light')
    expect(css).toContain('color-scheme: dark')
  })

  it('global.css includes forced-colors and prefers-contrast media queries', () => {
    const css = readFileSync('src/assets/global.css', 'utf-8')
    expect(css).toContain('forced-colors: active')
    expect(css).toContain('prefers-contrast: more')
  })
})

// ---------------------------------------------------------------------------
// Runtime: theme color utilities
// ---------------------------------------------------------------------------

describe('getCurrentThemeMode()', () => {
  beforeEach(() => {
    document.documentElement.className = ''
    document.documentElement.removeAttribute('data-theme')
  })

  it('returns "light" when no dark class is present', () => {
    expect(getCurrentThemeMode()).toBe('light')
  })

  it('returns "dark" when the .dark class is present', () => {
    document.documentElement.classList.add('dark')
    expect(getCurrentThemeMode()).toBe('dark')
  })
})

describe('getThemeColors()', () => {
  afterEach(() => {
    document.documentElement.classList.remove('dark')
  })

  it('returns the light palette when mode is "light"', () => {
    const colors = getThemeColors('light')
    expect(colors).toStrictEqual(THEME_COLORS.light)
    expect(colors.background).toBe('#ffffff')
    expect(colors.text.primary).toBe('#1f2937')
  })

  it('returns the dark palette when mode is "dark"', () => {
    const colors = getThemeColors('dark')
    expect(colors).toStrictEqual(THEME_COLORS.dark)
    expect(colors.background).toBe('#141414')
    expect(colors.text.primary).toBe('#e8e0d8')
  })

  it('auto-detects theme from document when no mode argument is given', () => {
    document.documentElement.classList.add('dark')
    expect(getThemeColors()).toStrictEqual(THEME_COLORS.dark)
    document.documentElement.classList.remove('dark')
    expect(getThemeColors()).toStrictEqual(THEME_COLORS.light)
  })

  it('light and dark palettes have the same shape (no missing keys)', () => {
    const lightKeys = Object.keys(THEME_COLORS.light).sort()
    const darkKeys = Object.keys(THEME_COLORS.dark).sort()
    expect(lightKeys).toEqual(darkKeys)
  })

  it('dark success/error colors differ from light (both palettes are independently defined)', () => {
    // Ensures dark palette is not accidentally a copy of the light one
    expect(THEME_COLORS.dark.success).not.toBe(THEME_COLORS.light.success)
    expect(THEME_COLORS.dark.background).not.toBe(THEME_COLORS.light.background)
  })
})
