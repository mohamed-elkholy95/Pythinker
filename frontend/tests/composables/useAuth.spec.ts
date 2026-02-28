/**
 * Tests for useAuth composable
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock the auth API module before importing the composable
vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  getCurrentUser: vi.fn(),
  refreshToken: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  storeToken: vi.fn(),
  storeRefreshToken: vi.fn(),
  getStoredToken: vi.fn(),
  getStoredRefreshToken: vi.fn(),
  clearStoredTokens: vi.fn(),
  migrateStaleTokens: vi.fn(),
  getCachedAuthProvider: vi.fn(),
}))

import { useAuth } from '@/composables/useAuth'
import * as authApi from '@/api/auth'

const makeValidJwt = (expiresInSeconds: number = 3600): string => {
  const now = Math.floor(Date.now() / 1000)
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
  const payload = Buffer.from(JSON.stringify({ exp: now + expiresInSeconds })).toString('base64url')
  return `${header}.${payload}.signature`
}

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset module state between tests
    vi.resetModules()
    // Clear global auth state from previous tests
    // Must mock getCachedAuthProvider before calling useAuth to prevent initAuth side effects
    vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
    vi.mocked(authApi.getStoredToken).mockReturnValue(null)
    const { clearAuth } = useAuth()
    clearAuth()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('initial state', () => {
    it('should have correct initial state', async () => {
      // Mock getCachedAuthProvider to return 'password' so initAuth doesn't auto-authenticate
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)

      const { isAuthenticated, isLoading, currentUser, authError } = useAuth()

      expect(isAuthenticated.value).toBe(false)
      expect(isLoading.value).toBe(false)
      expect(currentUser.value).toBe(null)
      expect(authError.value).toBe(null)
    })
  })

  describe('initAuth', () => {
    it('should auto-authenticate when auth provider is none', async () => {
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('none')

      const { initAuth, isAuthenticated, currentUser } = useAuth()
      await initAuth()

      expect(isAuthenticated.value).toBe(true)
      expect(currentUser.value).toMatchObject({
        id: 'anonymous',
        email: 'anonymous@localhost',
      })
    })

    it('should load user when token exists', async () => {
      const mockUser = {
        id: 'user-123',
        fullname: 'Test User',
        email: 'test@example.com',
        role: 'user',
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }

      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(makeValidJwt())
      vi.mocked(authApi.getCurrentUser).mockResolvedValue(mockUser)

      const { initAuth, isAuthenticated, currentUser } = useAuth()
      await initAuth()

      expect(authApi.setAuthToken).toHaveBeenCalledWith(expect.stringContaining('.'))
      expect(isAuthenticated.value).toBe(true)
      expect(currentUser.value).toEqual(mockUser)
    })
  })

  describe('login', () => {
    it('should successfully login and store tokens', async () => {
      const mockResponse = {
        access_token: 'access-token-123',
        refresh_token: 'refresh-token-456',
        token_type: 'bearer',
        user: {
          id: 'user-123',
          fullname: 'Test User',
          email: 'test@example.com',
          role: 'user',
          is_active: true,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      }

      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)
      vi.mocked(authApi.login).mockResolvedValue(mockResponse)

      const { login, isAuthenticated, currentUser } = useAuth()
      const result = await login({ email: 'test@example.com', password: 'password123' })

      expect(authApi.storeToken).toHaveBeenCalledWith('access-token-123')
      expect(authApi.storeRefreshToken).toHaveBeenCalledWith('refresh-token-456')
      expect(authApi.setAuthToken).toHaveBeenCalledWith('access-token-123')
      expect(isAuthenticated.value).toBe(true)
      expect(currentUser.value).toEqual(mockResponse.user)
      expect(result).toEqual(mockResponse)
    })

    it('should handle login failure', async () => {
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)
      vi.mocked(authApi.login).mockRejectedValue(new Error('Invalid credentials'))

      const { login, authError, isAuthenticated } = useAuth()

      await expect(login({ email: 'test@example.com', password: 'wrong' })).rejects.toThrow('Invalid credentials')
      expect(authError.value).toBe('Invalid credentials')
      expect(isAuthenticated.value).toBe(false)
    })
  })

  describe('logout', () => {
    it('should clear auth state on logout', async () => {
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)
      vi.mocked(authApi.logout).mockResolvedValue(undefined)

      const { logout, isAuthenticated, currentUser } = useAuth()
      await logout()

      expect(authApi.clearAuthToken).toHaveBeenCalled()
      expect(authApi.clearStoredTokens).toHaveBeenCalled()
      expect(isAuthenticated.value).toBe(false)
      expect(currentUser.value).toBe(null)
    })
  })

  describe('hasRole', () => {
    it('should correctly check user role', async () => {
      const mockUser = {
        id: 'admin-123',
        fullname: 'Admin User',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }

      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(makeValidJwt())
      vi.mocked(authApi.getCurrentUser).mockResolvedValue(mockUser)

      const { initAuth, hasRole, isAdmin } = useAuth()
      await initAuth()

      expect(hasRole('admin')).toBe(true)
      expect(hasRole('user')).toBe(false)
      expect(isAdmin.value).toBe(true)
    })
  })

  describe('refreshAuthToken', () => {
    it('should refresh token successfully', async () => {
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)
      vi.mocked(authApi.getStoredRefreshToken).mockReturnValue('refresh-token')
      vi.mocked(authApi.refreshToken).mockResolvedValue({
        access_token: 'new-access-token',
        token_type: 'bearer',
      })

      const { refreshAuthToken } = useAuth()
      const result = await refreshAuthToken()

      expect(result).toBe(true)
      expect(authApi.storeToken).toHaveBeenCalledWith('new-access-token')
      expect(authApi.setAuthToken).toHaveBeenCalledWith('new-access-token')
    })

    it('should clear auth when no refresh token exists', async () => {
      vi.mocked(authApi.getCachedAuthProvider).mockResolvedValue('password')
      vi.mocked(authApi.getStoredToken).mockReturnValue(null)
      vi.mocked(authApi.getStoredRefreshToken).mockReturnValue(null)

      const { refreshAuthToken, isAuthenticated } = useAuth()
      const result = await refreshAuthToken()

      expect(result).toBe(false)
      expect(authApi.clearAuthToken).toHaveBeenCalled()
      expect(isAuthenticated.value).toBe(false)
    })
  })
})
