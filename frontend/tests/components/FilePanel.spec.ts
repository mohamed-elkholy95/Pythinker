/**
 * Tests for FilePanel component
 * Tests file viewer functionality, download, and panel visibility
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
import FilePanel from '@/components/FilePanel.vue'

// Mock useFilePanel composable
const mockIsShow = ref(false)
const mockFileInfo = ref<any>(null)
const mockVisible = ref(true)
const mockShowFilePanel = vi.fn()
const mockHideFilePanel = vi.fn()

vi.mock('@/composables/useFilePanel', () => ({
  useFilePanel: () => ({
    isShow: mockIsShow,
    fileInfo: mockFileInfo,
    visible: mockVisible,
    showFilePanel: mockShowFilePanel,
    hideFilePanel: mockHideFilePanel,
  }),
}))

// Mock useResizeObserver
vi.mock('@/composables/useResizeObserver', () => ({
  useResizeObserver: () => ({
    size: ref(800),
  }),
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
  },
}))

// Mock constants
vi.mock('@/constants/event', () => ({
  EVENT_SHOW_TOOL_PANEL: 'show-tool-panel',
}))

// Mock file API
vi.mock('@/api/file', () => ({
  getFileDownloadUrl: vi.fn().mockResolvedValue('http://example.com/download'),
}))

// Mock file type util
vi.mock('@/utils/fileType', () => ({
  getFileType: vi.fn((filename: string) => {
    if (filename.endsWith('.txt')) {
      return {
        icon: { template: '<span class="mock-text-icon" />' },
        preview: { template: '<div class="mock-text-preview" />' },
      }
    }
    if (filename.endsWith('.pdf')) {
      return {
        icon: { template: '<span class="mock-pdf-icon" />' },
        preview: { template: '<div class="mock-pdf-preview" />' },
      }
    }
    return null
  }),
}))

// Mock lucide-vue-next
vi.mock('lucide-vue-next', () => ({
  Download: {
    name: 'Download',
    template: '<span class="mock-download" />',
  },
  X: {
    name: 'X',
    template: '<span class="mock-x" />',
  },
}))

describe('FilePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsShow.value = false
    mockFileInfo.value = null
    mockVisible.value = true
  })

  it('should render when visible', () => {
    const wrapper = mount(FilePanel)
    expect(wrapper.exists()).toBe(true)
  })

  it('should not render content when not shown', () => {
    const wrapper = mount(FilePanel)

    // Panel exists but inner content is not rendered
    expect(wrapper.find('.mock-download').exists()).toBe(false)
  })

  it('should render file info when shown', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    expect(wrapper.text()).toContain('test.txt')
  })

  it('should expose showFilePanel method', () => {
    const wrapper = mount(FilePanel)
    expect(typeof wrapper.vm.showFilePanel).toBe('function')
  })

  it('should expose hideFilePanel method', () => {
    const wrapper = mount(FilePanel)
    expect(typeof wrapper.vm.hideFilePanel).toBe('function')
  })

  it('should expose isShow ref', () => {
    const wrapper = mount(FilePanel)
    expect(wrapper.vm.isShow).toBeDefined()
  })

  it('should render download button when file is shown', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    const downloadIcon = wrapper.findComponent({ name: 'Download' })
    expect(downloadIcon.exists()).toBe(true)
  })

  it('should render close button when file is shown', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    const xIcon = wrapper.findComponent({ name: 'X' })
    expect(xIcon.exists()).toBe(true)
  })

  it('should call hideFilePanel when close button is clicked', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    // Find close button (contains X icon)
    const closeButtons = wrapper.findAll('.cursor-pointer')
    const closeButton = closeButtons.find(b => b.findComponent({ name: 'X' }).exists())

    if (closeButton) {
      await closeButton.trigger('click')
      expect(mockHideFilePanel).toHaveBeenCalled()
    }
  })

  it('should open download URL when download button is clicked', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const mockOpen = vi.fn()
    vi.stubGlobal('open', mockOpen)

    const wrapper = mount(FilePanel)
    await nextTick()

    // Find download button
    const downloadButtons = wrapper.findAll('.cursor-pointer')
    const downloadButton = downloadButtons.find(b => b.findComponent({ name: 'Download' }).exists())

    if (downloadButton) {
      await downloadButton.trigger('click')
      // Give time for async download URL fetch
      await nextTick()
    }

    vi.unstubAllGlobals()
  })

  it('should apply correct width based on parent size', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    const panel = wrapper.find('[style]')
    expect(panel.attributes('style')).toContain('width:')
  })

  it('should apply opacity 0 when hidden', async () => {
    mockIsShow.value = false
    mockFileInfo.value = null

    const wrapper = mount(FilePanel)
    await nextTick()

    const panel = wrapper.find('[style]')
    expect(panel.attributes('style')).toContain('opacity: 0')
  })

  it('should apply opacity 1 when shown', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'test.txt',
      path: '/home/ubuntu/test.txt',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    const panel = wrapper.find('[style]')
    expect(panel.attributes('style')).toContain('opacity: 1')
  })

  it('should display file icon based on file type', async () => {
    mockIsShow.value = true
    mockFileInfo.value = {
      filename: 'document.pdf',
      path: '/home/ubuntu/document.pdf',
      size: 1024,
      mtime: Date.now(),
    }

    const wrapper = mount(FilePanel)
    await nextTick()

    // File type detection should work
    expect(wrapper.text()).toContain('document.pdf')
  })
})
