import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PdfFilePreview from '../PdfFilePreview.vue'
import { downloadFile, getFileUrl } from '../../../api/file'

const pdfjsMocks = vi.hoisted(() => {
  const renderPromise = vi.fn().mockResolvedValue(undefined)
  const cleanup = vi.fn()
  const getPage = vi.fn(async () => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
    render: vi.fn(() => ({ promise: renderPromise() })),
    cleanup,
  }))
  const getDocument = vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 1,
      getPage,
    }),
  }))

  return {
    renderPromise,
    cleanup,
    getPage,
    getDocument,
  }
})

vi.mock('../../../api/file', () => ({
  downloadFile: vi.fn(),
  getFileUrl: vi.fn(),
}))

vi.mock('pdfjs-dist/build/pdf.mjs', () => ({
  GlobalWorkerOptions: {},
  getDocument: pdfjsMocks.getDocument,
}))

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: 'worker-url',
}))

describe('PdfFilePreview', () => {
  const canvasContext = {
    setTransform: vi.fn(),
  }

  beforeEach(() => {
    vi.mocked(downloadFile).mockReset()
    vi.mocked(getFileUrl).mockReset()
    pdfjsMocks.getDocument.mockClear()
    pdfjsMocks.getPage.mockClear()
    pdfjsMocks.cleanup.mockClear()
    pdfjsMocks.renderPromise.mockClear()

    vi.mocked(getFileUrl).mockImplementation((fileId: string) => `http://backend/api/v1/files/${fileId}/download`)
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['%PDF-1.4 test']))

    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => canvasContext as never)
  })

  it('renders the PDF bytes with PDF.js and exposes the backend link', async () => {
    const wrapper = mount(PdfFilePreview, {
      props: {
        file: {
          file_id: 'file-123',
          filename: 'report.pdf',
          size: 1024,
          upload_date: '2026-04-02T00:00:00Z',
        },
      },
    })

    await flushPromises()

    expect(vi.mocked(downloadFile)).toHaveBeenCalledWith('file-123')
    expect(pdfjsMocks.getDocument).toHaveBeenCalledOnce()
    expect(pdfjsMocks.getPage).toHaveBeenCalledWith(1)
    expect(wrapper.text()).toContain('Rendered with PDF.js')
    expect(wrapper.findAll('canvas')).toHaveLength(1)
    expect(wrapper.find('a[href="http://backend/api/v1/files/file-123/download"]').exists()).toBe(true)
  })

  it('shows a readable error when the PDF cannot be fetched', async () => {
    vi.mocked(downloadFile).mockRejectedValueOnce(new Error('network down'))

    const wrapper = mount(PdfFilePreview, {
      props: {
        file: {
          file_id: 'file-456',
          filename: 'broken.pdf',
          size: 1024,
          upload_date: '2026-04-02T00:00:00Z',
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Unable to render PDF preview')
    expect(wrapper.text()).toContain('network down')
    expect(wrapper.find('a[href="http://backend/api/v1/files/file-456/download"]').exists()).toBe(true)
  })
})
