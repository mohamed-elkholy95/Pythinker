<template>
  <div class="task-list">
    <template v-if="sessions.length > 0">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="task-item"
      >
        <div class="task-item-header">
          <span class="task-item-title">{{ session.title }}</span>
          <span class="task-item-status" :class="`status-${session.status}`">
            {{ session.status }}
          </span>
        </div>
        <span class="task-item-date">{{ formatDate(session.updated_at) }}</span>
      </div>
    </template>

    <div v-else class="task-list-empty">
      <p class="task-list-empty-text">Create a new task to get started</p>
    </div>
  </div>
</template>

<script setup lang="ts">
interface TaskSession {
  id: string
  title: string
  status: string
  updated_at: string
}

defineProps<{
  sessions: TaskSession[]
}>()

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffDays < 1) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}
</script>

<style scoped>
.task-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.task-item:hover {
  background: var(--fill-tsp-gray-main, #f5f5f5);
}

.task-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.task-item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-item-status {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 6px;
  flex-shrink: 0;
}

.status-active {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.1);
}

.status-completed {
  color: var(--text-tertiary);
  background: var(--fill-tsp-gray-main, #f0f0f0);
}

.task-item-date {
  font-size: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  margin-left: 12px;
}

.task-list-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  border-radius: 12px;
  border: 2px dashed var(--border-light);
}

.task-list-empty-text {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
}
</style>
