/**
 * useAuth composable — thin facade over the Pinia auth store.
 *
 * All proactive refresh logic, token management, and auth state live in
 * authStore.ts. This composable delegates entirely to the store, ensuring
 * a single source of truth (no duplicated timers or token parsing).
 *
 * Legacy code that imports `useAuth()` continues to work unchanged.
 */
import { computed } from 'vue'
import {
  migrateStaleTokens,
  type LoginRequest,
  type RegisterRequest,
  type LoginResponse,
  type RegisterResponse
} from '../api/auth'
import { useAuthStore } from '../stores/authStore'

export function useAuth() {
  const store = useAuthStore()

  // Register the singleton logout listener once
  store.registerLogoutListener()

  // Migrate stale localStorage keys from older auth implementations
  migrateStaleTokens()

  // Auto-initialize auth state when composable is first used (once per app lifecycle)
  if (!store.hasAttemptedInit() && !store.isAuthenticated && !store.isLoading) {
    store.initAuth()
  }

  return {
    // State (read-only computed refs for reactivity)
    currentUser: computed(() => store.currentUser),
    isAuthenticated: computed(() => store.isAuthenticated),
    isLoading: computed(() => store.isLoading),
    authError: computed(() => store.authError),
    isAdmin: store.isAdmin,
    isActive: store.isActive,

    // Actions — delegate directly to store
    login: store.login as (credentials: LoginRequest) => Promise<LoginResponse>,
    register: store.register as (data: RegisterRequest) => Promise<RegisterResponse>,
    logout: store.logout,
    initAuth: store.initAuth,
    loadCurrentUser: store.loadCurrentUser,
    refreshAuthToken: store.refreshAuthToken,
    hasRole: store.hasRole,
    clearError: store.clearError,
    clearAuth: store.clearAuth,
  }
}
