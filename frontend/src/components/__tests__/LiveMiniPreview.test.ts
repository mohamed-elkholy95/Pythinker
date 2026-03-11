import { shallowMount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import LiveMiniPreview from '../LiveMiniPreview.vue';

describe('LiveMiniPreview', () => {
  it('renders a simplified skeleton while initializing', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        isInitializing: true,
      },
      global: {
        stubs: {
          LiveViewer: {
            name: 'LiveViewer',
            template: '<div class="live-viewer-stub" />',
          },
          WideResearchMiniPreview: true,
        },
      },
    });

    expect(wrapper.find('.init-skeleton').exists()).toBe(true);
    expect(wrapper.find('.boot-dots').exists()).toBe(false);
    expect(wrapper.find('.scan-line').exists()).toBe(false);
  });

  it('prefers the browser live preview for active search sessions', () => {
    const wrapper = shallowMount(LiveMiniPreview, {
      props: {
        sessionId: 'session-123',
        enabled: true,
        isActive: true,
        toolName: 'search',
        toolFunction: 'web_search',
        searchQuery: 'latest browser automation news',
        searchResults: [
          {
            title: 'Example result',
            link: 'https://example.com/article',
            snippet: 'Example snippet',
          },
        ],
      },
      global: {
        stubs: {
          LiveViewer: {
            name: 'LiveViewer',
            template: '<div class="live-viewer-stub" />',
          },
          WideResearchMiniPreview: true,
        },
      },
    });

    expect(wrapper.find('.live-preview-container').exists()).toBe(true);
    expect(wrapper.find('.search-preview').exists()).toBe(false);
  });
});
