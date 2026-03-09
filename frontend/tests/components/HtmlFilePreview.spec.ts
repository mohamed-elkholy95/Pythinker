import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HtmlFilePreview from '@/components/filePreviews/HtmlFilePreview.vue'
import type { FileInfo } from '@/api/file'

const buildFile = (overrides: Partial<FileInfo>): FileInfo => ({
  file_id: 'file-1',
  filename: 'file.txt',
  size: 1024,
  upload_date: '2026-03-09T10:00:00Z',
  ...overrides,
})

describe('HtmlFilePreview', () => {
  beforeEach(() => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('<html><body><div id="chart-root">chart</div></body></html>'),
    })

    vi.stubGlobal('fetch', fetchMock)
    window.fetch = fetchMock as typeof fetch
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders an embedded html preview for interactive chart files', async () => {
    const wrapper = mount(HtmlFilePreview, {
      props: {
        file: buildFile({
          file_id: 'chart-html',
          filename: 'chart-sales.html',
          file_url: '/files/chart.html',
          metadata: { is_chart: true, chart_engine: 'plotly' },
        }),
      },
    })

    await flushPromises()
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(1)
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/files/chart.html')
    expect(wrapper.find('iframe[title="HTML Preview"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Failed to load chart preview.')
  })
})
