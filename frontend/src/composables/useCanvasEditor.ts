/**
 * Core canvas editor composable.
 * Manages project state, element CRUD, zoom/pan, and auto-save.
 *
 * State is scoped per-instance to prevent cross-session leakage.
 * Call dispose() or rely on onScopeDispose to clean up timers.
 */
import { ref, computed, onScopeDispose } from 'vue'
import type {
  CanvasProject,
  CanvasElement,
  EditorState,
  EditorTool,
  CanvasRemoteSyncState,
} from '@/types/canvas'
import type { CanvasUpdateEventData } from '@/types/event'
import * as canvasApi from '@/api/canvas'

export function useCanvasEditor() {
  // ---------------------------------------------------------------------------
  // Instance-scoped state (was previously module-level — caused C1 bug)
  // ---------------------------------------------------------------------------

  const project = ref<CanvasProject | null>(null)
  const editorState = ref<EditorState>({
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
  const loading = ref(false)
  const saving = ref(false)
  const syncState = ref<CanvasRemoteSyncState>({
    sessionId: null,
    serverVersion: 0,
    pendingRemoteVersion: null,
    hasRemoteConflict: false,
    isStale: false,
    lastRemoteOperation: null,
    lastRemoteSource: null,
    lastChangedElementIds: [],
    highlightedElementIds: [],
  })

  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
  let remoteHighlightTimer: ReturnType<typeof setTimeout> | null = null

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const activePage = computed(() => {
    if (!project.value) return null
    return project.value.pages[editorState.value.activePageIndex] ?? null
  })

  const elements = computed(() => activePage.value?.elements ?? [])

  const selectedElements = computed(() => {
    const ids = new Set(editorState.value.selectedElementIds)
    return elements.value.filter((el) => ids.has(el.id))
  })

  function clearRemoteHighlight() {
    if (remoteHighlightTimer) {
      clearTimeout(remoteHighlightTimer)
      remoteHighlightTimer = null
    }
    syncState.value.highlightedElementIds = []
  }

  function setHighlightedElements(elementIds?: string[] | null) {
    clearRemoteHighlight()
    const nextIds = (elementIds ?? []).filter((elementId): elementId is string => Boolean(elementId))
    syncState.value.highlightedElementIds = nextIds
    if (nextIds.length === 0) {
      return
    }
    remoteHighlightTimer = setTimeout(() => {
      syncState.value.highlightedElementIds = []
      remoteHighlightTimer = null
    }, 1800)
  }

  function resetRemoteSyncState() {
    syncState.value.pendingRemoteVersion = null
    syncState.value.hasRemoteConflict = false
    syncState.value.isStale = false
  }

  function syncProjectMetadata(nextProject: CanvasProject) {
    syncState.value.sessionId = nextProject.session_id
    syncState.value.serverVersion = nextProject.version
  }

  function applyProjectSnapshot(
    nextProject: CanvasProject,
    update?: Partial<CanvasUpdateEventData>,
  ) {
    project.value = nextProject
    editorState.value.activePageIndex = Math.min(
      editorState.value.activePageIndex,
      Math.max(nextProject.pages.length - 1, 0),
    )
    editorState.value.selectedElementIds = []
    editorState.value.isDirty = false
    syncProjectMetadata(nextProject)
    syncState.value.lastRemoteOperation = update?.operation ?? syncState.value.lastRemoteOperation
    syncState.value.lastRemoteSource = update?.source ?? syncState.value.lastRemoteSource
    syncState.value.lastChangedElementIds = [...(update?.changed_element_ids ?? [])]
    resetRemoteSyncState()
    setHighlightedElements(update?.changed_element_ids ?? [])
  }

  function buildRemoteUpdateFromProject(
    nextProject: CanvasProject,
    update?: Partial<CanvasUpdateEventData>,
  ): CanvasUpdateEventData {
    const firstPage = nextProject.pages[0]
    return {
      event_id: update?.event_id ?? `canvas-project-${nextProject.id}-${nextProject.version}`,
      timestamp: update?.timestamp ?? Date.now(),
      project_id: nextProject.id,
      session_id: update?.session_id ?? nextProject.session_id ?? undefined,
      operation: update?.operation ?? 'sync_project',
      element_count: update?.element_count ?? firstPage?.elements.length ?? 0,
      project_name: update?.project_name ?? nextProject.name,
      version: update?.version ?? nextProject.version,
      changed_element_ids: update?.changed_element_ids,
      source: update?.source,
    }
  }

  // ---------------------------------------------------------------------------
  // Project CRUD
  // ---------------------------------------------------------------------------

  async function loadProject(projectId: string) {
    loading.value = true
    try {
      const loadedProject = await canvasApi.getProject(projectId)
      project.value = loadedProject
      editorState.value.activePageIndex = 0
      editorState.value.selectedElementIds = []
      editorState.value.isDirty = false
      syncProjectMetadata(loadedProject)
      resetRemoteSyncState()
      syncState.value.lastChangedElementIds = []
      clearRemoteHighlight()
    } finally {
      loading.value = false
    }
  }

  async function createProject(
    name?: string,
    width?: number,
    height?: number,
    options?: { sessionId?: string },
  ) {
    loading.value = true
    try {
      project.value = await canvasApi.createProject({
        name,
        width,
        height,
        session_id: options?.sessionId,
      })
      editorState.value.activePageIndex = 0
      editorState.value.isDirty = false
      if (project.value) {
        syncProjectMetadata(project.value)
      }
      resetRemoteSyncState()
      syncState.value.lastChangedElementIds = []
      clearRemoteHighlight()
      return project.value
    } finally {
      loading.value = false
    }
  }

  async function saveProject() {
    if (!project.value || !editorState.value.isDirty) return
    saving.value = true
    try {
      const updated = await canvasApi.updateProject(project.value.id, {
        name: project.value.name,
        pages: project.value.pages.map((p) => ({ ...p })) as Record<string, unknown>[],
        width: project.value.width,
        height: project.value.height,
        background: project.value.background,
      })
      project.value = updated
      editorState.value.isDirty = false
      syncProjectMetadata(updated)
      resetRemoteSyncState()
      syncState.value.lastChangedElementIds = []
    } finally {
      saving.value = false
    }
  }

  function scheduleAutoSave() {
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(() => {
      saveProject()
    }, 3000)
  }

  function markDirty() {
    editorState.value.isDirty = true
    scheduleAutoSave()
  }

  async function syncFromRemoteUpdate(
    update: CanvasUpdateEventData,
    resolver?: () => Promise<CanvasProject>,
  ): Promise<'ignored' | 'queued' | 'applied'> {
    if (!project.value) return 'ignored'
    if (update.project_id !== project.value.id) return 'ignored'

    const knownVersion = Math.max(
      syncState.value.serverVersion,
      syncState.value.pendingRemoteVersion ?? 0,
    )
    if (update.version <= knownVersion) {
      return 'ignored'
    }

    syncState.value.sessionId = update.session_id ?? syncState.value.sessionId
    syncState.value.lastRemoteOperation = update.operation
    syncState.value.lastRemoteSource = update.source ?? null
    syncState.value.lastChangedElementIds = [...(update.changed_element_ids ?? [])]

    if (editorState.value.isDirty) {
      syncState.value.pendingRemoteVersion = update.version
      syncState.value.hasRemoteConflict = true
      syncState.value.isStale = false
      return 'queued'
    }

    const remoteProject = resolver
      ? await resolver()
      : await canvasApi.getProject(update.project_id)
    applyProjectSnapshot(remoteProject, update)
    return 'applied'
  }

  async function syncFromRemoteProject(
    remoteProject: CanvasProject,
    update?: Partial<CanvasUpdateEventData>,
  ): Promise<'ignored' | 'queued' | 'applied'> {
    const remoteUpdate = buildRemoteUpdateFromProject(remoteProject, update)
    if (!project.value) {
      applyProjectSnapshot(remoteProject, remoteUpdate)
      return 'applied'
    }
    return syncFromRemoteUpdate(remoteUpdate, async () => remoteProject)
  }

  async function applyPendingRemoteUpdate(
    resolver?: () => Promise<CanvasProject>,
  ): Promise<boolean> {
    if (!project.value || syncState.value.pendingRemoteVersion === null) {
      return false
    }

    const remoteProject = resolver
      ? await resolver()
      : await canvasApi.getProject(project.value.id)
    applyProjectSnapshot(remoteProject, {
      project_id: remoteProject.id,
      session_id: syncState.value.sessionId ?? remoteProject.session_id ?? undefined,
      operation: syncState.value.lastRemoteOperation ?? 'sync_project',
      element_count: remoteProject.pages[0]?.elements.length ?? 0,
      project_name: remoteProject.name,
      version: remoteProject.version,
      changed_element_ids: syncState.value.lastChangedElementIds,
      source: syncState.value.lastRemoteSource ?? undefined,
    })
    return true
  }

  function dismissPendingRemoteUpdate() {
    if (syncState.value.pendingRemoteVersion === null) {
      return
    }
    syncState.value.hasRemoteConflict = false
    syncState.value.isStale = true
  }

  // ---------------------------------------------------------------------------
  // Element operations
  // ---------------------------------------------------------------------------

  function addElement(element: CanvasElement) {
    if (!project.value || !activePage.value) return
    activePage.value.elements.push(element)
    markDirty()
  }

  function updateElement(elementId: string, updates: Partial<CanvasElement>) {
    if (!activePage.value) return
    const idx = activePage.value.elements.findIndex((el) => el.id === elementId)
    if (idx === -1) return
    Object.assign(activePage.value.elements[idx], updates)
    markDirty()
  }

  function deleteElements(elementIds: string[]) {
    if (!activePage.value) return
    const ids = new Set(elementIds)
    activePage.value.elements = activePage.value.elements.filter(
      (el) => !ids.has(el.id),
    )
    editorState.value.selectedElementIds = editorState.value.selectedElementIds.filter(
      (id) => !ids.has(id),
    )
    markDirty()
  }

  // ---------------------------------------------------------------------------
  // Selection
  // ---------------------------------------------------------------------------

  function selectElement(elementId: string, multi = false) {
    if (multi) {
      const idx = editorState.value.selectedElementIds.indexOf(elementId)
      if (idx >= 0) {
        editorState.value.selectedElementIds.splice(idx, 1)
      } else {
        editorState.value.selectedElementIds.push(elementId)
      }
    } else {
      editorState.value.selectedElementIds = [elementId]
    }
  }

  function clearSelection() {
    editorState.value.selectedElementIds = []
  }

  function selectAll() {
    if (!activePage.value) return
    editorState.value.selectedElementIds = activePage.value.elements.map((el) => el.id)
  }

  // ---------------------------------------------------------------------------
  // Tool
  // ---------------------------------------------------------------------------

  function setTool(tool: EditorTool) {
    editorState.value.activeTool = tool
  }

  // ---------------------------------------------------------------------------
  // Zoom / Pan
  // ---------------------------------------------------------------------------

  function setZoom(zoom: number) {
    editorState.value.zoom = Math.max(0.1, Math.min(zoom, 5))
  }

  function zoomIn() {
    setZoom(editorState.value.zoom * 1.2)
  }

  function zoomOut() {
    setZoom(editorState.value.zoom / 1.2)
  }

  function resetZoom() {
    editorState.value.zoom = 1
    editorState.value.panX = 0
    editorState.value.panY = 0
  }

  function setPan(x: number, y: number) {
    editorState.value.panX = x
    editorState.value.panY = y
  }

  // ---------------------------------------------------------------------------
  // Layer ordering
  // ---------------------------------------------------------------------------

  function bringToFront(elementId: string) {
    if (!activePage.value) return
    const maxZ = Math.max(...activePage.value.elements.map((el) => el.z_index), 0)
    updateElement(elementId, { z_index: maxZ + 1 })
  }

  function sendToBack(elementId: string) {
    if (!activePage.value) return
    const minZ = Math.min(...activePage.value.elements.map((el) => el.z_index), 0)
    updateElement(elementId, { z_index: minZ - 1 })
  }

  // ---------------------------------------------------------------------------
  // Cleanup
  // ---------------------------------------------------------------------------

  function dispose() {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
    clearRemoteHighlight()
  }

  // Auto-cleanup when the effect scope is disposed (component unmount)
  onScopeDispose(dispose)

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    project,
    editorState,
    syncState,
    loading,
    saving,
    activePage,
    elements,
    selectedElements,
    loadProject,
    createProject,
    saveProject,
    syncFromRemoteUpdate,
    syncFromRemoteProject,
    applyPendingRemoteUpdate,
    dismissPendingRemoteUpdate,
    clearRemoteHighlight,
    markDirty,
    addElement,
    updateElement,
    deleteElements,
    selectElement,
    clearSelection,
    selectAll,
    setTool,
    setZoom,
    zoomIn,
    zoomOut,
    resetZoom,
    setPan,
    bringToFront,
    sendToBack,
    dispose,
  }
}
