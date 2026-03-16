import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { FetchProgressEvent } from '@/composables/useBrowserWorkflow'
import BrowserProgress from '../BrowserProgress.vue'

const streamingEvents: FetchProgressEvent[] = [
  {
    event_id: '100-0',
    phase: 'fetching',
    url: 'https://example.com/article',
    mode: 'stealth',
    status: 'in_progress',
  },
  {
    event_id: '101-0',
    phase: 'completed',
    url: 'https://example.com/article',
    mode: 'stealth',
    tier_used: 'cache',
    from_cache: true,
  },
]

const failedEvents: FetchProgressEvent[] = [
  {
    event_id: '200-0',
    phase: 'failed',
    url: 'https://example.com/protected',
    mode: 'dynamic',
    error: 'Cloudflare blocked the request',
    suggested_mode: 'stealth',
  },
]

describe('BrowserProgress', () => {
  it('renders the latest progress state and a collapsible event log', () => {
    const wrapper = mount(BrowserProgress, {
      props: {
        events: streamingEvents,
        isStreaming: false,
        lastError: null,
      },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.attributes('aria-live')).toBe('polite')
    expect(wrapper.get('[data-testid="browser-progress-status"]').text()).toContain('Completed')
    expect(wrapper.get('[data-testid="browser-progress-mode"]').text()).toContain('Stealth')
    expect(wrapper.get('[data-testid="browser-progress-log"]').text()).toContain('2 events')
    expect(wrapper.text()).toContain('cache')
  })

  it('shows recovery guidance when the workflow fails', () => {
    const wrapper = mount(BrowserProgress, {
      props: {
        events: failedEvents,
        isStreaming: false,
        lastError: 'Cloudflare blocked the request',
      },
    })

    expect(wrapper.get('[data-testid="browser-progress-status"]').text()).toContain('Failed')
    expect(wrapper.get('[data-testid="browser-progress-error"]').text()).toContain('Cloudflare blocked the request')
    expect(wrapper.get('[data-testid="browser-progress-recovery"]').text()).toContain('Try stealth mode next.')
  })
})
