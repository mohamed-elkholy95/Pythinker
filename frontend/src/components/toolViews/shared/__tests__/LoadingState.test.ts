import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LoadingState from '../LoadingState.vue';
import LoadingDots from '../LoadingDots.vue';
import GlobeAnimation from '../animations/GlobeAnimation.vue';
import SearchAnimation from '../animations/SearchAnimation.vue';
import FileAnimation from '../animations/FileAnimation.vue';
import TerminalAnimation from '../animations/TerminalAnimation.vue';
import CodeAnimation from '../animations/CodeAnimation.vue';
import SpinnerAnimation from '../animations/SpinnerAnimation.vue';
import CheckAnimation from '../animations/CheckAnimation.vue';

describe('LoadingState.vue', () => {
  describe('rendering', () => {
    it('should render with default props', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.text()).toContain('Loading');
      expect(wrapper.findComponent(LoadingDots).exists()).toBe(true);
    });

    it('should render label text', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Fetching data',
        },
      });

      expect(wrapper.find('.loading-label').text()).toBe('Fetching data');
    });

    it('should render detail when provided', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          detail: 'Please wait...',
        },
      });

      expect(wrapper.find('.loading-detail').text()).toBe('Please wait...');
    });

    it('should not render detail when not provided', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.find('.loading-detail').exists()).toBe(false);
    });

    it('should render loading dots when isActive is true', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          isActive: true,
        },
      });

      expect(wrapper.findComponent(LoadingDots).exists()).toBe(true);
    });

    it('should not render loading dots when isActive is false', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          isActive: false,
        },
      });

      expect(wrapper.findComponent(LoadingDots).exists()).toBe(false);
    });
  });

  describe('animation selection', () => {
    it('should render globe animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          animation: 'globe',
        },
      });

      expect(wrapper.findComponent(GlobeAnimation).exists()).toBe(true);
    });

    it('should render search animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Searching',
          animation: 'search',
        },
      });

      expect(wrapper.findComponent(SearchAnimation).exists()).toBe(true);
    });

    it('should render file animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading file',
          animation: 'file',
        },
      });

      expect(wrapper.findComponent(FileAnimation).exists()).toBe(true);
    });

    it('should render terminal animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Executing',
          animation: 'terminal',
        },
      });

      expect(wrapper.findComponent(TerminalAnimation).exists()).toBe(true);
    });

    it('should render code animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Running code',
          animation: 'code',
        },
      });

      expect(wrapper.findComponent(CodeAnimation).exists()).toBe(true);
    });

    it('should render check animation', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Complete',
          animation: 'check',
        },
      });

      expect(wrapper.findComponent(CheckAnimation).exists()).toBe(true);
    });

    it('should render spinner animation by default', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.findComponent(SpinnerAnimation).exists()).toBe(true);
    });

    it('should render spinner animation when animation is "spinner"', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          animation: 'spinner',
        },
      });

      expect(wrapper.findComponent(SpinnerAnimation).exists()).toBe(true);
    });
  });

  describe('props interface', () => {
    it('should accept all valid LoadingStateProps', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Custom Label',
          detail: 'Custom Detail',
          animation: 'globe',
          isActive: false,
        },
      });

      expect(wrapper.find('.loading-label').text()).toBe('Custom Label');
      expect(wrapper.find('.loading-detail').text()).toBe('Custom Detail');
      expect(wrapper.findComponent(GlobeAnimation).exists()).toBe(true);
      expect(wrapper.findComponent(LoadingDots).exists()).toBe(false);
    });
  });

  describe('structure and classes', () => {
    it('should have correct root class', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.find('.loading-state').exists()).toBe(true);
    });

    it('should have loading animation container', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.find('.loading-animation').exists()).toBe(true);
    });

    it('should have loading text container', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.find('.loading-text').exists()).toBe(true);
    });
  });

  describe('accessibility', () => {
    it('should have proper DOM structure for screen readers', () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading content',
          detail: 'Please wait',
        },
      });

      const root = wrapper.find('.loading-state');
      expect(root.exists()).toBe(true);

      // Check that text content is accessible
      expect(wrapper.text()).toContain('Loading content');
      expect(wrapper.text()).toContain('Please wait');
    });
  });

  describe('responsive behavior', () => {
    it('should handle long labels gracefully', () => {
      const longLabel = 'This is a very long loading label that might overflow in some layouts';
      const wrapper = mount(LoadingState, {
        props: {
          label: longLabel,
        },
      });

      expect(wrapper.find('.loading-label').text()).toBe(longLabel);
    });

    it('should handle long details with truncation class', () => {
      const longDetail = 'This is a very long detail text that should be truncated with ellipsis';
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          detail: longDetail,
        },
      });

      const detailEl = wrapper.find('.loading-detail');
      expect(detailEl.text()).toBe(longDetail);
      // Component has overflow and text-overflow CSS for truncation
    });
  });

  describe('prop updates', () => {
    it('should update when label changes', async () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Initial',
        },
      });

      expect(wrapper.find('.loading-label').text()).toBe('Initial');

      await wrapper.setProps({ label: 'Updated' });

      expect(wrapper.find('.loading-label').text()).toBe('Updated');
    });

    it('should update when animation changes', async () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          animation: 'spinner',
        },
      });

      expect(wrapper.findComponent(SpinnerAnimation).exists()).toBe(true);

      await wrapper.setProps({ animation: 'globe' });

      expect(wrapper.findComponent(SpinnerAnimation).exists()).toBe(false);
      expect(wrapper.findComponent(GlobeAnimation).exists()).toBe(true);
    });

    it('should show/hide detail when prop changes', async () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
        },
      });

      expect(wrapper.find('.loading-detail').exists()).toBe(false);

      await wrapper.setProps({ detail: 'New detail' });

      expect(wrapper.find('.loading-detail').exists()).toBe(true);
      expect(wrapper.find('.loading-detail').text()).toBe('New detail');

      await wrapper.setProps({ detail: undefined });

      expect(wrapper.find('.loading-detail').exists()).toBe(false);
    });

    it('should show/hide loading dots when isActive changes', async () => {
      const wrapper = mount(LoadingState, {
        props: {
          label: 'Loading',
          isActive: true,
        },
      });

      expect(wrapper.findComponent(LoadingDots).exists()).toBe(true);

      await wrapper.setProps({ isActive: false });

      expect(wrapper.findComponent(LoadingDots).exists()).toBe(false);

      await wrapper.setProps({ isActive: true });

      expect(wrapper.findComponent(LoadingDots).exists()).toBe(true);
    });
  });
});
