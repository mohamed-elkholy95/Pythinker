import { usePreferredDark, useStorage } from '@vueuse/core'
import { computed, watch } from 'vue'
import type { ComputedRef } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'pythinker-theme-mode'

/**
 * Central theme controller — single source of truth for dark/light mode.
 *
 * Supports three modes:
 *  - 'light'  — always light
 *  - 'dark'   — always dark
 *  - 'system' — follows OS preference via matchMedia (default)
 *
 * Persisted to localStorage under 'pythinker-theme-mode'.
 * Syncs .dark class (Tailwind) + data-theme attribute (theme.css).
 *
 * Call once in App.vue setup(). All other components read theme reactively via:
 *  - useThemeColors() from @/utils/themeColors (MutationObserver on <html class>)
 *  - CSS custom properties (var(--text-primary) etc.) — adapt automatically
 */
export function useThemeMode() {
  const themeMode = useStorage<ThemeMode>(STORAGE_KEY, 'system')
  const osPrefersDark = usePreferredDark()

  const isDark: ComputedRef<boolean> = computed(() => {
    if (themeMode.value === 'system') return osPrefersDark.value
    return themeMode.value === 'dark'
  })

  // Sync DOM classes and attributes reactively
  watch(isDark, (dark) => {
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  }, { immediate: true })

  function setThemeMode(mode: ThemeMode): void {
    themeMode.value = mode
  }

  /** Legacy-compatible: set 'dark' or 'light' directly */
  function setTheme(mode: 'dark' | 'light'): void {
    themeMode.value = mode
  }

  function toggleTheme(): void {
    themeMode.value = isDark.value ? 'light' : 'dark'
  }

  return {
    isDark,
    themeMode,
    toggleTheme,
    setTheme,
    setThemeMode,
  }
}
