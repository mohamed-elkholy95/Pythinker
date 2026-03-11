import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import TimelineControls from '../TimelineControls.vue';

describe('TimelineControls', () => {
  it('keeps the current step footer visible at the live edge', () => {
    const wrapper = mount(TimelineControls, {
      props: {
        progress: 100,
        isLive: true,
        canStepForward: false,
        canStepBackward: true,
        currentStep: 4,
        totalSteps: 4,
      },
    });

    const footer = wrapper.find('.timeline-controls__step-footer');

    expect(footer.exists()).toBe(true);
    expect(footer.text()).toContain('4 / 4');
  });
});
