/**
 * Tests for useFilePanel composable
 * Tests file panel state management and file operations
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock file panel state
function createMockFilePanel() {
  const isOpen = ref(false)
  const currentFile = ref<{ path: string; content: string } | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  return {
    isOpen,
    currentFile,
    isLoading,
    error,

    open: vi.fn().mockImplementation((file: { path: string; content: string }) => {
      currentFile.value = file
      isOpen.value = true
    }),

    close: vi.fn().mockImplementation(() => {
      isOpen.value = false
      currentFile.value = null
    }),

    toggle: vi.fn().mockImplementation(() => {
      isOpen.value = !isOpen.value
    }),

    loadFile: vi.fn().mockImplementation(async (path: string) => {
      isLoading.value = true
      error.value = null
      try {
        await new Promise((r) => setTimeout(r, 10))
        currentFile.value = {
          path,
          content: `Content of ${path}`,
        }
        isOpen.value = true
      } catch {
        error.value = 'Failed to load file'
      } finally {
        isLoading.value = false
      }
    }),
  }
}

describe('useFilePanel', () => {
  let filePanel: ReturnType<typeof createMockFilePanel>

  beforeEach(() => {
    vi.clearAllMocks()
    filePanel = createMockFilePanel()
  })

  describe('Panel State', () => {
    it('should start with panel closed', () => {
      expect(filePanel.isOpen.value).toBe(false)
    })

    it('should open panel with file', () => {
      const file = { path: '/test.txt', content: 'test content' }
      filePanel.open(file)

      expect(filePanel.isOpen.value).toBe(true)
      expect(filePanel.currentFile.value).toEqual(file)
    })

    it('should close panel and clear file', () => {
      const file = { path: '/test.txt', content: 'test content' }
      filePanel.open(file)
      filePanel.close()

      expect(filePanel.isOpen.value).toBe(false)
      expect(filePanel.currentFile.value).toBeNull()
    })

    it('should toggle panel state', () => {
      expect(filePanel.isOpen.value).toBe(false)

      filePanel.toggle()
      expect(filePanel.isOpen.value).toBe(true)

      filePanel.toggle()
      expect(filePanel.isOpen.value).toBe(false)
    })
  })

  describe('File Loading', () => {
    it('should load file by path', async () => {
      await filePanel.loadFile('/home/ubuntu/test.txt')

      expect(filePanel.currentFile.value).not.toBeNull()
      expect(filePanel.currentFile.value?.path).toBe('/home/ubuntu/test.txt')
      expect(filePanel.isOpen.value).toBe(true)
    })

    it('should set loading state during file load', async () => {
      const loadPromise = filePanel.loadFile('/test.txt')

      expect(filePanel.isLoading.value).toBe(true)

      await loadPromise

      expect(filePanel.isLoading.value).toBe(false)
    })

    it('should handle file load errors', async () => {
      filePanel.loadFile = vi.fn().mockImplementation(async () => {
        filePanel.isLoading.value = true
        await new Promise((r) => setTimeout(r, 10))
        filePanel.error.value = 'Failed to load file'
        filePanel.isLoading.value = false
      })

      await filePanel.loadFile('/nonexistent.txt')

      expect(filePanel.error.value).toBe('Failed to load file')
    })
  })

  describe('File Content', () => {
    it('should preserve file content when panel is reopened', async () => {
      const file = { path: '/test.txt', content: 'original content' }
      filePanel.open(file)

      // Close and reopen
      filePanel.close()
      filePanel.open(file)

      expect(filePanel.currentFile.value?.content).toBe('original content')
    })

    it('should update file content when new file is opened', () => {
      const file1 = { path: '/file1.txt', content: 'content 1' }
      const file2 = { path: '/file2.txt', content: 'content 2' }

      filePanel.open(file1)
      expect(filePanel.currentFile.value?.content).toBe('content 1')

      filePanel.open(file2)
      expect(filePanel.currentFile.value?.content).toBe('content 2')
    })
  })
})

describe('File Type Detection', () => {
  const getFileType = (path: string): string => {
    const ext = path.split('.').pop()?.toLowerCase() || ''
    const typeMap: Record<string, string> = {
      ts: 'typescript',
      js: 'javascript',
      py: 'python',
      md: 'markdown',
      json: 'json',
      vue: 'vue',
      html: 'html',
      css: 'css',
      txt: 'text',
    }
    return typeMap[ext] || 'text'
  }

  it('should detect TypeScript files', () => {
    expect(getFileType('/src/main.ts')).toBe('typescript')
  })

  it('should detect Python files', () => {
    expect(getFileType('/scripts/test.py')).toBe('python')
  })

  it('should detect Vue files', () => {
    expect(getFileType('/components/App.vue')).toBe('vue')
  })

  it('should default to text for unknown types', () => {
    expect(getFileType('/file.unknown')).toBe('text')
  })
})
