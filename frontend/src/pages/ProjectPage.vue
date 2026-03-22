<template>
  <div class="project-page" v-if="project">
    <div class="project-main">
      <ProjectHeader :project="project" />

      <!-- Chat Input — reuses the same ChatBox as HomePage -->
      <div class="chat-input-wrapper">
        <ChatBox
          :rows="1"
          v-model="message"
          @submit="handleSubmit"
          :isRunning="isSubmitting"
          :attachments="attachments"
          :showConnectorBanner="true"
          expand-direction="down"
        />
      </div>

      <div class="project-tasks-section">
        <div class="project-tasks-header">
          <h3 class="project-tasks-title">Tasks</h3>
          <span class="project-tasks-note">Your tasks stay private unless shared</span>
        </div>
        <ProjectTaskList :sessions="[]" />
      </div>
    </div>

    <div class="project-sidebar">
      <ProjectInstructionsPanel
        :instructions="project.instructions"
        @edit="showInstructionsModal = true"
      />
      <ProjectConnectorsPanel
        :connector-ids="project.connector_ids"
        @add="showConnectorsModal = true"
      />
      <ProjectFilesPanel />
      <ProjectSkillsPanel />
    </div>

    <ProjectInstructionsModal
      v-model:open="showInstructionsModal"
      :instructions="project.instructions"
      @save="handleSaveInstructions"
    />
    <ProjectConnectorsModal v-model:open="showConnectorsModal" />
  </div>
  <div v-else-if="loading" class="project-loading">
    Loading...
  </div>
  <div v-else class="project-not-found">
    Project not found
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProject } from '@/composables/useProject'
import ChatBox from '@/components/ChatBox.vue'
import ProjectHeader from '@/components/project/ProjectHeader.vue'
import ProjectTaskList from '@/components/project/ProjectTaskList.vue'
import ProjectInstructionsPanel from '@/components/project/ProjectInstructionsPanel.vue'
import ProjectConnectorsPanel from '@/components/project/ProjectConnectorsPanel.vue'
import ProjectFilesPanel from '@/components/project/ProjectFilesPanel.vue'
import ProjectSkillsPanel from '@/components/project/ProjectSkillsPanel.vue'
import ProjectInstructionsModal from '@/components/project/ProjectInstructionsModal.vue'
import ProjectConnectorsModal from '@/components/project/ProjectConnectorsModal.vue'
import type { FileInfo } from '@/api/file'
import type { ThinkingMode, ResearchMode } from '@/api/agent'

const route = useRoute()
const router = useRouter()
const { project, loading, updateProject } = useProject(
  computed(() => route.params.projectId as string),
)

const message = ref('')
const attachments = ref<FileInfo[]>([])
const isSubmitting = ref(false)
const showInstructionsModal = ref(false)
const showConnectorsModal = ref(false)

async function handleSubmit(options: { thinkingMode?: ThinkingMode } = {}) {
  const trimmedMessage = message.value.trim()
  if (!trimmedMessage || isSubmitting.value) return

  isSubmitting.value = true
  try {
    await router.push({
      path: '/chat/new',
      state: {
        pendingSessionCreate: true,
        mode: 'agent',
        research_mode: 'deep_research' as ResearchMode,
        message: message.value,
        thinking_mode: options.thinkingMode || 'auto',
        project_id: route.params.projectId,
        skills: [],
        files: attachments.value.map((file: FileInfo) => ({
          file_id: file.file_id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
          upload_date: file.upload_date,
        })),
      },
    })
  } finally {
    isSubmitting.value = false
  }
}

async function handleSaveInstructions(instructions: string) {
  await updateProject({ instructions })
  showInstructionsModal.value = false
}
</script>

<style scoped>
.project-page {
  display: flex;
  gap: 24px;
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  min-height: 100%;
}

.project-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.chat-input-wrapper {
  width: 100%;
}

.project-tasks-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-tasks-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.project-tasks-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.project-tasks-note {
  font-size: 13px;
  color: var(--text-tertiary);
}

.project-sidebar {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  font-size: 14px;
  color: var(--text-tertiary);
}

.project-not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  font-size: 14px;
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .project-page {
    flex-direction: column;
    padding: 16px;
  }

  .project-sidebar {
    width: 100%;
  }
}
</style>
