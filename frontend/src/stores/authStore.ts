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
  verifyEmail as apiVerifyEmail,
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
  type VerifyEmailRequest,
} from '../api/auth'
import { tokenExpiresIn } from '../utils/jwt'

/** Default token lifetime in seconds (20 minutes) used when server doesn't provide expires_in */
const DEFAULT_TOKEN_LIFETIME_SECONDS = 1200

/** Minimum refresh interval to avoid tight loops (10 seconds) */
const MIN_REFRESH_INTERVAL_SECONDS = 10

/** Refresh 60 seconds before expiry when possible */
const REFRESH_LEEWAY_SECONDS = 60

let _refreshTimer: ReturnType<typeof setTimeout> | null = null

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
          email_verified: true,
          totp_enabled: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }
        isAuthenticated.value = true
        return
      }

      const token = getStoredToken()
      if (token) {
        setAuthToken(token)
        const expiresIn = tokenExpiresIn(token)
        if (expiresIn <= 0) {
          // Token already expired — attempt immediate refresh
          await refreshAuthToken()
        } else {
          scheduleProactiveRefresh(expiresIn)
          await loadCurrentUser()
        }
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

      // TOTP 2FA challenge — don't store tokens yet
      if (response.requires_totp) {
        return response
      }

      if (response.access_token) {
        storeToken(response.access_token)
        setAuthToken(response.access_token)
      }
      if (response.refresh_token) {
        storeRefreshToken(response.refresh_token)
      }
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS)
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
      // Do NOT store tokens — user must verify email first
      return response
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : 'Registration failed'
      authError.value = errMsg
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function verifyEmail(data: VerifyEmailRequest) {
    try {
      isLoading.value = true
      authError.value = null
      const response = await apiVerifyEmail(data)

      if (response.access_token) {
        storeToken(response.access_token)
        setAuthToken(response.access_token)
      }
      if (response.refresh_token) {
        storeRefreshToken(response.refresh_token)
      }
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS)
      await loadCurrentUser()
      return response
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : 'Email verification failed'
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
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS)
      return true
    } catch {
      clearAuth()
      return false
    }
  }

  function clearAuth() {
    cancelProactiveRefresh()
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

  /**
   * Schedule a proactive token refresh 60 seconds before expiry.
   * Prevents SSE reconnection failures by refreshing before expiry.
   */
  function scheduleProactiveRefresh(expiresInSeconds: number) {
    cancelProactiveRefresh()
    const refreshAfter = Math.max(
      MIN_REFRESH_INTERVAL_SECONDS,
      Math.floor(expiresInSeconds - REFRESH_LEEWAY_SECONDS),
    )
    _refreshTimer = setTimeout(() => {
      _refreshTimer = null
      refreshAuthToken()
    }, refreshAfter * 1000)
  }

  function cancelProactiveRefresh() {
    if (_refreshTimer !== null) {
      clearTimeout(_refreshTimer)
      _refreshTimer = null
    }
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
    verifyEmail,
    logout,
    refreshAuthToken,
    clearAuth,
    clearError,
    hasRole,
    registerLogoutListener,
    hasAttemptedInit,
  }
})
