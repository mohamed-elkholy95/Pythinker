import { computed, defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import SandboxViewer from '@/components/SandboxViewer.vue'

vi.mock('@/api/agent', () => ({
  getScreencastUrl: vi.fn().mockResolvedValue('ws://mock-screencast'),
  getInputStreamUrl: vi.fn().mockResolvedValue('ws://mock-input'),
}))

vi.mock('@/composables/useSandboxInput', () => ({
  useSandboxInput: () => ({
    isForwarding: ref(false),
    startForwarding: vi.fn(),
    stopForwarding: vi.fn(),
    attachInputListeners: vi.fn(() => () => {}),
  }),
}))

vi.mock('@/composables/useWideResearch', () => ({
  useWideResearchGlobal: () => ({
    overlayState: ref(null),
    isActive: ref(false),
  }),
}))

vi.mock('@/composables/useSkillEvents', () => ({
  useSkillEvents: () => ({
    activeSkillList: computed(() => []),
    handleSkillEvent: vi.fn(),
    reset: vi.fn(),
  }),
}))

const KonvaLiveStageStub = defineComponent({
  name: 'KonvaLiveStage',
  props: {
    enabled: { type: Boolean, required: true },
    showStats: { type: Boolean, default: false },
    showAgentActions: { type: Boolean, default: true },
    hideLocalCursor: { type: Boolean, default: false },
  },
  setup(_props, { expose }) {
    expose({
      pushFrame: vi.fn(),
      startStats: vi.fn(),
      stopStats: vi.fn(),
      resetScreencast: vi.fn(),
      forceDimensionReset: vi.fn(),
      processToolEvent: vi.fn(),
    })
    return {}
  },
  template: '<div class="konva-live-stage-stub" v-bind="$attrs"></div>',
})

describe('SandboxViewer', () => {
  it('hides browser-side cursor artifacts in passive view-only mode', async () => {
    const wrapper = mount(SandboxViewer, {
      props: {
        sessionId: 'session-1',
        enabled: true,
        viewOnly: true,
      },
      global: {
        stubs: {
          KonvaLiveStage: KonvaLiveStageStub,
          LoadingState: true,
          InactiveState: true,
          WideResearchOverlay: true,
          BrowserInteractionOverlay: true,
        },
      },
    })

    await flushPromises()

    const content = wrapper.get('.sandbox-content-inner')
    expect(content.attributes('style')).toContain('cursor: none')

    const liveStage = wrapper.getComponent(KonvaLiveStageStub)
    expect(liveStage.props('showAgentActions')).toBe(false)
    expect(liveStage.props('hideLocalCursor')).toBe(true)
    expect(liveStage.attributes('show-agent-cursor')).toBeUndefined()

    expect(wrapper.findComponent({ name: 'BrowserInteractionOverlay' }).exists()).toBe(false)
  })
})
