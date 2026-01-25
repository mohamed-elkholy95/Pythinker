/**
 * Vitest global test setup
 * This file runs before each test file
 */

import { config } from '@vue/test-utils'
import { vi } from 'vitest'

// Global test configuration
config.global.stubs = {
  // Stub router-link and router-view by default
  RouterLink: true,
  RouterView: true,
}

// Global mock for i18n
config.global.mocks = {
  $t: (key: string) => key,
}

// Mock marked library for markdown parsing
vi.mock('marked', () => ({
  marked: (content: string) => `<p>${content}</p>`,
}))

// Mock DOMPurify
vi.mock('dompurify', () => ({
  default: {
    sanitize: (html: string) => html,
  },
}))

// Mock window.matchMedia for components that use it
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Mock ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverMock

// Mock IntersectionObserver
class IntersectionObserverMock {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.IntersectionObserver = IntersectionObserverMock as unknown as typeof IntersectionObserver

// Mock NoVNC for VNCViewer component
vi.mock('@novnc/novnc/lib/rfb', () => ({
  default: class MockRFB {
    constructor() {}
    disconnect() {}
    sendCredentials() {}
    addEventListener() {}
    removeEventListener() {}
    scaleViewport = true
    resizeSession = true
    clipViewport = false
  },
}))

// Mock Monaco Editor
vi.mock('monaco-editor', () => ({
  editor: {
    create: vi.fn(() => ({
      dispose: vi.fn(),
      setValue: vi.fn(),
      getValue: vi.fn(() => ''),
      onDidChangeModelContent: vi.fn(),
      getModel: vi.fn(() => ({
        getValue: vi.fn(() => ''),
        setValue: vi.fn(),
      })),
      layout: vi.fn(),
      updateOptions: vi.fn(),
    })),
    createModel: vi.fn(),
    defineTheme: vi.fn(),
    setTheme: vi.fn(),
    setModelLanguage: vi.fn(),
  },
  languages: {
    register: vi.fn(),
    setMonarchTokensProvider: vi.fn(),
    registerCompletionItemProvider: vi.fn(),
  },
}))

// Mock WebSocket for real-time components
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.OPEN
  url: string
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    // Simulate connection opening
    setTimeout(() => {
      if (this.onopen) this.onopen()
    }, 0)
  }

  send(_data: string) {}
  close() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) this.onclose()
  }
}
global.WebSocket = MockWebSocket as unknown as typeof WebSocket

// Mock canvas for VNC and other canvas-based components
HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  getImageData: vi.fn(() => ({ data: new Array(4).fill(0) })),
  putImageData: vi.fn(),
  createImageData: vi.fn(() => []),
  setTransform: vi.fn(),
  drawImage: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  scale: vi.fn(),
  rotate: vi.fn(),
  translate: vi.fn(),
  transform: vi.fn(),
  beginPath: vi.fn(),
  closePath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  fill: vi.fn(),
  measureText: vi.fn(() => ({ width: 0 })),
  fillText: vi.fn(),
  strokeText: vi.fn(),
})) as unknown as typeof HTMLCanvasElement.prototype.getContext

// Mock URL.createObjectURL and revokeObjectURL
URL.createObjectURL = vi.fn(() => 'blob:mock-url')
URL.revokeObjectURL = vi.fn()

// Mock clipboard API
Object.defineProperty(navigator, 'clipboard', {
  writable: true,
  value: {
    writeText: vi.fn().mockResolvedValue(undefined),
    readText: vi.fn().mockResolvedValue(''),
  },
})
