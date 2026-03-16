import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import EmptyState from '../EmptyState.vue';
import { FileText, Terminal, Search, Globe, Code, Inbox } from 'lucide-vue-next';

describe('EmptyState.vue', () => {
  describe('rendering', () => {
    it('should render message', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No results found',
        },
      });

      expect(wrapper.find('.empty-message').text()).toBe('No results found');
    });

    it('should render without icon by default', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
        },
      });

      // When no icon prop is provided, it defaults to 'inbox'
      expect(wrapper.find('.empty-icon').exists()).toBe(false);
    });

    it('should not have overlay class by default', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
        },
      });

      expect(wrapper.find('.empty-state.overlay').exists()).toBe(false);
    });

    it('should have overlay class when overlay is true', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
          overlay: true,
        },
      });

      expect(wrapper.find('.empty-state.overlay').exists()).toBe(true);
    });
  });

  describe('icon rendering', () => {
    it('should render file icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No files',
          icon: 'file',
        },
      });

      const icon = wrapper.findComponent(FileText);
      expect(icon.exists()).toBe(true);
      expect(icon.classes()).toContain('empty-icon');
    });

    it('should render terminal icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No commands',
          icon: 'terminal',
        },
      });

      const icon = wrapper.findComponent(Terminal);
      expect(icon.exists()).toBe(true);
    });

    it('should render search icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No results',
          icon: 'search',
        },
      });

      const icon = wrapper.findComponent(Search);
      expect(icon.exists()).toBe(true);
    });

    it('should render browser icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No pages',
          icon: 'browser',
        },
      });

      const icon = wrapper.findComponent(Globe);
      expect(icon.exists()).toBe(true);
    });

    it('should render code icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No code',
          icon: 'code',
        },
      });

      const icon = wrapper.findComponent(Code);
      expect(icon.exists()).toBe(true);
    });

    it('should render inbox icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty inbox',
          icon: 'inbox',
        },
      });

      const icon = wrapper.findComponent(Inbox);
      expect(icon.exists()).toBe(true);
    });
  });

  describe('action slot', () => {
    it('should render action slot content', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No data',
        },
        slots: {
          action: '<button class="retry-btn">Retry</button>',
        },
      });

      expect(wrapper.find('.retry-btn').exists()).toBe(true);
      expect(wrapper.find('.retry-btn').text()).toBe('Retry');
    });

    it('should not render action slot when not provided', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
        },
      });

      const html = wrapper.html();
      expect(html).not.toContain('button');
    });

    it('should render complex action slot', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No items',
        },
        slots: {
          action: `
            <div class="actions">
              <button>Add Item</button>
              <button>Import</button>
            </div>
          `,
        },
      });

      expect(wrapper.find('.actions').exists()).toBe(true);
      expect(wrapper.findAll('button').length).toBe(2);
    });
  });

  describe('structure and classes', () => {
    it('should have correct root class', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
        },
      });

      expect(wrapper.find('.empty-state').exists()).toBe(true);
    });

    it('should have empty-message class', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Test message',
        },
      });

      expect(wrapper.find('.empty-message').exists()).toBe(true);
    });

    it('should have empty-icon class when icon is provided', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
          icon: 'search',
        },
      });

      expect(wrapper.find('.empty-icon').exists()).toBe(true);
    });
  });

  describe('prop updates', () => {
    it('should update message when prop changes', async () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Initial message',
        },
      });

      expect(wrapper.find('.empty-message').text()).toBe('Initial message');

      await wrapper.setProps({ message: 'Updated message' });

      expect(wrapper.find('.empty-message').text()).toBe('Updated message');
    });

    it('should update icon when prop changes', async () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
          icon: 'file',
        },
      });

      expect(wrapper.findComponent(FileText).exists()).toBe(true);

      await wrapper.setProps({ icon: 'search' });

      expect(wrapper.findComponent(FileText).exists()).toBe(false);
      expect(wrapper.findComponent(Search).exists()).toBe(true);
    });

    it('should toggle overlay class when prop changes', async () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
          overlay: false,
        },
      });

      expect(wrapper.find('.empty-state.overlay').exists()).toBe(false);

      await wrapper.setProps({ overlay: true });

      expect(wrapper.find('.empty-state.overlay').exists()).toBe(true);
    });
  });

  describe('message formatting', () => {
    it('should handle short messages', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Empty',
        },
      });

      expect(wrapper.find('.empty-message').text()).toBe('Empty');
    });

    it('should handle long messages', () => {
      const longMessage = 'This is a very long empty state message that describes in detail why there is no content to display';
      const wrapper = mount(EmptyState, {
        props: {
          message: longMessage,
        },
      });

      expect(wrapper.find('.empty-message').text()).toBe(longMessage);
    });

    it('should handle special characters in messages', () => {
      const specialMessage = 'No results for "query" & <tag>';
      const wrapper = mount(EmptyState, {
        props: {
          message: specialMessage,
        },
      });

      // Vue escapes HTML by default
      expect(wrapper.find('.empty-message').text()).toBe(specialMessage);
    });
  });

  describe('overlay mode', () => {
    it('should render as overlay', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No content',
          overlay: true,
        },
      });

      const container = wrapper.find('.empty-state');
      expect(container.classes()).toContain('overlay');
    });

    it('should render as non-overlay', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No content',
          overlay: false,
        },
      });

      const container = wrapper.find('.empty-state');
      expect(container.classes()).not.toContain('overlay');
    });
  });

  describe('visual states', () => {
    it('should render minimal state (message only)', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'Nothing here',
        },
      });

      const html = wrapper.html();
      expect(html).toContain('Nothing here');
      expect(wrapper.find('.empty-icon').exists()).toBe(false);
    });

    it('should render with icon', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No files',
          icon: 'file',
        },
      });

      expect(wrapper.findComponent(FileText).exists()).toBe(true);
      expect(wrapper.find('.empty-message').text()).toBe('No files');
    });

    it('should render with icon and action', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No data',
          icon: 'inbox',
        },
        slots: {
          action: '<button>Load Data</button>',
        },
      });

      expect(wrapper.findComponent(Inbox).exists()).toBe(true);
      expect(wrapper.find('.empty-message').text()).toBe('No data');
      expect(wrapper.find('button').text()).toBe('Load Data');
    });

    it('should render full state (overlay + icon + message + action)', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No results found',
          icon: 'search',
          overlay: true,
        },
        slots: {
          action: '<button>Try Again</button>',
        },
      });

      expect(wrapper.find('.empty-state.overlay').exists()).toBe(true);
      expect(wrapper.findComponent(Search).exists()).toBe(true);
      expect(wrapper.find('.empty-message').text()).toBe('No results found');
      expect(wrapper.find('button').text()).toBe('Try Again');
    });
  });

  describe('accessibility', () => {
    it('should have proper DOM structure for screen readers', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No content available',
        },
      });

      const root = wrapper.find('.empty-state');
      expect(root.exists()).toBe(true);

      // Check that message content is accessible
      expect(wrapper.text()).toContain('No content available');
    });

    it('should render icons with proper semantic meaning', () => {
      const wrapper = mount(EmptyState, {
        props: {
          message: 'No files',
          icon: 'file',
        },
      });

      // lucide-vue-next icons are SVG components
      const icon = wrapper.findComponent(FileText);
      expect(icon.exists()).toBe(true);
    });
  });
});
