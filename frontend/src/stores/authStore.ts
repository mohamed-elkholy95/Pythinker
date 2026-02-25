/**
 * Auth store — manages authentication state globally via Pinia.
 *
 * Replaces the module-level singleton refs in useAuth.ts composable.
 * The useAuth() composable becomes a thin facade over this store.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  getCurrentUser,
  refreshToken as apiRefreshToken,
  setAuthToken,
  clearAuthToken,
  storeToken,
  storeRefreshToken,
  getStoredToken,
  getStoredRefreshToken,
  clearStoredTokens,
  getCachedAuthProvider,
  type User,
  type LoginRequest,
  type RegisterRequest,
} from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  // ── State ────────────────────────────────────────────────────────
  const currentUser = ref<User | null>(null)
  const isAuthenticated = ref(false)
  const isLoading = ref(false)
  const authError = ref<string | null>(null)

  // Internal guards (not exposed as reactive state)
  let _isInitializing = false
  let _hasAttemptedInit = false
  let _logoutListenerRegistered = false

  // ── Computed ─────────────────────────────────────────────────────
  const isAdmin = computed(() => currentUser.value?.role === 'admin')
  const isActive = computed(() => currentUser.value?.is_active ?? false)

  // ── Actions ──────────────────────────────────────────────────────

  async function initAuth() {
    if (_isInitializing) return
    _isInitializing = true

    try {
      const authProvider = await getCachedAuthProvider()

      if (authProvider === 'none') {
        currentUser.value = {
          id: 'anonymous',
          fullname: 'Anonymous User',
          email: 'anonymous@localhost',
          role: 'user',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        isAuthenticated.value = true
        return
      }

      const token = getStoredToken()
      if (token) {
        setAuthToken(token)
        await loadCurrentUser()
      }
    } finally {
      _isInitializing = false
      _hasAttemptedInit = true
    }
  }

  async function loadCurrentUser() {
    try {
      isLoading.value = true
      authError.value = null
      const user = await getCurrentUser()
      currentUser.value = user
      isAuthenticated.value = true
    } catch (error: unknown) {
      currentUser.value = null
      isAuthenticated.value = false
      const errMsg = error instanceof Error ? error.message : 'Failed to load user'
      authError.value = errMsg
    } finally {
      isLoading.value = false
    }
  }

  async function login(credentials: LoginRequest) {
    try {
      isLoading.value = true
      authError.value = null
      const response = await apiLogin(credentials)
      storeToken(response.access_token)
      setAuthToken(response.access_token)
      if (response.refresh_token) {
        storeRefreshToken(response.refresh_token)
      }
      await loadCurrentUser()
      return response
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : 'Login failed'
      authError.value = errMsg
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function register(data: RegisterRequest) {
    try {
      isLoading.value = true
      authError.value = null
      const response = await apiRegister(data)
      return response
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : 'Registration failed'
      authError.value = errMsg
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function logout(silent = false) {
    try {
      if (!silent) {
        isLoading.value = true
      }
      await apiLogout()
    } catch {
      // Ignore logout errors — always clear local state
    } finally {
      clearAuth()
      if (!silent) {
        isLoading.value = false
      }
    }
  }

  async function refreshAuthToken() {
    const refreshTokenValue = getStoredRefreshToken()
    if (!refreshTokenValue) return false

    try {
      const response = await apiRefreshToken({ refresh_token: refreshTokenValue })
      storeToken(response.access_token)
      setAuthToken(response.access_token)
      return true
    } catch {
      clearAuth()
      return false
    }
  }

  function clearAuth() {
    currentUser.value = null
    isAuthenticated.value = false
    authError.value = null
    clearAuthToken()
    clearStoredTokens()
  }

  function clearError() {
    authError.value = null
  }

  function hasRole(role: string): boolean {
    return currentUser.value?.role === role
  }

  function registerLogoutListener() {
    if (_logoutListenerRegistered) return
    _logoutListenerRegistered = true
    window.addEventListener('auth:logout', () => {
      logout(true)
    })
  }

  // ── Getters (read-only access helpers) ───────────────────────────
  function hasAttemptedInit(): boolean {
    return _hasAttemptedInit
  }

  return {
    // State
    currentUser,
    isAuthenticated,
    isLoading,
    authError,
    // Computed
    isAdmin,
    isActive,
    // Actions
    initAuth,
    loadCurrentUser,
    login,
    register,
    logout,
    refreshAuthToken,
    clearAuth,
    clearError,
    hasRole,
    registerLogoutListener,
    hasAttemptedInit,
  }
})
