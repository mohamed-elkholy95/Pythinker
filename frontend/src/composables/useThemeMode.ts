import { useDark, useToggle } from '@vueuse/core'
import type { WritableComputedRef } from 'vue'

/**
 * Central theme controller — single source of truth for dark/light mode.
 *
 * Wraps VueUse useDark() to provide:
 *  - Reactive isDark ref persisted to localStorage under 'bolt_theme'
 *  - OS preference listener via matchMedia (auto-applied when no manual override)
 *  - data-theme attribute sync for CSS custom property selectors in theme.css
 *
 * Call once in App.vue setup(). All other components read theme reactively via:
 *  - useThemeColors() from @/utils/themeColors (MutationObserver on <html class>)
 *  - CSS custom properties (var(--text-primary) etc.) — adapt automatically
 */
export function useThemeMode() {
  const isDark = useDark({
    selector: 'html',
    attribute: 'class',
    valueDark: 'dark',
    valueLight: '',
    storageKey: 'bolt_theme',
    onChanged(dark, defaultHandler, mode) {
      // Toggle .dark class on <html> (Tailwind dark: variant)
      defaultHandler(mode)
      // Sync data-theme for :root[data-theme='dark'] selectors in theme.css
      document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    },
  })

  const toggle = useToggle(isDark)

  function setTheme(mode: 'dark' | 'light'): void {
    isDark.value = mode === 'dark'
  }

  return {
    isDark: isDark as WritableComputedRef<boolean>,
    toggleTheme: toggle,
    setTheme,
  }
}
