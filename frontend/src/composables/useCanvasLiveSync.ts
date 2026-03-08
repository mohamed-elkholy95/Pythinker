import { computed, ref, watch, type Ref } from 'vue'

import type { CanvasUpdateEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'

interface UseCanvasLiveSyncOptions {
  toolContent: Ref<ToolContent | undefined>
  activeCanvasUpdate: Ref<CanvasUpdateEventData | null | undefined>
}

export function useCanvasLiveSync({
  toolContent,
  activeCanvasUpdate,
}: UseCanvasLiveSyncOptions) {
  const resolvedProjectId = computed(() => {
    const activeProjectId = activeCanvasUpdate.value?.project_id
    if (activeProjectId) return activeProjectId

    const content = toolContent.value?.content as Record<string, unknown> | undefined
    if (typeof content?.project_id === 'string') return content.project_id

    const argProjectId = toolContent.value?.args?.project_id
    return typeof argProjectId === 'string' ? argProjectId : ''
  })

  const refreshToken = ref(0)
  let lastCanvasEventKey = ''

  watch(
    [
      resolvedProjectId,
      () => activeCanvasUpdate.value?.event_id,
      () => activeCanvasUpdate.value?.project_id,
      () => activeCanvasUpdate.value?.version,
      () => activeCanvasUpdate.value?.timestamp,
    ],
    ([projectId, eventId, updateProjectId, version, timestamp], [previousProjectId]) => {
      if (!projectId) return

      if (projectId !== previousProjectId) {
        refreshToken.value += 1
        return
      }

      if (!activeCanvasUpdate.value || updateProjectId !== projectId) {
        return
      }

      const eventKey = eventId || `${updateProjectId}:${version ?? 'na'}:${timestamp ?? 0}`
      if (!eventKey || eventKey === lastCanvasEventKey) {
        return
      }

      lastCanvasEventKey = eventKey
      refreshToken.value += 1
    },
    { immediate: true },
  )

  const latestCanvasUpdate = computed(() => {
    const update = activeCanvasUpdate.value
    if (!update || update.project_id !== resolvedProjectId.value) {
      return null
    }
    return update
  })

  return {
    latestCanvasUpdate,
    refreshToken,
    resolvedProjectId,
  }
}
