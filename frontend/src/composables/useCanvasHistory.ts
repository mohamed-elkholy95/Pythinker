/**
 * Canvas undo/redo history composable.
 * Uses JSON snapshots for deep state capture.
 *
 * State is scoped per-instance to prevent cross-session leakage.
 */
import { ref, computed, onScopeDispose } from 'vue'
import type { CanvasPage } from '@/types/canvas'

const MAX_HISTORY = 100

export function useCanvasHistory() {
  // Instance-scoped stacks (was previously module-level — caused C1 bug)
  const undoStack = ref<string[]>([])
  const redoStack = ref<string[]>([])

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function pushState(pages: CanvasPage[]) {
    const snapshot = JSON.stringify(pages)
    undoStack.value = [...undoStack.value.slice(-(MAX_HISTORY - 1)), snapshot]
    redoStack.value = []
  }

  function undo(currentPages: CanvasPage[]): CanvasPage[] | null {
    if (undoStack.value.length === 0) return null
    const currentSnapshot = JSON.stringify(currentPages)
    redoStack.value = [...redoStack.value, currentSnapshot]
    const previous = undoStack.value[undoStack.value.length - 1]
    undoStack.value = undoStack.value.slice(0, -1)
    return JSON.parse(previous) as CanvasPage[]
  }

  function redo(currentPages: CanvasPage[]): CanvasPage[] | null {
    if (redoStack.value.length === 0) return null
    const currentSnapshot = JSON.stringify(currentPages)
    undoStack.value = [...undoStack.value, currentSnapshot]
    const next = redoStack.value[redoStack.value.length - 1]
    redoStack.value = redoStack.value.slice(0, -1)
    return JSON.parse(next) as CanvasPage[]
  }

  function clear() {
    undoStack.value = []
    redoStack.value = []
  }

  // Auto-cleanup on scope dispose
  onScopeDispose(clear)

  return { canUndo, canRedo, pushState, undo, redo, clear }
}
