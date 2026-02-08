/**
 * Core canvas editor composable.
 * Manages project state, element CRUD, zoom/pan, and auto-save.
 */
import { ref, computed } from 'vue'
import type {
  CanvasProject,
  CanvasElement,
  EditorState,
  EditorTool,
} from '@/types/canvas'
import * as canvasApi from '@/api/canvas'

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

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

export function useCanvasEditor() {
  const activePage = computed(() => {
    if (!project.value) return null
    return project.value.pages[editorState.value.activePageIndex] ?? null
  })

  const elements = computed(() => activePage.value?.elements ?? [])

  const selectedElements = computed(() => {
    const ids = new Set(editorState.value.selectedElementIds)
    return elements.value.filter((el) => ids.has(el.id))
  })

  // --- Project CRUD ---
  async function loadProject(projectId: string) {
    loading.value = true
    try {
      project.value = await canvasApi.getProject(projectId)
      editorState.value.activePageIndex = 0
      editorState.value.selectedElementIds = []
      editorState.value.isDirty = false
    } finally {
      loading.value = false
    }
  }

  async function createProject(name?: string, width?: number, height?: number) {
    loading.value = true
    try {
      project.value = await canvasApi.createProject({ name, width, height })
      editorState.value.activePageIndex = 0
      editorState.value.isDirty = false
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

  // --- Element operations ---
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

  // --- Selection ---
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

  // --- Tool ---
  function setTool(tool: EditorTool) {
    editorState.value.activeTool = tool
  }

  // --- Zoom / Pan ---
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

  // --- Layer ordering ---
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

  return {
    project,
    editorState,
    loading,
    saving,
    activePage,
    elements,
    selectedElements,
    loadProject,
    createProject,
    saveProject,
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
  }
}
