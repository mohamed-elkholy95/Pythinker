import { describe, it, expect } from 'vitest';
import { h } from 'vue';
import { mount } from '@vue/test-utils';
import ContentContainer from '../ContentContainer.vue';

describe('ContentContainer.vue', () => {
  describe('rendering', () => {
    it('should render with default props', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: '<div class="content">Test content</div>',
        },
      });

      expect(wrapper.find('.content-container').exists()).toBe(true);
      expect(wrapper.find('.content-inner').exists()).toBe(true);
      expect(wrapper.find('.content').text()).toBe('Test content');
    });

    it('should render slot content', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: '<p>Custom content here</p>',
        },
      });

      expect(wrapper.find('p').text()).toBe('Custom content here');
    });

    it('should have scrollable class by default', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(true);
    });

    it('should have default padding', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(true);
    });
  });

  describe('scrollable prop', () => {
    it('should be scrollable by default', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(true);
    });

    it('should not be scrollable when scrollable is false', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          scrollable: false,
        },
      });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(false);
    });

    it('should toggle scrollable class', async () => {
      const wrapper = mount(ContentContainer, {
        props: {
          scrollable: true,
        },
      });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(true);

      await wrapper.setProps({ scrollable: false });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(false);
    });
  });

  describe('centered prop', () => {
    it('should not be centered by default', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-container.centered').exists()).toBe(false);
    });

    it('should have centered class when centered is true', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          centered: true,
        },
      });

      expect(wrapper.find('.content-container.centered').exists()).toBe(true);
    });

    it('should toggle centered class', async () => {
      const wrapper = mount(ContentContainer, {
        props: {
          centered: false,
        },
      });

      expect(wrapper.find('.content-container.centered').exists()).toBe(false);

      await wrapper.setProps({ centered: true });

      expect(wrapper.find('.content-container.centered').exists()).toBe(true);
    });
  });

  describe('constrained prop', () => {
    it('should not be constrained by default', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(false);
      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(false);
      expect(wrapper.find('.content-inner.constrained-wide').exists()).toBe(false);
    });

    it('should have constrained class when constrained is true', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: true,
        },
      });

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(true);
    });

    it('should have constrained-medium class', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: 'medium',
        },
      });

      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(true);
    });

    it('should have constrained-wide class', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: 'wide',
        },
      });

      expect(wrapper.find('.content-inner.constrained-wide').exists()).toBe(true);
    });

    it('should toggle constrained variants', async () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: true,
        },
      });

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(true);

      await wrapper.setProps({ constrained: 'medium' });

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(false);
      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(true);

      await wrapper.setProps({ constrained: 'wide' });

      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(false);
      expect(wrapper.find('.content-inner.constrained-wide').exists()).toBe(true);

      await wrapper.setProps({ constrained: false });

      expect(wrapper.find('.content-inner.constrained-wide').exists()).toBe(false);
    });
  });

  describe('padding prop', () => {
    it('should have medium padding by default', () => {
      const wrapper = mount(ContentContainer);

      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(true);
    });

    it('should have no padding when padding is "none"', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'none',
        },
      });

      expect(wrapper.find('.content-inner.padding-none').exists()).toBe(false);
      expect(wrapper.find('.content-inner.padding-sm').exists()).toBe(false);
      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(false);
      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(false);
    });

    it('should have small padding', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'sm',
        },
      });

      expect(wrapper.find('.content-inner.padding-sm').exists()).toBe(true);
    });

    it('should have medium padding', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'md',
        },
      });

      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(true);
    });

    it('should have large padding', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'lg',
        },
      });

      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(true);
    });

    it('should toggle padding variants', async () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'sm',
        },
      });

      expect(wrapper.find('.content-inner.padding-sm').exists()).toBe(true);

      await wrapper.setProps({ padding: 'md' });

      expect(wrapper.find('.content-inner.padding-sm').exists()).toBe(false);
      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(true);

      await wrapper.setProps({ padding: 'lg' });

      expect(wrapper.find('.content-inner.padding-md').exists()).toBe(false);
      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(true);

      await wrapper.setProps({ padding: 'none' });

      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(false);
    });
  });

  describe('combined props', () => {
    it('should apply all props together', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          scrollable: true,
          centered: true,
          constrained: 'medium',
          padding: 'lg',
        },
      });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(true);
      expect(wrapper.find('.content-container.centered').exists()).toBe(true);
      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(true);
      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(true);
    });

    it('should handle all props at their non-default values', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          scrollable: false,
          centered: true,
          constrained: 'wide',
          padding: 'none',
        },
      });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(false);
      expect(wrapper.find('.content-container.centered').exists()).toBe(true);
      expect(wrapper.find('.content-inner.constrained-wide').exists()).toBe(true);
      expect(wrapper.find('.content-inner.padding-none').exists()).toBe(false);
    });
  });

  describe('structure', () => {
    it('should have correct DOM structure', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: '<div>Content</div>',
        },
      });

      const container = wrapper.find('.content-container');
      expect(container.exists()).toBe(true);

      const inner = container.find('.content-inner');
      expect(inner.exists()).toBe(true);

      // Slot content should be inside inner div
      expect(inner.find('div').text()).toBe('Content');
    });

    it('should nest content correctly', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: '<p class="test-content">Test</p>',
        },
      });

      // Content should be nested: container > inner > slot
      const container = wrapper.find('.content-container');
      const inner = container.find('.content-inner');
      const content = inner.find('.test-content');

      expect(content.text()).toBe('Test');
    });
  });

  describe('slot content', () => {
    it('should render simple text content', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: 'Simple text',
        },
      });

      expect(wrapper.text()).toContain('Simple text');
    });

    it('should render complex HTML content', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: `
            <div class="header">Header</div>
            <div class="body">Body</div>
            <div class="footer">Footer</div>
          `,
        },
      });

      expect(wrapper.find('.header').text()).toBe('Header');
      expect(wrapper.find('.body').text()).toBe('Body');
      expect(wrapper.find('.footer').text()).toBe('Footer');
    });

    it('should render multiple child components', () => {
      const ChildComponent = {
        template: '<div class="child">Child {{ id }}</div>',
        props: ['id'],
      };

      const wrapper = mount(ContentContainer, {
        slots: {
          default: () => [
            h(ChildComponent, { id: 1 }),
            h(ChildComponent, { id: 2 }),
          ],
        },
      });

      // Should contain slot content
      expect(wrapper.find('.content-inner').exists()).toBe(true);
    });
  });

  describe('responsive behavior', () => {
    it('should handle full-width content', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: false,
        },
        slots: {
          default: '<div style="width: 100%">Full width</div>',
        },
      });

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(false);
    });

    it('should constrain content width', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: true,
        },
        slots: {
          default: '<div>Constrained content</div>',
        },
      });

      expect(wrapper.find('.content-inner.constrained').exists()).toBe(true);
    });
  });

  describe('use cases', () => {
    it('should work as scrollable content area', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          scrollable: true,
          padding: 'md',
        },
        slots: {
          default: '<div class="long-content">Long scrolling content...</div>',
        },
      });

      expect(wrapper.find('.content-container.scrollable').exists()).toBe(true);
      expect(wrapper.find('.long-content').exists()).toBe(true);
    });

    it('should work as centered empty/loading state container', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          centered: true,
          scrollable: false,
        },
        slots: {
          default: '<div class="loading-state">Loading...</div>',
        },
      });

      expect(wrapper.find('.content-container.centered').exists()).toBe(true);
      expect(wrapper.find('.content-container.scrollable').exists()).toBe(false);
      expect(wrapper.find('.loading-state').exists()).toBe(true);
    });

    it('should work as constrained article/document container', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          constrained: 'medium',
          padding: 'lg',
        },
        slots: {
          default: '<article>Article content</article>',
        },
      });

      expect(wrapper.find('.content-inner.constrained-medium').exists()).toBe(true);
      expect(wrapper.find('.content-inner.padding-lg').exists()).toBe(true);
      expect(wrapper.find('article').exists()).toBe(true);
    });

    it('should work as full-bleed container', () => {
      const wrapper = mount(ContentContainer, {
        props: {
          padding: 'none',
          constrained: false,
        },
        slots: {
          default: '<div class="full-width">Full bleed content</div>',
        },
      });

      expect(wrapper.find('.content-inner.padding-none').exists()).toBe(false);
      expect(wrapper.find('.content-inner.constrained').exists()).toBe(false);
      expect(wrapper.find('.full-width').exists()).toBe(true);
    });
  });

  describe('accessibility', () => {
    it('should have proper semantic structure', () => {
      const wrapper = mount(ContentContainer, {
        slots: {
          default: '<main>Main content</main>',
        },
      });

      // Container provides structural div, slot can contain semantic elements
      expect(wrapper.find('main').exists()).toBe(true);
      expect(wrapper.find('main').text()).toBe('Main content');
    });
  });
});
