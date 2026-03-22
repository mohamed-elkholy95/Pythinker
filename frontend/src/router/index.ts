import { createRouter, createWebHistory } from 'vue-router'
import { getStoredToken, getCachedAuthProvider } from '../api/auth'

// Route-level lazy loading keeps the bootstrap bundle small.
const LandingPage = () => import('../pages/LandingPage.vue')
const MainLayout = () => import('../pages/MainLayout.vue')
const HomePage = () => import('../pages/HomePage.vue')
const ChatPage = () => import('../pages/ChatPage.vue')
const AgentsPage = () => import('../pages/AgentsPage.vue')
const LoginPage = () => import('../pages/LoginPage.vue')
const ShareLayout = () => import('../pages/ShareLayout.vue')
const SharePage = () => import('../pages/SharePage.vue')
const SessionHistoryPage = () => import('../pages/SessionHistoryPage.vue')
const CanvasPage = () => import('../pages/CanvasPage.vue')
const ProjectPage = () => import('../pages/ProjectPage.vue')
const ProjectsPage = () => import('../pages/ProjectsPage.vue')
const NotFoundPage = () => import('../pages/NotFoundPage.vue')
const PrivacyPage = () => import('../pages/PrivacyPage.vue')
const TermsPage = () => import('../pages/TermsPage.vue')

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingPage,
      meta: { requiresAuth: false },
    },
    {
      path: '/privacy',
      name: 'privacy',
      component: PrivacyPage,
      meta: { requiresAuth: false },
    },
    {
      path: '/terms',
      name: 'terms',
      component: TermsPage,
      meta: { requiresAuth: false },
    },
    {
      path: '/chat',
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          component: HomePage,
          alias: ['/home'],
          meta: { requiresAuth: true },
        },
        {
          path: 'history',
          name: 'session-history',
          component: SessionHistoryPage,
          meta: { requiresAuth: true },
        },
        {
          path: 'agents',
          name: 'agents-home',
          component: AgentsPage,
          meta: { requiresAuth: true, workspace: 'agents', source: 'telegram' },
        },
        {
          path: 'agents/:sessionId',
          name: 'agents-session',
          component: ChatPage,
          meta: { requiresAuth: true, workspace: 'agents', source: 'telegram' },
        },
        {
          path: 'canvas/:projectId?',
          name: 'canvas',
          component: CanvasPage,
          meta: { requiresAuth: true },
        },
        {
          path: 'projects',
          name: 'projects',
          component: ProjectsPage,
          meta: { requiresAuth: true },
        },
        {
          path: 'projects/:projectId',
          name: 'project-detail',
          component: ProjectPage,
          meta: { requiresAuth: true },
        },
        {
          path: ':sessionId',
          name: 'chat-session',
          component: ChatPage,
          meta: { requiresAuth: true },
        },
      ],
    },
    {
      path: '/share',
      component: ShareLayout,
      children: [
        {
          path: ':sessionId',
          component: SharePage,
        },
      ],
    },
    {
      path: '/login',
      component: LoginPage,
    },
    // Legacy route redirects
    {
      path: '/sessions',
      redirect: '/chat/history',
    },
    {
      path: '/history',
      redirect: '/chat/history',
    },
    // Catch-all 404 — must be last
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundPage,
    },
  ],
})

// ── Auth guard ────────────────────────────────────────────────────
// Redirects unauthenticated users to /login for routes with
// meta.requiresAuth. Skips the check when auth provider is 'none'
// (open-access deployment).
router.beforeEach(async (to) => {
  const requiresAuth = to.matched.some((record) => record.meta.requiresAuth)
  if (!requiresAuth) return

  // When the backend is configured with no auth, allow all routes
  const authProvider = await getCachedAuthProvider()
  if (authProvider === 'none') return

  const token = getStoredToken()
  if (!token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})
