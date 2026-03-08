import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CanvasProject } from '@/types/canvas'
import type { CanvasUpdateEventData } from '@/types/event'

const {
  createProjectMock,
  getProjectMock,
  updateProjectMock,
} = vi.hoisted(() => ({
  createProjectMock: vi.fn(),
  getProjectMock: vi.fn(),
  updateProjectMock: vi.fn(),
}))

vi.mock('@/api/canvas', () => ({
  createProject: createProjectMock,
  getProject: getProjectMock,
  updateProject: updateProjectMock,
}))

import { useCanvasEditor } from '@/composables/useCanvasEditor'

function createProject(version = 1): CanvasProject {
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
            x: 24,
            y: 48,
            width: 320,
            height: 200,
            rotation: 0,
            scale_x: 1,
            scale_y: 1,
            opacity: 1,
            visible: true,
            locked: false,
            z_index: 1,
            corner_radius: 24,
          },
        ],
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
    version: 2,
    changed_element_ids: ['element-1'],
    source: 'agent',
    ...overrides,
  }
}

describe('useCanvasEditor remote sync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies remote updates immediately when the editor is clean', async () => {
    const scope = effectScope()
    const initialProject = createProject(1)
    const remoteProject = createProject(2)

    getProjectMock
      .mockResolvedValueOnce(initialProject)
      .mockResolvedValueOnce(remoteProject)

    const editor = scope.run(() => useCanvasEditor())
    if (!editor) {
      throw new Error('expected useCanvasEditor to initialize')
    }

    await editor.loadProject('project-1')

    const result = await editor.syncFromRemoteUpdate(
      createCanvasUpdate({ version: 2 }),
    )

    expect(result).toBe('applied')
    expect(editor.project.value?.version).toBe(2)
    expect(editor.editorState.value.isDirty).toBe(false)
    expect(editor.syncState.value.serverVersion).toBe(2)
    expect(editor.syncState.value.pendingRemoteVersion).toBe(null)
    expect(editor.syncState.value.highlightedElementIds).toEqual(['element-1'])

    scope.stop()
  })

  it('queues remote updates while the editor has local draft changes', async () => {
    const scope = effectScope()
    const initialProject = createProject(1)
    getProjectMock.mockResolvedValue(initialProject)

    const editor = scope.run(() => useCanvasEditor())
    if (!editor) {
      throw new Error('expected useCanvasEditor to initialize')
    }

    await editor.loadProject('project-1')
    editor.markDirty()

    const result = await editor.syncFromRemoteUpdate(
      createCanvasUpdate({ version: 3, event_id: 'canvas-update-2' }),
    )

    expect(result).toBe('queued')
    expect(editor.project.value?.version).toBe(1)
    expect(editor.editorState.value.isDirty).toBe(true)
    expect(editor.syncState.value.pendingRemoteVersion).toBe(3)
    expect(editor.syncState.value.hasRemoteConflict).toBe(true)
    expect(editor.syncState.value.isStale).toBe(false)

    scope.stop()
  })

  it('applies the latest pending remote version and clears the conflict queue', async () => {
    const scope = effectScope()
    const initialProject = createProject(1)
    const remoteProject = createProject(4)

    getProjectMock
      .mockResolvedValueOnce(initialProject)
      .mockResolvedValueOnce(remoteProject)

    const editor = scope.run(() => useCanvasEditor())
    if (!editor) {
      throw new Error('expected useCanvasEditor to initialize')
    }

    await editor.loadProject('project-1')
    editor.markDirty()
    await editor.syncFromRemoteUpdate(
      createCanvasUpdate({ version: 4, event_id: 'canvas-update-3' }),
    )

    const applied = await editor.applyPendingRemoteUpdate()

    expect(applied).toBe(true)
    expect(editor.project.value?.version).toBe(4)
    expect(editor.editorState.value.isDirty).toBe(false)
    expect(editor.syncState.value.pendingRemoteVersion).toBe(null)
    expect(editor.syncState.value.hasRemoteConflict).toBe(false)
    expect(editor.syncState.value.isStale).toBe(false)

    scope.stop()
  })

  it('keeps the draft and marks the view stale when a pending update is dismissed', async () => {
    const scope = effectScope()
    const initialProject = createProject(1)
    getProjectMock.mockResolvedValue(initialProject)

    const editor = scope.run(() => useCanvasEditor())
    if (!editor) {
      throw new Error('expected useCanvasEditor to initialize')
    }

    await editor.loadProject('project-1')
    editor.markDirty()
    await editor.syncFromRemoteUpdate(
      createCanvasUpdate({ version: 5, event_id: 'canvas-update-4' }),
    )

    editor.dismissPendingRemoteUpdate()

    expect(editor.editorState.value.isDirty).toBe(true)
    expect(editor.syncState.value.pendingRemoteVersion).toBe(5)
    expect(editor.syncState.value.hasRemoteConflict).toBe(false)
    expect(editor.syncState.value.isStale).toBe(true)

    scope.stop()
  })

  it('hydrates the editor from a remote project when no local project is loaded yet', async () => {
    const scope = effectScope()
    const remoteProject = createProject(3)

    const editor = scope.run(() => useCanvasEditor())
    if (!editor) {
      throw new Error('expected useCanvasEditor to initialize')
    }

    const result = await editor.syncFromRemoteProject(remoteProject, {
      operation: 'session_link',
      source: 'system',
    })

    expect(result).toBe('applied')
    expect(editor.project.value?.id).toBe('project-1')
    expect(editor.project.value?.version).toBe(3)
    expect(editor.editorState.value.isDirty).toBe(false)
    expect(editor.syncState.value.serverVersion).toBe(3)
    expect(editor.syncState.value.sessionId).toBe('session-1')

    scope.stop()
  })
})
