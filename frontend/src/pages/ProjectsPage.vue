<template>
  <div class="projects-page">
    <div class="projects-header">
      <h1 class="projects-title">Projects</h1>
      <button class="btn-new-project" type="button" @click="showCreateModal = true">
        <Plus :size="16" />
        <span>New project</span>
      </button>
    </div>

    <div v-if="loading" class="projects-loading">
      Loading projects...
    </div>

    <div v-else-if="projects.length > 0" class="projects-grid">
      <div
        v-for="item in projects"
        :key="item.id"
        class="project-card"
        @click="navigateToProject(item.id)"
      >
        <div class="project-card-icon">
          <Folder :size="20" />
        </div>
        <div class="project-card-body">
          <h3 class="project-card-name">{{ item.name }}</h3>
          <p class="project-card-meta">
            {{ item.session_count }} {{ item.session_count === 1 ? 'task' : 'tasks' }}
            &middot; Updated {{ formatDate(item.updated_at) }}
          </p>
        </div>
      </div>
    </div>

    <div v-else class="projects-empty">
      <div class="projects-empty-icon">
        <Folder :size="32" />
      </div>
      <p class="projects-empty-title">No projects yet</p>
      <p class="projects-empty-text">Create a project to organize your tasks with shared instructions and files.</p>
      <button class="btn-new-project" type="button" @click="showCreateModal = true">
        <Plus :size="16" />
        <span>New project</span>
      </button>
    </div>

    <CreateProjectModal
      v-model:open="showCreateModal"
      @created="handleProjectCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Folder, Plus } from 'lucide-vue-next'
import { useProjectList } from '@/composables/useProjectList'
import CreateProjectModal from '@/components/project/CreateProjectModal.vue'
import type { ProjectListItem } from '@/types/project'

const router = useRouter()
const { projects, loading, addProject } = useProjectList()
const showCreateModal = ref(false)

function navigateToProject(id: string) {
  router.push({ name: 'project-detail', params: { projectId: id } })
}

function handleProjectCreated(project: ProjectListItem) {
  addProject(project)
  navigateToProject(project.id)
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffDays < 1) return 'today'
  if (diffDays === 1) return 'yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  return date.toLocaleDateString()
}
</script>

<style scoped>
.projects-page {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}

.projects-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.projects-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}

.btn-new-project {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  border-radius: 10px;
  border: none;
  background: var(--text-primary, #1a1a1a);
  color: var(--background-main, #ffffff);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.btn-new-project:hover {
  opacity: 0.85;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.project-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: all 0.15s ease;
}

.project-card:hover {
  border-color: var(--border-main);
  background: var(--fill-tsp-gray-main, #fafafa);
}

.project-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.project-card-body {
  flex: 1;
  min-width: 0;
}

.project-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-card-meta {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

.projects-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  font-size: 14px;
  color: var(--text-tertiary);
}

.projects-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  gap: 12px;
}

.projects-empty-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.projects-empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.projects-empty-text {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
  text-align: center;
  max-width: 360px;
  line-height: 1.5;
}
</style>
