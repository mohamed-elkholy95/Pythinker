/**
 * Canvas undo/redo history composable.
 * Uses structuredClone for deep snapshots.
 */
import { ref, computed } from 'vue'
import type { CanvasPage } from '@/types/canvas'

const MAX_HISTORY = 100

const undoStack = ref<string[]>([])
const redoStack = ref<string[]>([])

export function useCanvasHistory() {
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function pushState(pages: CanvasPage[]) {
    const snapshot = JSON.stringify(pages)
    undoStack.value.push(snapshot)
    if (undoStack.value.length > MAX_HISTORY) {
      undoStack.value.shift()
    }
    redoStack.value = []
  }

  function undo(currentPages: CanvasPage[]): CanvasPage[] | null {
    if (undoStack.value.length === 0) return null
    const currentSnapshot = JSON.stringify(currentPages)
    redoStack.value.push(currentSnapshot)
    const prev = undoStack.value.pop()!
    return JSON.parse(prev) as CanvasPage[]
  }

  function redo(currentPages: CanvasPage[]): CanvasPage[] | null {
    if (redoStack.value.length === 0) return null
    const currentSnapshot = JSON.stringify(currentPages)
    undoStack.value.push(currentSnapshot)
    const next = redoStack.value.pop()!
    return JSON.parse(next) as CanvasPage[]
  }

  function clear() {
    undoStack.value = []
    redoStack.value = []
  }

  return { canUndo, canRedo, pushState, undo, redo, clear }
}
