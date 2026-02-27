import { createRouter, createWebHistory } from 'vue-router'

// Route-level lazy loading keeps the bootstrap bundle small.
const MainLayout = () => import('../pages/MainLayout.vue')
const HomePage = () => import('../pages/HomePage.vue')
const ChatPage = () => import('../pages/ChatPage.vue')
const LoginPage = () => import('../pages/LoginPage.vue')
const ShareLayout = () => import('../pages/ShareLayout.vue')
const SharePage = () => import('../pages/SharePage.vue')
const SessionHistoryPage = () => import('../pages/SessionHistoryPage.vue')
const CanvasPage = () => import('../pages/CanvasPage.vue')
const NotFoundPage = () => import('../pages/NotFoundPage.vue')

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
          meta: { requiresAuth: true },
        },
        {
          path: 'history',
          component: SessionHistoryPage,
          meta: { requiresAuth: true },
        },
        {
          path: 'canvas/:projectId?',
          component: CanvasPage,
          meta: { requiresAuth: true },
        },
        {
          path: ':sessionId',
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
