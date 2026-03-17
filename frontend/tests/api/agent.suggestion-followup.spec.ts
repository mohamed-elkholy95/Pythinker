/**
 * Tests for follow-up context in agent API
 * Verifies that follow_up metadata is properly sent with chat requests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock the API client
const mockCreateSSEConnection = vi.fn()

vi.mock('@/api/client', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
  createSSEConnection: (...args: unknown[]) => mockCreateSSEConnection(...args),
  API_CONFIG: { host: 'http://localhost:8000' },
}))

describe('Agent API - Follow-up Context', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should send follow_up metadata when provided', async () => {
    const { chatWithSession } = await import('../../src/api/agent')

    mockCreateSSEConnection.mockResolvedValue(() => {})

    await chatWithSession(
      'session123',
      'Tell me more about that',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      {
        selected_suggestion: 'Can you explain this in more detail?',
        anchor_event_id: 'evt_123456',
        source: 'suggestion_click',
      }
    )

    expect(mockCreateSSEConnection).toHaveBeenCalledWith(
      '/sessions/session123/chat',
      {
        method: 'POST',
        body: expect.objectContaining({
          message: 'Tell me more about that',
          follow_up: {
            selected_suggestion: 'Can you explain this in more detail?',
            anchor_event_id: 'evt_123456',
            source: 'suggestion_click',
          },
        }),
      },
      undefined
    )
  })

  it('should not send follow_up when not provided', async () => {
    const { chatWithSession } = await import('../../src/api/agent')

    mockCreateSSEConnection.mockResolvedValue(() => {})

    await chatWithSession('session123', 'Regular message')

    expect(mockCreateSSEConnection).toHaveBeenCalledWith(
      '/sessions/session123/chat',
      {
        method: 'POST',
        body: expect.objectContaining({
          message: 'Regular message',
        }),
      },
      undefined
    )

    const callArgs = mockCreateSSEConnection.mock.calls[0]
    expect(callArgs[1].body).not.toHaveProperty('follow_up')
  })

  it('should send follow_up as null when explicitly set to null', async () => {
    const { chatWithSession } = await import('../../src/api/agent')

    mockCreateSSEConnection.mockResolvedValue(() => {})

    await chatWithSession(
      'session123',
      'Message',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      null
    )

    const callArgs = mockCreateSSEConnection.mock.calls[0]
    // When null is passed, we don't include it in the body
    expect(callArgs[1].body).not.toHaveProperty('follow_up')
  })

  it('should include follow_up with other request fields', async () => {
    const { chatWithSession } = await import('../../src/api/agent')

    mockCreateSSEConnection.mockResolvedValue(() => {})

    await chatWithSession(
      'session123',
      'Follow-up message',
      'evt_prev',
      [{ file_id: 'file1', filename: 'test.txt', content_type: 'text/plain', size: 100, upload_date: '2024-01-01' }],
      ['skill1'],
      { deep_research: true },
      undefined,
      {
        selected_suggestion: 'What about X?',
        anchor_event_id: 'evt_789',
        source: 'suggestion_click',
      }
    )

    const callArgs = mockCreateSSEConnection.mock.calls[0]
    const body = callArgs[1].body

    // event_id is intentionally omitted when fresh input is provided
    // (hasFreshInput is true due to non-empty message, attachments, skills, etc.)
    expect(body).not.toHaveProperty('event_id')
    expect(body.message).toBe('Follow-up message')
    expect(body.attachments).toEqual([{ file_id: 'file1', filename: 'test.txt', content_type: 'text/plain', size: 100, upload_date: '2024-01-01' }])
    expect(body.skills).toEqual(['skill1'])
    expect(body.deep_research).toBe(true)
    expect(body.follow_up).toEqual({
      selected_suggestion: 'What about X?',
      anchor_event_id: 'evt_789',
      source: 'suggestion_click',
    })
  })
})
