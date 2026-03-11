import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import TimelineControls from '@/components/timeline/TimelineControls.vue';

describe('TimelineControls', () => {
  it('renders the redesigned transport and scrubber framing hooks', () => {
    const wrapper = mount(TimelineControls, {
      props: {
        progress: 42,
        currentTimestamp: Date.now(),
        isLive: true,
        canStepForward: true,
        canStepBackward: true,
        currentStep: 2,
        totalSteps: 5,
      },
    });

    expect(wrapper.find('.timeline-controls__transport').exists()).toBe(true);
    expect(wrapper.find('[data-test="timeline-scrubber-frame"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="timeline-mode-badge"]').exists()).toBe(true);
  });
});
