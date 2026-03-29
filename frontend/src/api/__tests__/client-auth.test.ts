import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  clearStoredTokensMock,
  getStoredRefreshTokenMock,
  getStoredTokenMock,
  pushMock,
  tokenExpiresInMock,
} = vi.hoisted(() => ({
  clearStoredTokensMock: vi.fn(),
  getStoredRefreshTokenMock: vi.fn(),
  getStoredTokenMock: vi.fn(),
  pushMock: vi.fn(),
  tokenExpiresInMock: vi.fn(),
}))

vi.mock('../auth', () => ({
  clearStoredTokens: clearStoredTokensMock,
  getStoredRefreshToken: getStoredRefreshTokenMock,
  getStoredToken: getStoredTokenMock,
  storeRefreshToken: vi.fn(),
  storeToken: vi.fn(),
}))

vi.mock('@/router', () => ({
  router: {
    currentRoute: {
      value: {
        path: '/chat',
      },
    },
    push: pushMock,
  },
}))

vi.mock('@/utils/jwt', () => ({
  tokenExpiresIn: tokenExpiresInMock,
}))

import { _requestInterceptorFulfilled, apiClient } from '../client'

describe('auth request interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getStoredTokenMock.mockReturnValue('expired-access-token')
    getStoredRefreshTokenMock.mockReturnValue(null)
    tokenExpiresInMock.mockReturnValue(0)
    apiClient.defaults.headers.Authorization = 'Bearer expired-access-token'
  })

  it('rejects expired requests immediately when no refresh token exists', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')

    await expect(
      _requestInterceptorFulfilled({
        url: '/sessions',
        headers: {},
      } as never),
    ).rejects.toMatchObject({
      code: 401,
      message: 'Authentication required',
    })

    expect(clearStoredTokensMock).toHaveBeenCalledTimes(1)
    expect(pushMock).toHaveBeenCalledWith('/login')
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth:logout' }),
    )
    expect(apiClient.defaults.headers.Authorization).toBeUndefined()
  })
})
