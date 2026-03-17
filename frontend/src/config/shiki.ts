/**
 * Shiki syntax highlighter configuration
 *
 * Defines themes and bundled languages for code highlighting
 */
import type { BundledLanguage, BundledTheme } from 'shiki'

/**
 * Theme configuration for light and dark modes
 */
export const SHIKI_THEMES = {
  light: 'github-light' as BundledTheme,
  dark: 'github-dark' as BundledTheme,
} as const

/**
 * Languages to bundle with the highlighter
 * These are the most commonly used languages in the application
 */
export const SHIKI_LANGUAGES: BundledLanguage[] = [
  'javascript',
  'typescript',
  'python',
  'bash',
  'shell',
  'json',
  'html',
  'css',
  'markdown',
  'yaml',
  'go',
  'java',
  'sql',
  'rust',
  'c',
  'cpp',
  'dockerfile',
  'xml',
  'toml',
  'ini',
  'diff',
  'log',
]

/**
 * File extension to language mapping
 */
export const EXTENSION_TO_LANGUAGE: Record<string, BundledLanguage> = {
  '.js': 'javascript',
  '.mjs': 'javascript',
  '.cjs': 'javascript',
  '.jsx': 'javascript',
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.mts': 'typescript',
  '.cts': 'typescript',
  '.py': 'python',
  '.pyi': 'python',
  '.pyw': 'python',
  '.sh': 'bash',
  '.bash': 'bash',
  '.zsh': 'bash',
  '.fish': 'bash',
  '.json': 'json',
  '.jsonc': 'json',
  '.json5': 'json',
  '.html': 'html',
  '.htm': 'html',
  '.vue': 'html',
  '.svelte': 'html',
  '.css': 'css',
  '.scss': 'css',
  '.sass': 'css',
  '.less': 'css',
  '.md': 'markdown',
  '.mdx': 'markdown',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.go': 'go',
  '.java': 'java',
  '.sql': 'sql',
  '.rs': 'rust',
  '.c': 'c',
  '.h': 'c',
  '.cpp': 'cpp',
  '.cc': 'cpp',
  '.cxx': 'cpp',
  '.hpp': 'cpp',
  '.hxx': 'cpp',
  '.dockerfile': 'dockerfile',
  '.xml': 'xml',
  '.svg': 'xml',
  '.toml': 'toml',
  '.ini': 'ini',
  '.cfg': 'ini',
  '.conf': 'ini',
  '.diff': 'diff',
  '.patch': 'diff',
  '.log': 'log',
}

/**
 * Language aliases for auto-detection
 */
export const LANGUAGE_ALIASES: Record<string, BundledLanguage> = {
  js: 'javascript',
  ts: 'typescript',
  py: 'python',
  sh: 'bash',
  shell: 'shell',
  zsh: 'bash',
  yml: 'yaml',
  dockerfile: 'dockerfile',
  docker: 'dockerfile',
  make: 'makefile' as BundledLanguage,
  makefile: 'makefile' as BundledLanguage,
  plaintext: 'text' as BundledLanguage,
  plain: 'text' as BundledLanguage,
  text: 'text' as BundledLanguage,
  txt: 'text' as BundledLanguage,
}

/**
 * Maximum cache size for highlighted code blocks
 */
export const SHIKI_CACHE_MAX_SIZE = 200

/**
 * Get language from filename
 */
export function getLanguageFromFilename(filename: string): BundledLanguage | null {
  if (!filename) return null

  // Check for exact filename matches (e.g., Dockerfile, Makefile)
  const basename = filename.split('/').pop()?.toLowerCase() || ''

  if (basename === 'dockerfile') return 'dockerfile'
  if (basename === 'makefile') return 'makefile' as BundledLanguage

  // Check file extension
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex === -1) return null

  const extension = filename.slice(lastDotIndex).toLowerCase()
  return EXTENSION_TO_LANGUAGE[extension] || null
}

/**
 * Normalize language identifier
 */
export function normalizeLanguage(lang: string): BundledLanguage {
  if (!lang) return 'text' as BundledLanguage

  const normalized = lang.toLowerCase().trim()

  // Check aliases first
  if (normalized in LANGUAGE_ALIASES) {
    return LANGUAGE_ALIASES[normalized]
  }

  // Check if it's a valid bundled language
  if (SHIKI_LANGUAGES.includes(normalized as BundledLanguage)) {
    return normalized as BundledLanguage
  }

  // Default to text
  return 'text' as BundledLanguage
}
