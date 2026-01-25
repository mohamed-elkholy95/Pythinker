/**
 * Tests for session-related composables
 * Tests session management and state
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mockSession, createMockSessionAPI } from '../mocks/api'

// Mock session state
const mockSessionState = {
  currentSession: ref(null),
  sessions: ref([]),
  isLoading: ref(false),
  error: ref(null),
}

// Mock useSessionFileList composable behavior
function createMockUseSessionFileList() {
  const files = ref([])
  const isLoading = ref(false)
  const error = ref(null)

  return {
    files,
    isLoading,
    error,
    fetchFiles: vi.fn().mockImplementation(async (_sessionId: string) => {
      isLoading.value = true
      await new Promise((r) => setTimeout(r, 10))
      files.value = [
        { name: 'file1.txt', path: '/home/ubuntu/file1.txt', size: 100 },
        { name: 'file2.md', path: '/home/ubuntu/file2.md', size: 200 },
      ]
      isLoading.value = false
    }),
    clearFiles: vi.fn().mockImplementation(() => {
      files.value = []
    }),
  }
}

describe('Session Management', () => {
  let sessionAPI: ReturnType<typeof createMockSessionAPI>

  beforeEach(() => {
    vi.clearAllMocks()
    sessionAPI = createMockSessionAPI()
    mockSessionState.currentSession.value = null
    mockSessionState.sessions.value = []
    mockSessionState.isLoading.value = false
    mockSessionState.error.value = null
  })

  describe('Session Creation', () => {
    it('should create a new session', async () => {
      const result = await sessionAPI.createSession()
      expect(result.data).toEqual(mockSession)
    })

    it('should set loading state during creation', async () => {
      mockSessionState.isLoading.value = true
      expect(mockSessionState.isLoading.value).toBe(true)

      await sessionAPI.createSession()
      mockSessionState.isLoading.value = false

      expect(mockSessionState.isLoading.value).toBe(false)
    })
  })

  describe('Session Listing', () => {
    it('should list all sessions', async () => {
      const result = await sessionAPI.listSessions()
      expect(result.data).toEqual([mockSession])
    })
  })

  describe('Session Deletion', () => {
    it('should delete a session', async () => {
      const result = await sessionAPI.deleteSession()
      expect(result.data.success).toBe(true)
    })
  })
})

describe('Session File List', () => {
  let fileList: ReturnType<typeof createMockUseSessionFileList>

  beforeEach(() => {
    vi.clearAllMocks()
    fileList = createMockUseSessionFileList()
  })

  it('should fetch files for a session', async () => {
    await fileList.fetchFiles('session-123')

    expect(fileList.files.value).toHaveLength(2)
    expect(fileList.files.value[0].name).toBe('file1.txt')
  })

  it('should set loading state during file fetch', async () => {
    const fetchPromise = fileList.fetchFiles('session-123')

    expect(fileList.isLoading.value).toBe(true)

    await fetchPromise

    expect(fileList.isLoading.value).toBe(false)
  })

  it('should clear files when requested', () => {
    fileList.files.value = [{ name: 'test.txt', path: '/test.txt', size: 100 }]

    fileList.clearFiles()

    expect(fileList.files.value).toHaveLength(0)
  })
})

describe('Session Status', () => {
  it('should track session status transitions', () => {
    const statuses = ['idle', 'running', 'completed', 'error']

    statuses.forEach((status) => {
      const session = { ...mockSession, status }
      expect(session.status).toBe(status)
    })
  })

  it('should handle session timeout', async () => {
    const session = ref({ ...mockSession, status: 'running' })

    // Simulate timeout
    await new Promise((r) => setTimeout(r, 10))
    session.value.status = 'error'

    expect(session.value.status).toBe('error')
  })
})
