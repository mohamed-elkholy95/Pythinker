import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import BrowserChrome from '@/components/workspace/BrowserChrome.vue';

describe('BrowserChrome', () => {
  it('renders the redesigned control deck structure', () => {
    const wrapper = mount(BrowserChrome, {
      props: {
        url: 'https://example.com/docs?q=live',
      },
    });

    expect(wrapper.find('.browser-chrome--deck').exists()).toBe(true);
    expect(wrapper.find('.browser-chrome__traffic-lights').exists()).toBe(true);
    expect(wrapper.find('.browser-chrome__meta-badge').exists()).toBe(true);
  });
});
