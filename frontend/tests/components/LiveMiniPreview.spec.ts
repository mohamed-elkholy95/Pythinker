import { describe, expect, it } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import LiveMiniPreview from '@/components/LiveMiniPreview.vue'

describe('LiveMiniPreview', () => {
  it('does not render live preview without tool context', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders live preview when browser tool context is active', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'browser',
        toolFunction: 'browser_navigate',
        isActive: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(true)
  })

  it('does not render live preview while initializing', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'browser',
        toolFunction: 'browser_navigate',
        isActive: true,
        isInitializing: true,
      },
    })

    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders final replay screenshot when session is complete', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        replayScreenshotUrl: 'blob:final-screenshot',
        isActive: false,
      },
    })

    expect(wrapper.find('.final-screenshot-image').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
  })

  it('renders completed placeholder when replay screenshot is unavailable', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        isActive: false,
      },
    })

    expect(wrapper.find('.final-screenshot-placeholder').exists()).toBe(true)
    expect(wrapper.text()).toContain('Session Complete')
  })

  it('does not show initializing dots when session is complete', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSessionComplete: true,
        isActive: false,
      },
    })

    expect(wrapper.find('.init-loading-dots').exists()).toBe(false)
  })

  it('prioritizes summary streaming view over terminal preview and live preview', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'shell',
        toolFunction: 'shell_exec',
        isActive: true,
        contentPreview: '$ npm test\nrunning...',
        isSummaryStreaming: true,
        summaryStreamText: '## Partial report',
      },
    })

    expect(wrapper.find('.streaming-preview').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'LiveViewer' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('Writing report...')
  })

  it('shows report-complete summary view when summary text is buffered after stream end', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSummaryStreaming: false,
        summaryStreamText: 'Final summary text',
      },
    })

    expect(wrapper.find('.streaming-preview').exists()).toBe(true)
    expect(wrapper.text()).toContain('Report complete')
  })

  it('keeps report-complete view visible from persisted final report text after streaming clears', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        toolName: 'browser',
        toolFunction: 'browser_navigate',
        isSessionComplete: true,
        replayScreenshotUrl: 'blob:final-screenshot',
        isActive: false,
        finalReportText: '# Final report',
      },
    })

    expect(wrapper.find('.streaming-preview').exists()).toBe(true)
    expect(wrapper.find('.final-screenshot-image').exists()).toBe(false)
    expect(wrapper.text()).toContain('Report complete')
  })

  // ── Planning preview tests ──────────────────────────────────────

  it('renders planning preview when planPresentationText is present', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        planPresentationText: '# AI Frameworks Plan\n## Step 1',
        isPlanStreaming: true,
      },
    })

    expect(wrapper.find('.streaming-preview').exists()).toBe(true)
    expect(wrapper.text()).toContain('Creating plan...')
  })

  it('shows "Plan ready" when isPlanStreaming=false with plan text', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        planPresentationText: '# Final Plan\n## Step 1',
        isPlanStreaming: false,
      },
    })

    expect(wrapper.find('.streaming-preview').exists()).toBe(true)
    expect(wrapper.text()).toContain('Plan ready')
  })

  it('summary/report preview still wins when both report and plan data are present', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        isSummaryStreaming: true,
        summaryStreamText: '## Report content',
        planPresentationText: '# Plan content',
        isPlanStreaming: false,
      },
    })

    expect(wrapper.text()).toContain('Writing report...')
    expect(wrapper.text()).not.toContain('Plan ready')
  })
})
