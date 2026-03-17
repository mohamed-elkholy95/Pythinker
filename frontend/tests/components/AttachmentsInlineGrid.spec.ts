import { mount } from '@vue/test-utils'
import { describe, expect, it, vi, afterEach } from 'vitest'
import AttachmentsInlineGrid from '@/components/report/AttachmentsInlineGrid.vue'
import type { FileInfo } from '@/api/file'

vi.mock('@/api/file', () => ({
  fileApi: {
    getFileUrl: (fileId: string) => `https://example.com/files/${fileId}`,
  },
}))

vi.mock('@/components/FileTypeIcon.vue', () => ({
  default: {
    name: 'FileTypeIcon',
    template: '<div class="mock-file-type-icon" />',
    props: ['filename', 'size'],
  },
}))

const buildFile = (overrides: Partial<FileInfo>): FileInfo => ({
  file_id: 'file-1',
  filename: 'file.txt',
  size: 1024,
  upload_date: '2026-03-09T10:00:00Z',
  ...overrides,
})

describe('AttachmentsInlineGrid', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('emits the paired chart html file instead of opening a raw download url', async () => {
    const pngFile = buildFile({
      file_id: 'chart-png',
      filename: 'chart-sales.png',
      metadata: { is_chart: true, chart_engine: 'plotly' },
    })
    const htmlFile = buildFile({
      file_id: 'chart-html',
      filename: 'chart-sales.html',
      metadata: { is_chart: true, chart_engine: 'plotly' },
    })

    const openSpy = vi.fn()
    vi.stubGlobal('open', openSpy)

    const wrapper = mount(AttachmentsInlineGrid, {
      props: {
        attachments: [pngFile, htmlFile],
      },
    })

    await wrapper.get('.chart-preview-card').trigger('click')

    expect(wrapper.emitted('openFile')).toEqual([[htmlFile]])
    expect(openSpy).not.toHaveBeenCalled()
  })
})
