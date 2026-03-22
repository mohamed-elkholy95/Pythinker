<template>
  <div v-if="project" class="project-page-root">
    <!-- Top header bar -->
    <div class="project-top-bar">
      <div class="flex items-center">
        <button class="model-name-btn" @click="openSettingsDialog('model')">
          <span>{{ activeModelName || 'Pythinker' }}</span>
          <ChevronRight :size="16" class="rotate-90 text-[var(--text-tertiary)]" />
        </button>
      </div>
      <div class="flex items-center gap-1">
        <Popover>
          <PopoverTrigger as-child>
            <button class="menu-dots-btn">
              <Ellipsis :size="18" />
            </button>
          </PopoverTrigger>
          <PopoverContent
            side="bottom"
            align="end"
            :side-offset="4"
            class="menu-popover !w-[200px] !rounded-xl !p-1"
          >
            <button class="menu-item" @click="handleEditProject">
              <Pencil :size="16" />
              <span>Edit project</span>
            </button>
            <button class="menu-item" @click="showInstructionsModal = true">
              <FileEdit :size="16" />
              <span>Edit instructions</span>
            </button>
            <button class="menu-item menu-item-danger" @click="handleDeleteProject">
              <Trash2 :size="16" />
              <span>Delete project</span>
            </button>
          </PopoverContent>
        </Popover>
      </div>
    </div>

    <!-- Grid content -->
    <div class="project-grid">
      <!-- Col 1, Row 1: Header -->
      <ProjectHeader :project="project" class="project-header-col" />

      <!-- Col 1, Row 2: ChatBox -->
      <div class="project-chatbox-col">
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

      <!-- Col 2: Sidebar -->
      <ProjectSidebar
        :project="project"
        :file-details="fileDetailMap"
        :skill-details="skillDetailMap"
        @edit-instructions="showInstructionsModal = true"
        @upload-file="triggerFileUpload"
        @remove-file="removeFile"
        @add-skills="showSkillsModal = true"
        @remove-skill="removeSkill"
      />
      <input
        ref="fileInputRef"
        type="file"
        multiple
        class="hidden"
        @change="handleFileUpload"
      />

      <!-- Col 1, Row 3: Tasks section -->
      <div class="project-tasks-col">
        <div class="tasks-header">
          <span class="tasks-title">Tasks</span>
          <span class="tasks-note">Your tasks stay private unless shared</span>
        </div>
        <!-- Session list -->
        <div v-if="projectSessions.length > 0" class="project-session-list">
          <button
            v-for="s in projectSessions"
            :key="s.session_id"
            class="project-session-item"
            @click="router.push(`/chat/${s.session_id}`)"
          >
            <MessageSquareDashed :size="16" class="text-[var(--text-tertiary)] shrink-0" />
            <span class="project-session-title">{{ s.title || 'Untitled task' }}</span>
            <span class="project-session-status" :class="`status-${s.status}`">{{ s.status }}</span>
          </button>
        </div>
        <div v-else class="tasks-empty">
          <MessageSquareDashed :size="32" class="text-[var(--text-tertiary)]" />
          <span>Create a new task to get started</span>
        </div>
      </div>
    </div>

    <!-- Modals -->
    <ProjectInstructionsModal
      v-model:open="showInstructionsModal"
      :instructions="project.instructions"
      @save="handleSaveInstructions"
    />
    <ProjectSkillsModal
      v-model:open="showSkillsModal"
      :current-skill-ids="project.skill_ids"
      @save="handleSkillsSelected"
    />
  </div>
  <div v-else-if="loading" class="project-loading">
    Loading...
  </div>
  <div v-else class="project-not-found">
    Project not found
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProject } from '@/composables/useProject'
import { useSkills } from '@/composables/useSkills'
import { useSettingsDialog } from '@/composables/useSettingsDialog'
import { getServerConfig } from '@/api/settings'
import { uploadFile, getFileInfo } from '@/api/file'
import { listProjectSessions, type ProjectSession } from '@/api/projects'
import type { FileInfo } from '@/api/file'
import type { ThinkingMode, ResearchMode } from '@/api/agent'
import ChatBox from '@/components/ChatBox.vue'
import ProjectHeader from '@/components/project/ProjectHeader.vue'
import ProjectSidebar from '@/components/project/ProjectSidebar.vue'
import ProjectInstructionsModal from '@/components/project/ProjectInstructionsModal.vue'
import ProjectSkillsModal from '@/components/project/ProjectSkillsModal.vue'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  ChevronRight,
  Ellipsis,
  Pencil,
  FileEdit,
  Trash2,
  MessageSquareDashed,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const { openSettingsDialog } = useSettingsDialog()
const { availableSkills, loadAvailableSkills } = useSkills()

const { project, loading, updateProject, deleteProject } = useProject(
  computed(() => route.params.projectId as string),
)

const message = ref('')
const attachments = ref<FileInfo[]>([])
const isSubmitting = ref(false)
const showInstructionsModal = ref(false)
const showSkillsModal = ref(false)
const activeModelName = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const fileDetailMap = ref<Record<string, { filename: string; content_type?: string | null; size?: number | null }>>({})
const skillDetailMap = ref<Record<string, { name: string; description?: string }>>({})
const projectSessions = ref<ProjectSession[]>([])

async function loadProjectSessions() {
  const pid = route.params.projectId as string
  if (!pid) return
  try {
    projectSessions.value = await listProjectSessions(pid)
  } catch {
    projectSessions.value = []
  }
}

onMounted(async () => {
  try {
    const config = await getServerConfig()
    activeModelName.value = config.model_name || 'Pythinker'
  } catch {
    activeModelName.value = 'Pythinker'
  }

  // Load available skills and build detail map
  await loadAvailableSkills()
  for (const skill of availableSkills.value) {
    skillDetailMap.value[skill.id] = {
      name: skill.name,
      description: skill.description,
    }
  }

  // Resolve file details for existing project files
  if (project.value?.file_ids.length) {
    for (const fid of project.value.file_ids) {
      try {
        const info = await getFileInfo(fid)
        if (info) {
          fileDetailMap.value[fid] = {
            filename: info.filename,
            content_type: info.content_type ?? null,
            size: info.size ?? null,
          }
        }
      } catch {
        // File info unavailable, will show truncated ID
      }
    }
  }

  // Load project sessions
  await loadProjectSessions()
})

function triggerFileUpload() {
  fileInputRef.value?.click()
}

async function handleFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || !project.value) return

  const newFileIds = [...project.value.file_ids]
  for (const file of Array.from(input.files)) {
    try {
      const uploaded = await uploadFile(file)
      newFileIds.push(uploaded.file_id)
      fileDetailMap.value[uploaded.file_id] = {
        filename: uploaded.filename,
        content_type: uploaded.content_type ?? null,
        size: uploaded.size ?? null,
      }
    } catch (err) {
      console.error('File upload failed:', err)
    }
  }
  await updateProject({ file_ids: newFileIds })

  // Reset input so same file can be re-selected
  input.value = ''
}

async function removeFile(index: number) {
  if (!project.value) return
  const newFileIds = [...project.value.file_ids]
  newFileIds.splice(index, 1)
  await updateProject({ file_ids: newFileIds })
}

async function removeSkill(index: number) {
  if (!project.value) return
  const newSkillIds = [...project.value.skill_ids]
  newSkillIds.splice(index, 1)
  await updateProject({ skill_ids: newSkillIds })
}

async function handleSkillsSelected(skillIds: string[]) {
  await updateProject({ skill_ids: skillIds })
  showSkillsModal.value = false
}

function handleEditProject() {
  // TODO: implement project name editing
}

async function handleDeleteProject() {
  await deleteProject()
}

async function handleSubmit(options: { thinkingMode?: ThinkingMode } = {}) {
  const trimmedMessage = message.value.trim()
  if (!trimmedMessage || isSubmitting.value) return

  isSubmitting.value = true
  try {
    // Build the pending session state
    const pendingState = {
      pendingSessionCreate: true,
      mode: 'agent',
      research_mode: 'deep_research' as ResearchMode,
      message: message.value,
      thinking_mode: options.thinkingMode || 'auto',
      project_id: route.params.projectId as string,
      skills: project.value?.skill_ids || [],
      files: attachments.value.map((file: FileInfo) => ({
        file_id: file.file_id,
        filename: file.filename,
        content_type: file.content_type,
        size: file.size,
        upload_date: file.upload_date,
      })),
    }

    // Store in sessionStorage as fallback — history.state can be lost
    // during cross-route transitions within the same Vue Router layout
    try {
      sessionStorage.setItem('pythinker:pendingSession', JSON.stringify(pendingState))
    } catch { /* storage unavailable */ }

    await router.push({
      path: '/chat/new',
      state: pendingState,
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
.project-page-root {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* ── Top header bar ── */
.project-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-main);
  min-height: 48px;
}

.model-name-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
}

.model-name-btn:hover {
  background: var(--fill-tsp-gray-main);
}

.menu-dots-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s;
}

.menu-dots-btn:hover {
  background: var(--fill-tsp-gray-main);
}

/* ── Popover menu items ── */
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.menu-item:hover {
  background: var(--fill-tsp-gray-main);
}

.menu-item-danger {
  color: var(--text-error, #ef4444);
}

.menu-item-danger:hover {
  background: var(--fill-tsp-error-light, rgba(239, 68, 68, 0.08));
}

/* ── Grid layout ── */
.project-grid {
  padding-top: 32px;
  padding-left: 24px;
  padding-right: 24px;
  margin: 0 auto;
  width: 100%;
  max-width: 768px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.project-header-col {
  grid-column: 1;
}

.project-chatbox-col {
  grid-column: 1;
  margin-top: 20px;
}

.project-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 24px;
}

.project-tasks-col {
  grid-column: 1;
  margin-top: 32px;
  padding-bottom: 48px;
}

@media (min-width: 768px) {
  .project-grid {
    max-width: 1168px;
    padding-left: 18px;
    padding-right: 18px;
    grid-template-columns: minmax(390px, 768px) minmax(240px, 320px);
    column-gap: 44px;
    grid-template-rows: auto auto 1fr;
  }

  .project-sidebar {
    grid-column: 2;
    grid-row: 1 / 4;
    position: sticky;
    top: 160px;
    align-self: start;
    padding-bottom: 32px;
    margin-top: 0;
  }
}

/* ── Tasks section ── */
.tasks-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}

.tasks-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.tasks-note {
  font-size: 13px;
  color: var(--text-tertiary);
}

.tasks-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* ── Project session list ── */
.project-session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background 0.12s;
  text-align: left;
  width: 100%;
}

.project-session-item:hover {
  background: var(--fill-tsp-gray-main);
}

.project-session-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-session-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
  text-transform: capitalize;
}

.status-completed {
  background: rgba(34, 197, 94, 0.1);
  color: #16a34a;
}

.status-running, .status-initializing {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.status-pending {
  background: rgba(234, 179, 8, 0.1);
  color: #ca8a04;
}

.status-failed, .status-cancelled {
  background: rgba(239, 68, 68, 0.08);
  color: #dc2626;
}

.status-waiting {
  background: rgba(168, 85, 247, 0.1);
  color: #7c3aed;
}

/* ── Loading / Not found states ── */
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
</style>
