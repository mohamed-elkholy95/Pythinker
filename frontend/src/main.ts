import { createApp } from 'vue'
import VueKonva from 'vue-konva'
import App from './App.vue'
import './assets/global.css'
import './assets/theme.css'
import './utils/toast'
import i18n from './composables/useI18n'
import { router } from './router'
import { getStoredToken, getCachedAuthProvider } from './api/auth'
import autoFollowScrollPlugin from './plugins/autoFollowScroll'
import apiResiliencePlugin from './plugins/apiResilience'
import { configure } from "vue-gtag";

// FOUC prevention — runs synchronously before Vue mounts.
// useThemeMode() in App.vue takes over reactive management after mount.
const canReadStorage = typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'
const storedTheme = canReadStorage ? localStorage.getItem('bolt_theme') : null
const prefersDark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
// Guard: only accept explicit 'dark'/'light' — ignore 'auto' or null (fall back to OS)
const resolvedTheme = (storedTheme === 'dark' || storedTheme === 'light')
  ? storedTheme
  : (prefersDark ? 'dark' : 'light')
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-theme', resolvedTheme)
  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
}

// Only enable Google Analytics when a tag ID is configured
const gaTagId = import.meta.env.VITE_GA_TAG_ID
if (gaTagId) {
  configure({ tagId: gaTagId })
}

// Global route guard
router.beforeEach(async (to, _, next) => {
  const requiresAuth = to.matched.some((record) => record.meta?.requiresAuth)
  const hasToken = !!getStoredToken()

  if (requiresAuth) {
    const authProvider = await getCachedAuthProvider()

    // Bug #10 fix: when backend is unavailable (null), fail open for token holders
    // and redirect to login for users without tokens
    if (authProvider === 'none') {
      next()
      return
    }

    if (authProvider === null) {
      // Backend unavailable — allow token holders through (they'll get 401 later
      // if the token is actually invalid), redirect others to login
      if (hasToken) {
        next()
      } else {
        next({ path: '/login', query: { redirect: to.fullPath } })
      }
      return
    }

    if (!hasToken) {
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      })
      return
    }
  }

  if (to.path === '/login' && hasToken) {
    next('/')
  } else {
    next()
  }
})

const app = createApp(App)

app.use(router)
app.use(i18n)
app.use(VueKonva)
app.use(apiResiliencePlugin, { maxRetries: 3 })
app.use(autoFollowScrollPlugin)
app.mount('#app')
