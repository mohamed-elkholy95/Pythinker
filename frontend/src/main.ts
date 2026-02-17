import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import VueKonva from 'vue-konva'
import App from './App.vue'
import './assets/global.css'
import './assets/theme.css'
import './utils/toast'
import i18n from './composables/useI18n'
import { getStoredToken, getCachedAuthProvider } from './api/auth'
import autoFollowScrollPlugin from './plugins/autoFollowScroll'
import apiResiliencePlugin from './plugins/apiResilience'

// Configure Monaco Editor Web Workers
// This prevents UI freezes by offloading syntax highlighting to web workers
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === 'json') {
      return new jsonWorker()
    }
    return new editorWorker()
  }
}

// Import page components
import HomePage from './pages/HomePage.vue'
import ChatPage from './pages/ChatPage.vue'
import LoginPage from './pages/LoginPage.vue'
import MainLayout from './pages/MainLayout.vue'
import { configure } from "vue-gtag";
import SharePage from './pages/SharePage.vue';
import ShareLayout from './pages/ShareLayout.vue';
import SessionHistoryPage from './pages/SessionHistoryPage.vue';
import CanvasPage from './pages/CanvasPage.vue'

const canReadStorage = typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function'
const storedTheme = canReadStorage ? localStorage.getItem('bolt_theme') : null
const prefersDark = typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
const resolvedTheme = storedTheme ?? (prefersDark ? 'dark' : 'light')
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-theme', resolvedTheme)
  document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
}

configure({
  tagId: 'G-XCRZ3HH31S' // Replace with your own Google Analytics tag ID
})

// Create router
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { 
      path: '/chat', 
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          component: HomePage,
          alias: ['/', '/home'],
          meta: { requiresAuth: true }
        },
        {
          path: 'history',
          component: SessionHistoryPage,
          meta: { requiresAuth: true }
        },
        {
          path: 'canvas/:projectId?',
          component: CanvasPage,
          meta: { requiresAuth: true }
        },
        {
          path: ':sessionId',
          component: ChatPage,
          meta: { requiresAuth: true }
        }
      ]
    },
    {
      path: '/share',
      component: ShareLayout,
      children: [
        {
          path: ':sessionId',
          component: SharePage,
        }
      ]
    },
    { 
      path: '/login', 
      component: LoginPage
    }
  ]
})

// Global route guard
router.beforeEach(async (to, _, next) => {
  const requiresAuth = to.matched.some((record) => record.meta?.requiresAuth)
  const hasToken = !!getStoredToken()
  
  if (requiresAuth) {
    const authProvider = await getCachedAuthProvider()
    
    if (authProvider === 'none') {
      next()
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
