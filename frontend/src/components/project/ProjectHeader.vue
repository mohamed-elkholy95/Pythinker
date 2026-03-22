<template>
  <div class="project-header">
    <div class="project-header-top">
      <div class="project-icon">
        <Folder :size="20" />
      </div>
      <h1 class="project-name">{{ project.name }}</h1>
    </div>
    <p class="project-meta">
      Created by {{ createdBy }} &middot; Updated {{ relativeDate }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Folder } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import type { Project } from '@/types/project'

const props = defineProps<{
  project: Project
}>()

const { currentUser } = useAuth()

const createdBy = computed(() => currentUser.value?.fullname ?? 'you')

const relativeDate = computed(() => {
  const updated = new Date(props.project.updated_at)
  const now = new Date()
  const diffMs = now.getTime() - updated.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHrs = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHrs < 24) return `${diffHrs}h ago`
  if (diffDays < 30) return `${diffDays}d ago`
  return updated.toLocaleDateString()
})
</script>

<style scoped>
.project-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.project-header-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--fill-tsp-gray-main, #f0f0f0);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.project-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin: 0;
}

.project-meta {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
  padding-left: 42px;
}
</style>
