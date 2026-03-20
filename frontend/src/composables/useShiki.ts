/**
 * Composable for Shiki syntax highlighting
 *
 * Provides lazy-loaded syntax highlighting with:
 * - Singleton highlighter pattern
 * - Theme synchronization with document
 * - LRU-style cache for performance
 * - Language auto-detection
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import type { Highlighter, BundledLanguage } from 'shiki'
import {
  SHIKI_THEMES,
  SHIKI_LANGUAGES,
  SHIKI_CACHE_MAX_SIZE,
  normalizeLanguage,
  getLanguageFromFilename,
} from '@/config/shiki'
import {
  SHIKI_TERMINAL_TOOL_THEMES,
  SHIKI_TERMINAL_TOOL_THEME_IDS,
} from '@/config/terminalToolDesign'

// Singleton highlighter instance
let highlighterInstance: Highlighter | null = null
let highlighterPromise: Promise<Highlighter> | null = null

// LRU-style cache for highlighted code
const highlightCache = new Map<string, string>()

/**
 * Get current theme from document
 */
function getCurrentTheme(): 'light' | 'dark' {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/**
 * Generate cache key for highlighted code
 */
function getCacheKey(code: string, language: string, theme: 'light' | 'dark'): string {
  // Use a hash-like approach for the cache key
  const codeHash = code.length > 100 ? `${code.slice(0, 50)}...${code.slice(-50)}:${code.length}` : code
  return `${language}:${theme}:${codeHash}`
}

/**
 * Initialize the Shiki highlighter (lazy singleton)
 */
async function initializeHighlighter(): Promise<Highlighter> {
  if (highlighterInstance) {
    return highlighterInstance
  }

  if (highlighterPromise) {
    return highlighterPromise
  }

  highlighterPromise = (async () => {
    const { createHighlighter } = await import('shiki')

    highlighterInstance = await createHighlighter({
      themes: [
        SHIKI_THEMES.light,
        SHIKI_THEMES.dark,
        ...SHIKI_TERMINAL_TOOL_THEMES,
      ],
      langs: SHIKI_LANGUAGES,
    })

    return highlighterInstance
  })()

  return highlighterPromise
}

/**
 * Highlight code using Shiki
 */
async function highlightCode(
  code: string,
  language: BundledLanguage | string,
  options: {
    theme?: 'light' | 'dark'
    lineNumbers?: boolean
    highlightLines?: number[]
  } = {}
): Promise<string> {
  const { theme = getCurrentTheme(), lineNumbers = false, highlightLines = [] } = options

  const normalizedLang = normalizeLanguage(language)
  const shikiTheme = theme === 'dark' ? SHIKI_THEMES.dark : SHIKI_THEMES.light

  // Check cache
  const cacheKey = getCacheKey(code, `${normalizedLang}:${lineNumbers}:${highlightLines.join(',')}`, theme)
  const cached = highlightCache.get(cacheKey)
  if (cached) {
    return cached
  }

  try {
    const highlighter = await initializeHighlighter()

    // Load language if not already loaded
    const loadedLangs = highlighter.getLoadedLanguages()
    const langString = normalizedLang as string
    if (!loadedLangs.includes(normalizedLang) && langString !== 'text') {
      try {
        await highlighter.loadLanguage(normalizedLang)
      } catch {
        // Fallback to text if language loading fails
        console.warn(`Failed to load language: ${normalizedLang}, falling back to text`)
      }
    }

    // Use the loaded language or fallback to text
    const langToUse = highlighter.getLoadedLanguages().includes(normalizedLang) ? normalizedLang : ('text' as BundledLanguage)

    let html = highlighter.codeToHtml(code, {
      lang: langToUse,
      theme: shikiTheme,
      transformers: [],
    })

    // Add line numbers if requested
    if (lineNumbers) {
      html = addLineNumbers(html, highlightLines)
    }

    // Cache the result (with LRU eviction)
    if (highlightCache.size >= SHIKI_CACHE_MAX_SIZE) {
      const firstKey = highlightCache.keys().next().value
      if (firstKey) {
        highlightCache.delete(firstKey)
      }
    }
    highlightCache.set(cacheKey, html)

    return html
  } catch (error) {
    console.error('Shiki highlighting error:', error)
    // Return escaped HTML as fallback
    return `<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`
  }
}

/**
 * Add line numbers to highlighted HTML
 */
function addLineNumbers(html: string, highlightLines: number[] = []): string {
  // Parse the HTML and wrap lines with line numbers
  const lines = html.split('\n')
  const highlightSet = new Set(highlightLines)

  const numberedLines = lines.map((line, index) => {
    const lineNum = index + 1
    const isHighlighted = highlightSet.has(lineNum)
    const highlightClass = isHighlighted ? ' highlighted' : ''
    return `<span class="line${highlightClass}" data-line="${lineNum}">${line}</span>`
  })

  return numberedLines.join('\n')
}

/**
 * Escape HTML entities
 */
function escapeHtml(text: string): string {
  const htmlEntities: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }
  return text.replace(/[&<>"']/g, (char) => htmlEntities[char])
}

/**
 * Clear the highlight cache
 */
function clearCache(): void {
  highlightCache.clear()
}

/**
 * Composable for reactive Shiki highlighting
 */
export function useShiki() {
  const isLoading = ref(false)
  const currentTheme = ref<'light' | 'dark'>(getCurrentTheme())
  let themeObserver: MutationObserver | null = null

  // Watch for theme changes
  onMounted(() => {
    if (typeof document === 'undefined') return

    themeObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.attributeName === 'class') {
          const newTheme = getCurrentTheme()
          if (newTheme !== currentTheme.value) {
            currentTheme.value = newTheme
            // Clear cache when theme changes
            clearCache()
          }
        }
      }
    })

    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    })
  })

  onUnmounted(() => {
    themeObserver?.disconnect()
  })

  /**
   * Highlight code with current theme
   */
  async function highlight(
    code: string,
    language: string,
    options: {
      lineNumbers?: boolean
      highlightLines?: number[]
    } = {}
  ): Promise<string> {
    isLoading.value = true
    try {
      return await highlightCode(code, language, {
        ...options,
        theme: currentTheme.value,
      })
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Highlight code with dual themes for CSS variable switching
   */
  async function highlightDualTheme(
    code: string,
    language: string,
    options: {
      lineNumbers?: boolean
      highlightLines?: number[]
    } = {}
  ): Promise<string> {
    isLoading.value = true
    try {
      const highlighter = await initializeHighlighter()
      const normalizedLang = normalizeLanguage(language)

      // Load language if not already loaded
      const loadedLangs = highlighter.getLoadedLanguages()
      const langString = normalizedLang as string
      if (!loadedLangs.includes(normalizedLang) && langString !== 'text') {
        try {
          await highlighter.loadLanguage(normalizedLang)
        } catch {
          console.warn(`Failed to load language: ${normalizedLang}`)
        }
      }

      const langToUse = highlighter.getLoadedLanguages().includes(normalizedLang) ? normalizedLang : ('text' as BundledLanguage)

      // Use dual theme output with CSS variables
      let html = highlighter.codeToHtml(code, {
        lang: langToUse,
        themes: {
          light: SHIKI_THEMES.light,
          dark: SHIKI_THEMES.dark,
        },
        defaultColor: 'light',
        cssVariablePrefix: '--shiki-',
      })

      if (options.lineNumbers) {
        html = addLineNumbers(html, options.highlightLines)
      }

      return html
    } catch (error) {
      console.error('Shiki dual-theme highlighting error:', error)
      return `<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Dual-theme highlight for terminal tool commands (reference palette, not GitHub).
   */
  async function highlightTerminalDualTheme(
    code: string,
    language: string,
    options: {
      lineNumbers?: boolean
      highlightLines?: number[]
    } = {},
  ): Promise<string> {
    isLoading.value = true
    try {
      const highlighter = await initializeHighlighter()
      const normalizedLang = normalizeLanguage(language)

      const loadedLangs = highlighter.getLoadedLanguages()
      const langString = normalizedLang as string
      if (!loadedLangs.includes(normalizedLang) && langString !== 'text') {
        try {
          await highlighter.loadLanguage(normalizedLang)
        } catch {
          console.warn(`Failed to load language: ${normalizedLang}`)
        }
      }

      const langToUse = highlighter.getLoadedLanguages().includes(normalizedLang)
        ? normalizedLang
        : ('text' as BundledLanguage)

      let html = highlighter.codeToHtml(code, {
        lang: langToUse,
        themes: {
          light: SHIKI_TERMINAL_TOOL_THEME_IDS.light,
          dark: SHIKI_TERMINAL_TOOL_THEME_IDS.dark,
        },
        defaultColor: 'light',
        cssVariablePrefix: '--shiki-',
      })

      if (options.lineNumbers) {
        html = addLineNumbers(html, options.highlightLines)
      }

      return html
    } catch (error) {
      console.error('Shiki terminal-tool highlighting error:', error)
      return `<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Get language from filename
   */
  function detectLanguage(filename: string): string {
    return getLanguageFromFilename(filename) || 'text'
  }

  return {
    highlight,
    highlightDualTheme,
    highlightTerminalDualTheme,
    detectLanguage,
    normalizeLanguage,
    isLoading,
    currentTheme: computed(() => currentTheme.value),
    clearCache,
  }
}

/**
 * Preload the highlighter (call early in app lifecycle)
 */
export async function preloadShiki(): Promise<void> {
  await initializeHighlighter()
}

/**
 * Get the shared highlighter instance
 */
export async function getHighlighter(): Promise<Highlighter> {
  return initializeHighlighter()
}

export { highlightCode, clearCache as clearShikiCache }
