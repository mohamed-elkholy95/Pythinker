import { ref, toValue, watch, type MaybeRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import * as projectsApi from '@/api/projects'
import type { Project, UpdateProjectRequest } from '@/types/project'

export function useProject(projectId: MaybeRef<string>) {
  const router = useRouter()
  const project = ref<Project | null>(null) as Ref<Project | null>
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProject(): Promise<void> {
    const id = toValue(projectId)
    if (!id) return
    loading.value = true
    error.value = null
    try {
      project.value = await projectsApi.getProject(id)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load project'
    } finally {
      loading.value = false
    }
  }

  async function updateProject(updates: UpdateProjectRequest): Promise<void> {
    const id = toValue(projectId)
    if (!id) return
    error.value = null
    try {
      project.value = await projectsApi.updateProject(id, updates)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to update project'
    }
  }

  async function deleteProject(): Promise<void> {
    const id = toValue(projectId)
    if (!id) return
    error.value = null
    try {
      await projectsApi.deleteProject(id)
      router.push('/chat')
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to delete project'
    }
  }

  // Auto-fetch when projectId changes
  watch(() => toValue(projectId), (newId) => {
    if (newId) fetchProject()
  }, { immediate: true })

  return {
    project,
    loading,
    error,
    fetchProject,
    updateProject,
    deleteProject,
  }
}
