/**
 * Canvas export composable.
 * Export canvas as PNG, SVG, or JSON.
 */
import type { CanvasProject } from '@/types/canvas'

export function useCanvasExport() {
  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  function exportPNG(stageNode: { toDataURL: (config?: Record<string, unknown>) => string }, pixelRatio = 2) {
    const dataUrl = stageNode.toDataURL({ pixelRatio })
    const byteString = atob(dataUrl.split(',')[1])
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)
    for (let i = 0; i < byteString.length; i++) {
      ia[i] = byteString.charCodeAt(i)
    }
    const blob = new Blob([ab], { type: 'image/png' })
    downloadBlob(blob, 'canvas-export.png')
  }

  function exportJSON(project: CanvasProject) {
    const json = JSON.stringify(project, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    downloadBlob(blob, `${project.name || 'canvas'}.json`)
  }

  return { exportPNG, exportJSON, downloadBlob }
}
