/**
 * Terminal tool panel — reference-aligned palette (light / dark).
 * Used by xterm.js surfaces, ShellToolView (Shiki), and tool panel chrome.
 */
import type { ITheme } from '@xterm/xterm'
import type { ThemeRegistration } from 'shiki'

/**
 * Manus-style terminal (reference UI):
 * Light: white card chrome, warm gray viewport (#f8f8f8), charcoal body text, vibrant prompt green.
 * Dark: neutral charcoal chrome (#1e1e1e) + slightly lifted body (#252525), no navy.
 */
export const TERMINAL_TOOL_COLORS = {
  outerBgLight: '#ffffff',
  outerBgDark: '#1e1e1e',
  viewportBgLight: '#f8f8f8',
  viewportBgDark: '#252525',
  borderLight: '#e8e8e8',
  borderDark: 'rgba(255, 255, 255, 0.08)',
  promptLight: '#16a34a',
  promptDark: '#4ade80',
  textLight: '#171717',
  textDark: '#e8e8e8',
  mutedLight: '#737373',
  mutedDark: '#a3a3a3',
  accentBlueLight: '#3b82f6',
  accentBlueDark: '#3b82f6',
} as const

export const SHIKI_TERMINAL_TOOL_THEME_IDS = {
  light: 'pythinker-terminal-tool-light',
  dark: 'pythinker-terminal-tool-dark',
} as const

/** Shiki themes: flat terminal look (command/output match reference body text). */
export const SHIKI_TERMINAL_TOOL_THEMES: ThemeRegistration[] = [
  {
    name: SHIKI_TERMINAL_TOOL_THEME_IDS.light,
    type: 'light',
    colors: {
      'editor.background': TERMINAL_TOOL_COLORS.viewportBgLight,
      'editor.foreground': TERMINAL_TOOL_COLORS.textLight,
    },
    tokenColors: [
      {
        settings: {
          background: TERMINAL_TOOL_COLORS.viewportBgLight,
          foreground: TERMINAL_TOOL_COLORS.textLight,
        },
      },
      {
        scope: [
          'keyword',
          'storage',
          'string',
          'variable',
          'support',
          'entity',
          'constant',
          'punctuation',
          'meta',
          'invalid',
        ],
        settings: { foreground: TERMINAL_TOOL_COLORS.textLight },
      },
      {
        scope: ['comment', 'punctuation.definition.comment', 'string.comment'],
        settings: { foreground: TERMINAL_TOOL_COLORS.mutedLight },
      },
    ],
  },
  {
    name: SHIKI_TERMINAL_TOOL_THEME_IDS.dark,
    type: 'dark',
    colors: {
      'editor.background': TERMINAL_TOOL_COLORS.viewportBgDark,
      'editor.foreground': TERMINAL_TOOL_COLORS.textDark,
    },
    tokenColors: [
      {
        settings: {
          background: TERMINAL_TOOL_COLORS.viewportBgDark,
          foreground: TERMINAL_TOOL_COLORS.textDark,
        },
      },
      {
        scope: [
          'keyword',
          'storage',
          'string',
          'variable',
          'support',
          'entity',
          'constant',
          'punctuation',
          'meta',
          'invalid',
        ],
        settings: { foreground: TERMINAL_TOOL_COLORS.textDark },
      },
      {
        scope: ['comment', 'punctuation.definition.comment', 'string.comment'],
        settings: { foreground: TERMINAL_TOOL_COLORS.mutedDark },
      },
    ],
  },
]

const ansi = {
  light: {
    black: TERMINAL_TOOL_COLORS.textLight,
    red: '#dc2626',
    green: TERMINAL_TOOL_COLORS.promptLight,
    yellow: '#ca8a04',
    blue: TERMINAL_TOOL_COLORS.accentBlueLight,
    magenta: '#9333ea',
    cyan: '#0891b2',
    white: '#f3f4f6',
    brightBlack: TERMINAL_TOOL_COLORS.mutedLight,
    brightRed: '#ef4444',
    brightGreen: '#16a34a',
    brightYellow: '#eab308',
    brightBlue: TERMINAL_TOOL_COLORS.accentBlueLight,
    brightMagenta: '#a855f7',
    brightCyan: '#06b6d4',
    brightWhite: '#ffffff',
  },
  dark: {
    black: TERMINAL_TOOL_COLORS.viewportBgDark,
    red: '#f87171',
    green: TERMINAL_TOOL_COLORS.promptDark,
    yellow: '#facc15',
    blue: TERMINAL_TOOL_COLORS.accentBlueDark,
    magenta: '#c084fc',
    cyan: '#22d3ee',
    white: TERMINAL_TOOL_COLORS.textDark,
    brightBlack: TERMINAL_TOOL_COLORS.mutedDark,
    brightRed: '#fca5a5',
    brightGreen: TERMINAL_TOOL_COLORS.promptDark,
    brightYellow: '#fde047',
    brightBlue: TERMINAL_TOOL_COLORS.accentBlueDark,
    brightMagenta: '#d8b4fe',
    brightCyan: '#67e8f9',
    brightWhite: '#ffffff',
  },
} as const

export function createTerminalToolXtermTheme(mode: 'light' | 'dark'): ITheme {
  const a = ansi[mode]
  const bg =
    mode === 'light'
      ? TERMINAL_TOOL_COLORS.viewportBgLight
      : TERMINAL_TOOL_COLORS.viewportBgDark
  const fg =
    mode === 'light' ? TERMINAL_TOOL_COLORS.textLight : TERMINAL_TOOL_COLORS.textDark

  return {
    background: bg,
    foreground: fg,
    cursor: fg,
    cursorAccent: bg,
    selectionBackground:
      mode === 'light' ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.12)',
    selectionForeground: fg,
    scrollbarSliderBackground: 'transparent',
    scrollbarSliderHoverBackground:
      mode === 'light' ? 'rgba(0, 0, 0, 0.2)' : 'rgba(255, 255, 255, 0.22)',
    scrollbarSliderActiveBackground:
      mode === 'light' ? 'rgba(0, 0, 0, 0.28)' : 'rgba(255, 255, 255, 0.3)',
    black: a.black,
    red: a.red,
    green: a.green,
    yellow: a.yellow,
    blue: a.blue,
    magenta: a.magenta,
    cyan: a.cyan,
    white: a.white,
    brightBlack: a.brightBlack,
    brightRed: a.brightRed,
    brightGreen: a.brightGreen,
    brightYellow: a.brightYellow,
    brightBlue: a.brightBlue,
    brightMagenta: a.brightMagenta,
    brightCyan: a.brightCyan,
    brightWhite: a.brightWhite,
  }
}
