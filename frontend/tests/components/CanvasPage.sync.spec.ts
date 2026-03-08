import { computed, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CanvasProject, CanvasRemoteSyncState, EditorState } from '@/types/canvas'

const {
  applyPendingRemoteUpdateMock,
  createProjectMock,
  dismissPendingRemoteUpdateMock,
  getSessionProjectMock,
  loadProjectMock,
  pushMock,
  replaceMock,
} = vi.hoisted(() => ({
  applyPendingRemoteUpdateMock: vi.fn(),
  createProjectMock: vi.fn(),
  dismissPendingRemoteUpdateMock: vi.fn(),
  getSessionProjectMock: vi.fn(),
  loadProjectMock: vi.fn(),
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
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
const syncStateRef = ref<CanvasRemoteSyncState>({
  sessionId: 'session-1',
  serverVersion: 2,
  pendingRemoteVersion: null,
  hasRemoteConflict: false,
  isStale: false,
  lastRemoteOperation: null,
  lastRemoteSource: null,
  lastChangedElementIds: [],
  highlightedElementIds: [],
})

function createProject(version = 2): CanvasProject {
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
        elements: [],
      },
    ],
    width: 1280,
    height: 720,
    background: '#ffffff',
    thumbnail: null,
    version,
    created_at: '2026-03-08T12:00:00Z',
    updated_at: '2026-03-08T12:00:00Z',
  }
}

projectRef.value = createProject()

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return {
    ...actual,
    useRoute: () => ({
      params: { projectId: 'project-1' },
      query: { sessionId: 'session-1' },
    }),
    useRouter: () => ({
      push: pushMock,
      replace: replaceMock,
    }),
  }
})

vi.mock('@/composables/useCanvasEditor', () => ({
  useCanvasEditor: () => ({
    project: projectRef,
    editorState: editorStateRef,
    syncState: syncStateRef,
    loading: ref(false),
    saving: ref(false),
    activePage: computed(() => projectRef.value?.pages[0] ?? null),
    elements: computed(() => projectRef.value?.pages[0]?.elements ?? []),
    selectedElements: computed(() => []),
    loadProject: loadProjectMock,
    createProject: createProjectMock,
    saveProject: vi.fn(),
    markDirty: vi.fn(),
    addElement: vi.fn(),
    updateElement: vi.fn(),
    deleteElements: vi.fn(),
    selectElement: vi.fn(),
    clearSelection: vi.fn(),
    selectAll: vi.fn(),
    setTool: vi.fn(),
    setZoom: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    resetZoom: vi.fn(),
    setPan: vi.fn(),
    bringToFront: vi.fn(),
    sendToBack: vi.fn(),
    syncFromRemoteUpdate: vi.fn(),
    applyPendingRemoteUpdate: applyPendingRemoteUpdateMock,
    dismissPendingRemoteUpdate: dismissPendingRemoteUpdateMock,
    clearRemoteHighlight: vi.fn(),
  }),
}))

vi.mock('@/composables/useCanvasHistory', () => ({
  useCanvasHistory: () => ({
    canUndo: computed(() => false),
    canRedo: computed(() => false),
    pushState: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    clear: vi.fn(),
  }),
}))

vi.mock('@/composables/useCanvasExport', () => ({
  useCanvasExport: () => ({
    exportPNG: vi.fn(),
    exportJSON: vi.fn(),
  }),
}))

vi.mock('@/api/canvas', () => ({
  getSessionProject: getSessionProjectMock,
}))

import CanvasPage from '@/pages/CanvasPage.vue'

const mountCanvasPage = () =>
  mount(CanvasPage, {
    global: {
      stubs: {
        CanvasStage: { template: '<div data-testid="canvas-stage" />' },
        CanvasToolbar: { template: '<div data-testid="canvas-toolbar" />' },
        CanvasPropertyPanel: { template: '<div data-testid="canvas-property-panel" />' },
        CanvasLayerPanel: { template: '<div data-testid="canvas-layer-panel" />' },
        CanvasAIPanel: { template: '<div data-testid="canvas-ai-panel" />' },
        CanvasZoomControls: { template: '<div data-testid="canvas-zoom-controls" />' },
        CanvasExportDialog: { template: '<div data-testid="canvas-export-dialog" />' },
      },
    },
  })

describe('CanvasPage sync UX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    projectRef.value = createProject()
    editorStateRef.value = {
      activeTool: 'select',
      activePageIndex: 0,
      selectedElementIds: [],
      zoom: 1,
      panX: 0,
      panY: 0,
      showGrid: false,
      snapEnabled: true,
      isDirty: false,
    }
    syncStateRef.value = {
      sessionId: 'session-1',
      serverVersion: 2,
      pendingRemoteVersion: null,
      hasRemoteConflict: false,
      isStale: false,
      lastRemoteOperation: null,
      lastRemoteSource: null,
      lastChangedElementIds: [],
      highlightedElementIds: [],
    }
    loadProjectMock.mockResolvedValue(undefined)
    applyPendingRemoteUpdateMock.mockResolvedValue(true)
    dismissPendingRemoteUpdateMock.mockReturnValue(undefined)
    getSessionProjectMock.mockResolvedValue(createProject())
  })

  it('shows a conflict banner and routes banner actions to the editor sync methods', async () => {
    editorStateRef.value.isDirty = true
    syncStateRef.value = {
      ...syncStateRef.value,
      pendingRemoteVersion: 5,
      hasRemoteConflict: true,
      lastRemoteOperation: 'Updated callout block',
      lastRemoteSource: 'agent',
    }

    const wrapper = mountCanvasPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Agent updated this canvas')
    expect(wrapper.text()).toContain('Apply latest')
    expect(wrapper.text()).toContain('Keep my draft')

    await wrapper.get('[data-testid="canvas-sync-primary"]').trigger('click')
    await wrapper.get('[data-testid="canvas-sync-secondary"]').trigger('click')

    expect(applyPendingRemoteUpdateMock).toHaveBeenCalledTimes(1)
    expect(dismissPendingRemoteUpdateMock).toHaveBeenCalledTimes(1)
  })

  it('shows the stale banner state after the remote update was dismissed', async () => {
    editorStateRef.value.isDirty = true
    syncStateRef.value = {
      ...syncStateRef.value,
      pendingRemoteVersion: 4,
      isStale: true,
      lastRemoteOperation: 'Adjusted background color',
      lastRemoteSource: 'agent',
    }

    const wrapper = mountCanvasPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Your draft is behind the latest agent canvas')
    expect(wrapper.text()).toContain('Reload canvas')
  })
})
