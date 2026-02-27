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
  migrateStaleTokens,
  getCachedAuthProvider,
  type User,
  type LoginRequest,
  type RegisterRequest,
  type LoginResponse,
  type RegisterResponse
} from '../api/auth'

/** Default token lifetime in seconds (2 hours) used when server doesn't provide expires_in */
const DEFAULT_TOKEN_LIFETIME_SECONDS = 7200

/** Minimum refresh interval to avoid tight loops (60 seconds) */
const MIN_REFRESH_INTERVAL_SECONDS = 60

/** Proactive refresh fires at 75% of token lifetime */
const REFRESH_LIFETIME_RATIO = 0.75

let _refreshTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Parse JWT payload to extract expiration time.
 * Returns seconds until expiry, or 0 if expired/invalid.
 */
function getTokenExpiresIn(token: string): number {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return 0
    const payload = parts[1]!.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = JSON.parse(atob(payload)) as { exp?: number }
    if (typeof decoded.exp !== 'number') return 0
    const remaining = decoded.exp - Math.floor(Date.now() / 1000)
    return Math.max(0, remaining)
  } catch {
    return 0
  }
}

// Global auth state
const currentUser = ref<User | null>(null)
const isAuthenticated = ref<boolean>(false)
const isLoading = ref<boolean>(false)
const authError = ref<string | null>(null)
let isInitializingAuth = false
let hasAttemptedInit = false

// Singleton listener for logout events from token refresh interceptor (registered once at module load)
let _logoutListenerRegistered = false

function scheduleProactiveRefresh(expiresInSeconds: number, doRefresh: () => Promise<boolean>) {
  cancelProactiveRefresh()
  const refreshAfter = Math.max(
    MIN_REFRESH_INTERVAL_SECONDS,
    Math.floor(expiresInSeconds * REFRESH_LIFETIME_RATIO),
  )
  _refreshTimer = setTimeout(() => {
    _refreshTimer = null
    doRefresh()
  }, refreshAfter * 1000)
}

function cancelProactiveRefresh() {
  if (_refreshTimer !== null) {
    clearTimeout(_refreshTimer)
    _refreshTimer = null
  }
}

export function useAuth() {
  /**
   * Initialize authentication state
   */
  const initAuth = async () => {
    // Prevent concurrent calls from multiple component mounts
    if (isInitializingAuth) return
    isInitializingAuth = true

    try {
      // Get auth provider configuration (cached after first call)
      const authProvider = await getCachedAuthProvider()

      if (authProvider === 'none') {
        // No authentication required, set as authenticated with anonymous user
        currentUser.value = {
          id: 'anonymous',
          fullname: 'Anonymous User',
          email: 'anonymous@localhost',
          role: 'user',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
        isAuthenticated.value = true
        return
      }

      // For other auth providers, check token
      const token = getStoredToken()
      if (token) {
        setAuthToken(token)
        const expiresIn = getTokenExpiresIn(token)
        if (expiresIn <= 0) {
          // Token already expired — attempt immediate refresh
          await refreshAuthToken()
        } else {
          scheduleProactiveRefresh(expiresIn, refreshAuthToken)
          await loadCurrentUser()
        }
      }
    } finally {
      isInitializingAuth = false
      hasAttemptedInit = true
    }
  }

  /**
   * Load current user information
   */
  const loadCurrentUser = async () => {
    try {
      isLoading.value = true
      authError.value = null
      const user = await getCurrentUser()
      currentUser.value = user
      isAuthenticated.value = true
    } catch (error: unknown) {
      console.error('Failed to load current user:', error)
      // If token is invalid, clear auth state
      clearAuth()
      authError.value = error instanceof Error ? error.message : 'Failed to load user information'
    } finally {
      isLoading.value = false
    }
  }

  /**
   * User login
   */
  const login = async (credentials: LoginRequest): Promise<LoginResponse> => {
    try {
      isLoading.value = true
      authError.value = null
      
      const response = await apiLogin(credentials)
      
      // Store tokens
      storeToken(response.access_token)
      storeRefreshToken(response.refresh_token)
      setAuthToken(response.access_token)
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS, refreshAuthToken)

      // Update user state
      currentUser.value = response.user
      isAuthenticated.value = true

      return response
    } catch (error: unknown) {
      authError.value = error instanceof Error ? error.message : 'Login failed'
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * User registration
   */
  const register = async (data: RegisterRequest): Promise<RegisterResponse> => {
    try {
      isLoading.value = true
      authError.value = null
      
      const response = await apiRegister(data)
      
      // Store tokens
      storeToken(response.access_token)
      storeRefreshToken(response.refresh_token)
      setAuthToken(response.access_token)
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS, refreshAuthToken)

      // Update user state
      currentUser.value = response.user
      isAuthenticated.value = true

      return response
    } catch (error: unknown) {
      authError.value = error instanceof Error ? error.message : 'Registration failed'
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * User logout
   */
  const logout = async (silent: boolean = false) => {
    try {
      if (!silent) {
        isLoading.value = true
        authError.value = null
        
        // Call logout API
        await apiLogout()
      }
    } catch (error: unknown) {
      console.error('Logout API failed:', error)
      // Continue with local logout even if API fails
    } finally {
      // Clear local auth state
      clearAuth()
      isLoading.value = false
    }
  }

  /**
   * Clear authentication state
   */
  const clearAuth = () => {
    cancelProactiveRefresh()
    currentUser.value = null
    isAuthenticated.value = false
    clearAuthToken()
    clearStoredTokens()
    migrateStaleTokens()  // Also purge any legacy keys
    authError.value = null
  }

  /**
   * Refresh authentication token
   */
  const refreshAuthToken = async (): Promise<boolean> => {
    const refreshToken = getStoredRefreshToken()
    if (!refreshToken) {
      clearAuth()
      return false
    }

    try {
      const response = await apiRefreshToken({ refresh_token: refreshToken })

      // Store new access token
      storeToken(response.access_token)
      setAuthToken(response.access_token)
      scheduleProactiveRefresh(response.expires_in ?? DEFAULT_TOKEN_LIFETIME_SECONDS, refreshAuthToken)

      return true
    } catch (error: unknown) {
      console.error('Token refresh failed:', error)
      clearAuth()
      return false
    }
  }

  /**
   * Check if user has specific role
   */
  const hasRole = (role: string): boolean => {
    return currentUser.value?.role === role
  }

  /**
   * Check if user is admin
   */
  const isAdmin = computed(() => hasRole('admin'))

  /**
   * Check if user account is active
   */
  const isActive = computed(() => currentUser.value?.is_active === true)

  /**
   * Clear authentication error
   */
  const clearError = () => {
    authError.value = null
  }

  // Register global logout listener once (singleton — not per-component)
  if (!_logoutListenerRegistered) {
    window.addEventListener('auth:logout', () => {
      logout(true)
    })
    _logoutListenerRegistered = true
  }

  // Auto-initialize auth state when composable is first used (once per app lifecycle)
  if (!hasAttemptedInit && !isAuthenticated.value && !isLoading.value) {
    initAuth()
  }

  return {
    // State
    currentUser: computed(() => currentUser.value),
    isAuthenticated: computed(() => isAuthenticated.value),
    isLoading: computed(() => isLoading.value),
    authError: computed(() => authError.value),
    isAdmin,
    isActive,
    
    // Actions
    login,
    register,
    logout,
    initAuth,
    loadCurrentUser,
    refreshAuthToken,
    hasRole,
    clearError,
    clearAuth
  }
} 