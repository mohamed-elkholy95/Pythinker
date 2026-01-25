/**
 * API mocks for testing
 * Provides mock implementations of API calls and data fixtures
 */

import { vi } from 'vitest'

// Mock user data
export const mockUser = {
  id: 'user-123',
  email: 'test@example.com',
  fullname: 'Test User',
  role: 'user',
  is_active: true,
}

// Mock session data
export const mockSession = {
  id: 'session-123',
  user_id: 'user-123',
  status: 'running',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

// Mock tool content
export const mockToolContent = {
  name: 'file',
  function: 'file_read',
  args: {
    path: '/home/ubuntu/test.txt',
  },
  status: 'completed',
  result: 'File content here',
  timestamp: Date.now(),
}

export const mockMCPToolContent = {
  name: 'mcp',
  function: 'mcp_some_tool',
  args: {
    param1: 'value1',
  },
  status: 'calling',
  result: null,
  timestamp: Date.now(),
}

// Mock message data
export const mockUserMessage = {
  type: 'user',
  content: {
    content: 'Hello, how are you?',
    timestamp: Date.now(),
  },
}

export const mockAssistantMessage = {
  type: 'assistant',
  content: {
    content: 'I am doing well, thank you!',
    timestamp: Date.now(),
  },
}

export const mockToolMessage = {
  type: 'tool',
  content: mockToolContent,
}

export const mockStepMessage = {
  type: 'step',
  content: {
    description: 'Reading the configuration file',
    status: 'completed',
    tools: [mockToolContent],
    timestamp: Date.now(),
  },
}

// Mock auth tokens
export const mockTokens = {
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  token_type: 'Bearer',
}

// Mock API responses
export function createMockAuthAPI() {
  return {
    login: vi.fn().mockResolvedValue({ data: mockTokens }),
    logout: vi.fn().mockResolvedValue({ data: { success: true } }),
    register: vi.fn().mockResolvedValue({ data: mockUser }),
    getCurrentUser: vi.fn().mockResolvedValue({ data: mockUser }),
    refreshToken: vi.fn().mockResolvedValue({ data: mockTokens }),
  }
}

export function createMockSessionAPI() {
  return {
    createSession: vi.fn().mockResolvedValue({ data: mockSession }),
    getSession: vi.fn().mockResolvedValue({ data: mockSession }),
    listSessions: vi.fn().mockResolvedValue({ data: [mockSession] }),
    deleteSession: vi.fn().mockResolvedValue({ data: { success: true } }),
  }
}

// Mock localStorage
export function createMockLocalStorage() {
  const store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      Object.keys(store).forEach((key) => delete store[key])
    }),
    key: vi.fn((index: number) => Object.keys(store)[index] || null),
    get length() {
      return Object.keys(store).length
    },
  }
}

// Mock i18n
export function createMockI18n() {
  return {
    t: vi.fn((key: string) => key),
    locale: { value: 'en' },
    availableLocales: ['en', 'zh-CN'],
  }
}

// Mock plan data
export const mockPlanEventData = {
  event_id: 'plan-123',
  timestamp: Date.now(),
  steps: [
    {
      event_id: 'step-1',
      timestamp: Date.now(),
      id: '1',
      description: 'Analyze the requirements',
      status: 'completed' as const,
    },
    {
      event_id: 'step-2',
      timestamp: Date.now(),
      id: '2',
      description: 'Search for information',
      status: 'running' as const,
    },
    {
      event_id: 'step-3',
      timestamp: Date.now(),
      id: '3',
      description: 'Generate response',
      status: 'pending' as const,
    },
  ],
}

// Mock file info
export const mockFileInfo = {
  filename: 'document.pdf',
  path: '/home/ubuntu/documents/document.pdf',
  size: 1024 * 100, // 100KB
  mtime: Date.now(),
}

export const mockTextFileInfo = {
  filename: 'readme.txt',
  path: '/home/ubuntu/readme.txt',
  size: 256,
  mtime: Date.now(),
}

export const mockImageFileInfo = {
  filename: 'screenshot.png',
  path: '/home/ubuntu/images/screenshot.png',
  size: 1024 * 500, // 500KB
  mtime: Date.now(),
}

// Mock VNC data
export const mockVNCConfig = {
  host: 'localhost',
  port: 5902,
  password: 'secret',
  path: '/websockify',
}

// Mock report data
export const mockReportData = {
  id: 'report-123',
  title: 'Analysis Report',
  content: `# Analysis Report

## Summary

This is a test report with some content.

## Findings

- Finding 1
- Finding 2
- Finding 3

## Conclusion

Test conclusion here.`,
  lastModified: Date.now(),
  fileCount: 2,
  sections: [
    { title: 'Summary', preview: 'This is a test report with some content.', level: 2 },
    { title: 'Findings', preview: 'Finding 1 Finding 2 Finding 3', level: 2 },
    { title: 'Conclusion', preview: 'Test conclusion here.', level: 2 },
  ],
  attachments: [mockFileInfo, mockTextFileInfo],
}

// Mock SSE events
export const mockToolEvent = {
  event: 'tool' as const,
  data: {
    event_id: 'tool-event-1',
    timestamp: Date.now(),
    tool_call_id: 'call-123',
    name: 'file',
    status: 'calling' as const,
    function: 'file_read',
    args: { path: '/home/ubuntu/test.txt' },
  },
}

export const mockStepEvent = {
  event: 'step' as const,
  data: {
    event_id: 'step-event-1',
    timestamp: Date.now(),
    status: 'running' as const,
    id: '1',
    description: 'Processing request',
  },
}

export const mockMessageEvent = {
  event: 'message' as const,
  data: {
    event_id: 'msg-event-1',
    timestamp: Date.now(),
    content: 'Hello, I am processing your request.',
    role: 'assistant' as const,
    attachments: [],
  },
}

export const mockPlanEvent = {
  event: 'plan' as const,
  data: mockPlanEventData,
}

// Mock File API
export function createMockFileAPI() {
  return {
    getFileList: vi.fn().mockResolvedValue({ data: [mockFileInfo, mockTextFileInfo] }),
    getFileContent: vi.fn().mockResolvedValue({ data: 'File content here' }),
    getFileDownloadUrl: vi.fn().mockResolvedValue('http://localhost:8000/download/test.txt'),
    uploadFile: vi.fn().mockResolvedValue({ data: mockFileInfo }),
    deleteFile: vi.fn().mockResolvedValue({ data: { success: true } }),
  }
}

// Mock VNC API
export function createMockVNCAPI() {
  return {
    getVNCUrl: vi.fn().mockResolvedValue('ws://localhost:5902/websockify'),
    getVNCConfig: vi.fn().mockResolvedValue({ data: mockVNCConfig }),
  }
}

// Mock Settings API
export function createMockSettingsAPI() {
  return {
    getSettings: vi.fn().mockResolvedValue({
      data: {
        llm_provider: 'openai',
        model_name: 'gpt-4',
        temperature: 0.7,
        search_provider: 'bing',
      },
    }),
    updateSettings: vi.fn().mockResolvedValue({ data: { success: true } }),
    getProviders: vi.fn().mockResolvedValue({
      data: {
        llm_providers: ['openai', 'anthropic', 'ollama'],
        search_providers: ['bing', 'google', 'duckduckgo', 'brave'],
      },
    }),
  }
}

// Utility to reset all mocks
export function resetAllMocks() {
  vi.resetAllMocks()
}
