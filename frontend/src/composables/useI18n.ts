import { createI18n } from 'vue-i18n'
import { ref, watch } from 'vue'
import messages from '../locales'
import type { Locale } from '../locales'

const STORAGE_KEY = 'pythinker-locale'

const canReadStorage = (): boolean =>
  typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'

const canWriteStorage = (): boolean =>
  typeof localStorage !== 'undefined' && typeof localStorage.setItem === 'function'

// Get browser language and map to supported locale
const getBrowserLocale = (): Locale => {
  // Currently only English is supported
  // When adding new locales, update the Locale type in @/locales/index.ts
  // and add corresponding translations
  return 'en'
}

// Get current language from localStorage, default to browser language
const getStoredLocale = (): Locale => {
  if (!canReadStorage()) {
    return getBrowserLocale()
  }

  const storedLocale = localStorage.getItem(STORAGE_KEY)
  return (storedLocale as Locale) || getBrowserLocale()
}

// Create i18n instance
export const i18n = createI18n({
  legacy: false, // Use Composition API mode
  locale: getStoredLocale(),
  fallbackLocale: 'en',
  messages,
  silentTranslationWarn: true,    // Disable translation warnings
  silentFallbackWarn: true,       // Disable fallback warnings
  missingWarn: false,             // Disable missing key warnings
  fallbackWarn: false,            // Disable fallback warnings
  warnHtmlMessage: false          // Disable HTML in message warnings
})

// Create a composable to use in components
export function useLocale() {
  const currentLocale = ref(getStoredLocale())

  // Switch language
  const setLocale = (locale: Locale) => {
    i18n.global.locale.value = locale
    currentLocale.value = locale
    if (canWriteStorage()) {
      localStorage.setItem(STORAGE_KEY, locale)
    }
    document.querySelector('html')?.setAttribute('lang', locale)
  }

  // Watch language change
  watch(currentLocale, (val) => {
    setLocale(val)
  })

  return {
    currentLocale,
    setLocale
  }
}

export default i18n 
