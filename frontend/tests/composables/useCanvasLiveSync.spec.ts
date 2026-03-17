import { nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useCanvasLiveSync } from '@/composables/useCanvasLiveSync'
import type { CanvasUpdateEventData } from '@/types/event'
import type { ToolContent } from '@/types/message'

function createToolContent(projectId = 'tool-project'): ToolContent {
  return {
    event_id: 'tool-event-1',
    timestamp: Date.now(),
    tool_call_id: 'tool-call-1',
    name: 'canvas',
    function: 'canvas_add_element',
    args: { project_id: projectId },
    content: { project_id: projectId, element_count: 1 },
    status: 'called',
  }
}

function createCanvasUpdate(
  overrides: Partial<CanvasUpdateEventData> = {},
): CanvasUpdateEventData {
  return {
    event_id: 'canvas-event-1',
    timestamp: Date.now(),
    project_id: 'live-project',
    session_id: 'session-1',
    operation: 'add_element',
    element_count: 1,
    version: 2,
    source: 'agent',
    ...overrides,
  }
}

describe('useCanvasLiveSync', () => {
  it('prefers the latest canvas update project over tool content project ids', () => {
    const toolContent = ref<ToolContent | undefined>(createToolContent('tool-project'))
    const activeCanvasUpdate = ref<CanvasUpdateEventData | null>(
      createCanvasUpdate({ project_id: 'live-project' }),
    )

    const sync = useCanvasLiveSync({ toolContent, activeCanvasUpdate })

    expect(sync.resolvedProjectId.value).toBe('live-project')
  })

  it('bumps the refresh token for repeated updates to the same project', async () => {
    const toolContent = ref<ToolContent | undefined>(createToolContent('project-1'))
    const activeCanvasUpdate = ref<CanvasUpdateEventData | null>(null)

    const sync = useCanvasLiveSync({ toolContent, activeCanvasUpdate })
    await nextTick()

    const initialToken = sync.refreshToken.value

    activeCanvasUpdate.value = createCanvasUpdate({
      event_id: 'canvas-event-1',
      project_id: 'project-1',
      version: 2,
    })
    await nextTick()

    const afterFirstUpdate = sync.refreshToken.value
    expect(afterFirstUpdate).toBeGreaterThan(initialToken)

    activeCanvasUpdate.value = createCanvasUpdate({
      event_id: 'canvas-event-2',
      project_id: 'project-1',
      version: 3,
    })
    await nextTick()

    expect(sync.refreshToken.value).toBe(afterFirstUpdate + 1)
  })

  it('does not bump the refresh token for duplicate canvas update events', async () => {
    const toolContent = ref<ToolContent | undefined>(createToolContent('project-1'))
    const activeCanvasUpdate = ref<CanvasUpdateEventData | null>(
      createCanvasUpdate({
        event_id: 'canvas-event-1',
        project_id: 'project-1',
        version: 2,
      }),
    )

    const sync = useCanvasLiveSync({ toolContent, activeCanvasUpdate })
    await nextTick()

    const firstToken = sync.refreshToken.value

    activeCanvasUpdate.value = createCanvasUpdate({
      event_id: 'canvas-event-1',
      project_id: 'project-1',
      version: 2,
      timestamp: activeCanvasUpdate.value.timestamp,
    })
    await nextTick()

    expect(sync.refreshToken.value).toBe(firstToken)
  })
})
