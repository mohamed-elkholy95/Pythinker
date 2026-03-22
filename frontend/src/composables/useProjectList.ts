import { ref, onMounted } from 'vue'
import * as projectsApi from '@/api/projects'
import type { ProjectListItem } from '@/types/project'

export function useProjectList() {
  const projects = ref<ProjectListItem[]>([])
  const loading = ref(false)

  async function fetchProjects(): Promise<void> {
    loading.value = true
    try {
      projects.value = await projectsApi.listProjects({ status: 'active', limit: 50 })
    } catch {
      // Silently fail — sidebar should not block on project load failure
      projects.value = []
    } finally {
      loading.value = false
    }
  }

  async function addProject(project: ProjectListItem): Promise<void> {
    projects.value = [project, ...projects.value]
  }

  onMounted(fetchProjects)

  return { projects, loading, fetchProjects, addProject }
}
