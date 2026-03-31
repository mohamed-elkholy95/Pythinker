import { defineComponent, nextTick, ref } from 'vue';
import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import HomePage from '@/pages/HomePage.vue';

const mockPush = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock('@/pages/ChatPage.vue', () => ({
  default: defineComponent({
    name: 'ChatPage',
    template: '<div />',
  }),
}));

vi.mock('@/components/ChatBox.vue', () => ({
  default: defineComponent({
    name: 'ChatBox',
    props: {
      modelValue: {
        type: String,
        default: '',
      },
    },
    emits: ['update:modelValue', 'submit'],
    template: '<div data-testid="chatbox-stub">{{ modelValue }}</div>',
  }),
}));

vi.mock('@/components/SimpleBar.vue', () => ({
  default: defineComponent({
    name: 'SimpleBar',
    template: '<div><slot /></div>',
  }),
}));

vi.mock('@/components/UserMenu.vue', () => ({
  default: defineComponent({
    name: 'UserMenu',
    template: '<div />',
  }),
}));

vi.mock('@/components/connectors/ConnectorsDialog.vue', () => ({
  default: defineComponent({
    name: 'ConnectorsDialog',
    template: '<div />',
  }),
}));

vi.mock('@/api/settings', () => ({
  getServerConfig: vi.fn().mockResolvedValue({
    model_name: 'test-model',
    model_display_name: 'Test Model',
  }),
  getSettings: vi.fn().mockResolvedValue({
    model_name: 'Test Model',
  }),
}));

vi.mock('@/utils/chatHeaderModel', () => ({
  resolveInitialHeaderModelName: vi.fn().mockReturnValue('Test Model'),
}));

vi.mock('@/composables/useFilePanel', () => ({
  useFilePanel: () => ({
    hideFilePanel: vi.fn(),
  }),
}));

vi.mock('@/composables/useAuth', () => ({
  useAuth: () => ({
    currentUser: ref({
      fullname: 'Anonymous User',
      email: 'anon@example.com',
    }),
  }),
}));

vi.mock('@/composables/useLeftPanel', () => ({
  useLeftPanel: () => ({
    toggleLeftPanel: vi.fn(),
  }),
}));

vi.mock('@/composables/useSettingsDialog', () => ({
  useSettingsDialog: () => ({
    openSettingsDialog: vi.fn(),
  }),
}));

vi.mock('lucide-vue-next', () => ({
  ChevronDown: defineComponent({ name: 'ChevronDown', template: '<span />' }),
  Tag: defineComponent({ name: 'Tag', template: '<span />' }),
}));

vi.mock('@/components/icons/SearchIcon.vue', () => ({
  default: defineComponent({
    name: 'SearchIcon',
    template: '<span />',
  }),
}));

vi.mock('@/components/icons/PaletteIcon.vue', () => ({
  default: defineComponent({
    name: 'PaletteIcon',
    template: '<span />',
  }),
}));

vi.mock('@/components/icons/ChatBubbleIcon.vue', () => ({
  default: defineComponent({
    name: 'ChatBubbleIcon',
    template: '<span />',
  }),
}));

describe('HomePage pending session submit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPush.mockImplementation(() => new Promise(() => {}));
  });

  it('clears the visible draft immediately while the /chat/new navigation is still pending', async () => {
    const wrapper = mount(HomePage);
    await nextTick();

    const chatBox = wrapper.findComponent({ name: 'ChatBox' });
    chatBox.vm.$emit('update:modelValue', 'draft prompt');
    await nextTick();

    expect(chatBox.props('modelValue')).toBe('draft prompt');

    chatBox.vm.$emit('submit', { thinkingMode: 'auto' });
    await nextTick();

    expect(mockPush).toHaveBeenCalledWith({
      path: '/chat/new',
      state: expect.objectContaining({
        pendingSessionCreate: true,
        message: 'draft prompt',
      }),
    });
    expect(chatBox.props('modelValue')).toBe('');
  });
});
