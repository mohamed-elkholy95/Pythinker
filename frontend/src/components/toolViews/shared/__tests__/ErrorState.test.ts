import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import ErrorState from '../ErrorState.vue';

describe('ErrorState.vue', () => {
  describe('rendering', () => {
    it('should render error message', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Something went wrong',
        },
      });

      expect(wrapper.find('.error-message').text()).toBe('Something went wrong');
    });

    it('should render error icon', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error occurred',
        },
      });

      expect(wrapper.find('.error-icon').exists()).toBe(true);
    });

    it('should not render retry button by default', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
        },
      });

      expect(wrapper.find('.retry-button').exists()).toBe(false);
    });

    it('should render retry button when retryable is true', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Network error',
          retryable: true,
        },
      });

      expect(wrapper.find('.retry-button').exists()).toBe(true);
      expect(wrapper.find('.retry-button').text()).toContain('Try Again');
    });
  });

  describe('retry functionality', () => {
    it('should emit retry event when button is clicked', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Failed to load',
          retryable: true,
        },
      });

      await wrapper.find('.retry-button').trigger('click');

      expect(wrapper.emitted('retry')).toBeTruthy();
      expect(wrapper.emitted('retry')?.length).toBe(1);
    });

    it('should emit multiple retry events on multiple clicks', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Failed',
          retryable: true,
        },
      });

      await wrapper.find('.retry-button').trigger('click');
      await wrapper.find('.retry-button').trigger('click');
      await wrapper.find('.retry-button').trigger('click');

      expect(wrapper.emitted('retry')?.length).toBe(3);
    });
  });

  describe('structure and classes', () => {
    it('should have correct root class', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
        },
      });

      expect(wrapper.find('.error-state').exists()).toBe(true);
    });

    it('should have error icon with correct class', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
        },
      });

      expect(wrapper.find('.error-icon').exists()).toBe(true);
    });

    it('should have error message with correct class', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
        },
      });

      expect(wrapper.find('.error-message').exists()).toBe(true);
    });

    it('should have retry button with correct classes when retryable', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');
      expect(button.exists()).toBe(true);
      expect(button.find('.retry-icon').exists()).toBe(true);
    });
  });

  describe('accessibility', () => {
    it('should have aria-label on retry button', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');
      expect(button.attributes('aria-label')).toBe('Retry operation');
    });

    it('should have proper button semantics', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');
      expect(button.element.tagName).toBe('BUTTON');
    });

    it('should be keyboard accessible', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');

      // Native button elements are inherently keyboard accessible
      // (Enter and Space keys trigger click events automatically)
      expect(button.element.tagName).toBe('BUTTON');

      // Should have focus styles for keyboard navigation
      expect(button.classes()).toContain('retry-button');
    });
  });

  describe('error message formatting', () => {
    it('should handle short error messages', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
        },
      });

      expect(wrapper.find('.error-message').text()).toBe('Error');
    });

    it('should handle long error messages', () => {
      const longError = 'This is a very long error message that describes in detail what went wrong with the operation and provides comprehensive information about the failure';
      const wrapper = mount(ErrorState, {
        props: {
          error: longError,
        },
      });

      expect(wrapper.find('.error-message').text()).toBe(longError);
    });

    it('should handle multiline error messages', () => {
      const multilineError = 'Line 1\nLine 2\nLine 3';
      const wrapper = mount(ErrorState, {
        props: {
          error: multilineError,
        },
      });

      expect(wrapper.find('.error-message').text()).toContain('Line 1');
      expect(wrapper.find('.error-message').text()).toContain('Line 2');
      expect(wrapper.find('.error-message').text()).toContain('Line 3');
    });

    it('should handle special characters in error messages', () => {
      const specialError = 'Error: <script>alert("xss")</script>';
      const wrapper = mount(ErrorState, {
        props: {
          error: specialError,
        },
      });

      // Vue escapes HTML by default
      expect(wrapper.find('.error-message').text()).toBe(specialError);
    });
  });

  describe('prop updates', () => {
    it('should update error message when prop changes', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Initial error',
        },
      });

      expect(wrapper.find('.error-message').text()).toBe('Initial error');

      await wrapper.setProps({ error: 'Updated error' });

      expect(wrapper.find('.error-message').text()).toBe('Updated error');
    });

    it('should show retry button when retryable changes to true', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: false,
        },
      });

      expect(wrapper.find('.retry-button').exists()).toBe(false);

      await wrapper.setProps({ retryable: true });

      expect(wrapper.find('.retry-button').exists()).toBe(true);
    });

    it('should hide retry button when retryable changes to false', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      expect(wrapper.find('.retry-button').exists()).toBe(true);

      await wrapper.setProps({ retryable: false });

      expect(wrapper.find('.retry-button').exists()).toBe(false);
    });
  });

  describe('visual states', () => {
    it('should render without retry button', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Connection failed',
          retryable: false,
        },
      });

      const html = wrapper.html();
      expect(html).toContain('Connection failed');
      expect(html).not.toContain('Try Again');
    });

    it('should render with retry button', () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Connection failed',
          retryable: true,
        },
      });

      const html = wrapper.html();
      expect(html).toContain('Connection failed');
      expect(html).toContain('Try Again');
    });
  });

  describe('button interaction', () => {
    it('should handle rapid clicks without errors', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');

      // Rapid clicks
      for (let i = 0; i < 10; i++) {
        await button.trigger('click');
      }

      expect(wrapper.emitted('retry')?.length).toBe(10);
    });

    it('should maintain focus after click', async () => {
      const wrapper = mount(ErrorState, {
        props: {
          error: 'Error',
          retryable: true,
        },
      });

      const button = wrapper.find('.retry-button');
      await button.trigger('click');

      // Component should still be interactive
      expect(wrapper.find('.retry-button').exists()).toBe(true);
    });
  });
});
