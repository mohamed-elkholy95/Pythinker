import { computed, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CanvasProject, EditorState } from '@/types/canvas'
import type { CanvasUpdateEventData } from '@/types/event'

const {
  loadProjectMock,
  pushMock,
} = vi.hoisted(() => ({
  loadProjectMock: vi.fn(),
  pushMock: vi.fn(),
}))

const projectRef = ref<CanvasProject | null>(null)
const editorStateRef = ref<EditorState>({
  activeTool: 'select',
  activePageIndex: 0,
  selectedElementIds: [],
  zoom: 1,
  panX: 0,
  panY: 0,
  showGrid: false,
  snapEnabled: true,
  isDirty: false,
})

function createProject(): CanvasProject {
  return {
    id: 'project-1',
    user_id: 'user-1',
    session_id: 'session-1',
    name: 'Studio Board',
    description: '',
    pages: [
      {
        id: 'page-1',
        name: 'Page 1',
        width: 1280,
        height: 720,
        background: '#ffffff',
        sort_order: 0,
        elements: [
          {
            id: 'element-1',
            type: 'rectangle',
            name: 'Card',
            x: 0,
            y: 0,
            width: 200,
            height: 120,
            rotation: 0,
            scale_x: 1,
            scale_y: 1,
            opacity: 1,
            visible: true,
            locked: false,
            z_index: 1,
            corner_radius: 0,
          },
        ],
      },
    ],
    width: 1280,
    height: 720,
    background: '#ffffff',
    thumbnail: null,
    version: 4,
    created_at: '2026-03-08T12:00:00Z',
    updated_at: '2026-03-08T12:00:00Z',
  }
}

function createCanvasUpdate(
  overrides: Partial<CanvasUpdateEventData> = {},
): CanvasUpdateEventData {
  return {
    event_id: 'canvas-update-1',
    timestamp: Date.now(),
    project_id: 'project-1',
    session_id: 'session-1',
    operation: 'modify_element',
    element_count: 1,
    project_name: 'Studio Board',
    version: 5,
    source: 'agent',
    changed_element_ids: ['element-1'],
    ...overrides,
  }
}

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRouter: () => ({
      push: pushMock,
    }),
  }
})

vi.mock('@/composables/useCanvasEditor', () => ({
  useCanvasEditor: () => ({
    project: projectRef,
    editorState: editorStateRef,
    loading: ref(false),
    activePage: computed(() => projectRef.value?.pages[0] ?? null),
    elements: computed(() => projectRef.value?.pages[0]?.elements ?? []),
    loadProject: loadProjectMock,
    updateElement: vi.fn(),
    selectElement: vi.fn(),
    clearSelection: vi.fn(),
    setTool: vi.fn(),
    setZoom: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    resetZoom: vi.fn(),
    setPan: vi.fn(),
  }),
}))

vi.mock('@/composables/useCanvasHistory', () => ({
  useCanvasHistory: () => ({
    pushState: vi.fn(),
  }),
}))

import CanvasLiveView from '@/components/toolViews/CanvasLiveView.vue'

const mountCanvasLiveView = (overrides: Record<string, unknown> = {}) =>
  mount(CanvasLiveView, {
    props: {
      sessionId: 'session-1',
      projectId: 'project-1',
      live: true,
      latestUpdate: createCanvasUpdate(),
      syncStatus: 'live',
      ...overrides,
    },
    global: {
      stubs: {
        CanvasStage: { template: '<div data-testid="canvas-stage" />' },
      },
    },
  })

describe('CanvasLiveView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    projectRef.value = createProject()
    loadProjectMock.mockResolvedValue(undefined)
  })

  it('renders project and activity metadata from the latest canvas update', async () => {
    const wrapper = mountCanvasLiveView({
      latestUpdate: createCanvasUpdate({
        operation: 'arrange_layer',
        element_count: 6,
        version: 8,
      }),
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Studio Board')
    expect(wrapper.text()).toContain('arrange layer')
    expect(wrapper.text()).toContain('v8')
    expect(wrapper.text()).toContain('6 elements')
  })

  it('opens the studio route with the linked session id', async () => {
    const wrapper = mountCanvasLiveView()
    await flushPromises()

    await wrapper.get('[data-testid="canvas-header-primary"]').trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      path: '/chat/canvas/project-1',
      query: { sessionId: 'session-1' },
    })
  })

  it('renders the conflict banner when a newer remote version is pending', async () => {
    const wrapper = mountCanvasLiveView({
      live: false,
      syncStatus: 'conflict',
      pendingRemoteVersion: 9,
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Agent updated this canvas')
    expect(wrapper.text()).toContain('Apply latest')
    expect(wrapper.text()).toContain('Keep my draft')
  })
})
