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

      <!-- Col 2: Sidebar (sticky, spans rows 1-3) -->
      <div class="project-sidebar">
        <!-- Card 1: Instructions + Connectors -->
        <div class="sidebar-card">
          <div class="sidebar-section clickable" @click="showInstructionsModal = true">
            <div class="sidebar-section-header">
              <span class="sidebar-section-title">Instructions</span>
              <ChevronRight :size="14" class="text-[var(--text-tertiary)]" />
            </div>
            <p class="sidebar-section-desc">
              {{
                project.instructions
                  ? truncateText(project.instructions, 80)
                  : "Add instructions to tailor Pythinker's responses"
              }}
            </p>
            <button
              class="sidebar-add-btn"
              @click.stop="showInstructionsModal = true"
            >
              <Plus :size="14" />
              <span>Add</span>
            </button>
          </div>
          <div class="sidebar-separator" />
          <div
            class="sidebar-section-compact clickable"
            @click="openConnectorDialog()"
          >
            <div class="connectors-row">
              <Cable :size="16" class="text-[var(--text-secondary)]" />
              <span class="connectors-label">Connectors</span>
              <button class="connectors-add-btn" @click.stop="openConnectorDialog()">
                <Plus :size="14" />
                <span>Add</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Card 2: Files + Skills -->
        <div class="sidebar-card">
          <div class="sidebar-section" @click.self="triggerFileUpload">
            <div class="sidebar-section-header">
              <span class="sidebar-section-title">Files</span>
              <ChevronRight :size="14" class="text-[var(--text-tertiary)]" />
            </div>
            <!-- Show uploaded files -->
            <div v-if="project.file_ids.length > 0" class="sidebar-file-list">
              <div
                v-for="(fid, idx) in project.file_ids"
                :key="fid"
                class="sidebar-file-item"
              >
                <FileText :size="14" class="text-[var(--text-tertiary)] shrink-0" />
                <span class="sidebar-file-name">{{ fileNameMap[fid] || fid.slice(0, 12) + '...' }}</span>
                <button class="sidebar-remove-btn" title="Remove" @click.stop="removeFile(idx)">
                  <X :size="12" />
                </button>
              </div>
            </div>
            <p v-else class="sidebar-section-desc">
              Start by attaching files to your project.
            </p>
            <button class="sidebar-outline-btn" @click.stop="triggerFileUpload">
              <Upload :size="14" />
              <span>Upload files</span>
            </button>
            <input
              ref="fileInputRef"
              type="file"
              multiple
              class="hidden"
              @change="handleFileUpload"
            />
          </div>
          <div class="sidebar-separator" />
          <div class="sidebar-section">
            <div class="sidebar-section-header">
              <span class="sidebar-section-title">Skills</span>
              <ChevronRight :size="14" class="text-[var(--text-tertiary)]" />
            </div>
            <!-- Show selected skills -->
            <div v-if="project.skill_ids.length > 0" class="sidebar-skill-list">
              <div
                v-for="(sid, idx) in project.skill_ids"
                :key="sid"
                class="sidebar-skill-item"
              >
                <Sparkles :size="14" class="text-[var(--text-tertiary)] shrink-0" />
                <span class="sidebar-skill-name">{{ skillNameMap[sid] || sid }}</span>
                <button class="sidebar-remove-btn" title="Remove" @click.stop="removeSkill(idx)">
                  <X :size="12" />
                </button>
              </div>
            </div>
            <p v-else class="sidebar-section-desc">
              Add skills to enhance Pythinker's know-how.
            </p>
            <button class="sidebar-outline-btn" @click.stop="showSkillsModal = true">
              <Plus :size="14" />
              <span>Add</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Col 1, Row 3: Tasks section -->
      <div class="project-tasks-col">
        <div class="tasks-header">
          <span class="tasks-title">Tasks</span>
          <span class="tasks-note">Your tasks stay private unless shared</span>
        </div>
        <div class="tasks-empty">
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
import { useConnectorDialog } from '@/composables/useConnectorDialog'
import { getServerConfig } from '@/api/settings'
import { uploadFile, getFileInfo } from '@/api/file'
import type { FileInfo } from '@/api/file'
import type { ThinkingMode, ResearchMode } from '@/api/agent'
import ChatBox from '@/components/ChatBox.vue'
import ProjectHeader from '@/components/project/ProjectHeader.vue'
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
  FileText,
  Trash2,
  Cable,
  Plus,
  Upload,
  Sparkles,
  X,
  MessageSquareDashed,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const { openSettingsDialog } = useSettingsDialog()
const { openConnectorDialog } = useConnectorDialog()
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
const fileNameMap = ref<Record<string, string>>({})
const skillNameMap = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    const config = await getServerConfig()
    activeModelName.value = config.model_name || 'Pythinker'
  } catch {
    activeModelName.value = 'Pythinker'
  }

  // Load available skills and build name map
  await loadAvailableSkills()
  for (const skill of availableSkills.value) {
    skillNameMap.value[skill.id] = skill.name
  }

  // Resolve file names for existing project files
  if (project.value?.file_ids.length) {
    for (const fid of project.value.file_ids) {
      try {
        const info = await getFileInfo(fid)
        if (info) fileNameMap.value[fid] = info.filename
      } catch {
        // File info unavailable, will show truncated ID
      }
    }
  }
})

function truncateText(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen).trimEnd() + '...'
}

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
      fileNameMap.value[uploaded.file_id] = uploaded.filename
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
    await router.push({
      path: '/chat/new',
      state: {
        pendingSessionCreate: true,
        mode: 'agent',
        research_mode: 'deep_research' as ResearchMode,
        message: message.value,
        thinking_mode: options.thinkingMode || 'auto',
        project_id: route.params.projectId,
        skills: project.value?.skill_ids || [],
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

/* ── Sidebar cards ── */
.sidebar-card {
  border-radius: 12px;
  border: 1px solid var(--border-main);
  overflow: hidden;
}

.sidebar-section {
  padding: 16px;
  padding-right: 12px;
}

.sidebar-section.clickable {
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-section.clickable:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-separator {
  border-top: 1px solid var(--border-main);
}

.sidebar-section-compact {
  padding: 16px;
  padding-right: 12px;
}

.sidebar-section-compact.clickable {
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-section-compact.clickable:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-section-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.sidebar-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-section-desc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-secondary);
  margin: 0 0 10px 0;
}

.sidebar-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.sidebar-add-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-hover, var(--border-main));
}

.sidebar-upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.sidebar-upload-btn:hover {
  background: var(--fill-tsp-gray-main);
  border-color: var(--border-hover, var(--border-main));
}

/* ── File & Skill lists in sidebar ── */
.sidebar-file-list,
.sidebar-skill-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.sidebar-file-item,
.sidebar-skill-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.sidebar-file-item:hover,
.sidebar-skill-item:hover {
  background: var(--fill-tsp-gray-main);
}

.sidebar-file-name,
.sidebar-skill-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s, background 0.12s;
  flex-shrink: 0;
}

.sidebar-file-item:hover .sidebar-remove-btn,
.sidebar-skill-item:hover .sidebar-remove-btn {
  opacity: 1;
}

.sidebar-remove-btn:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-error, #ef4444);
}

.sidebar-outline-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
}

.sidebar-outline-btn:hover {
  background: var(--fill-tsp-gray-main);
}

/* ── Connectors row ── */
.connectors-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--fill-tsp-white-light, rgba(255, 255, 255, 0.04));
}

.connectors-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  flex: 1;
}

.connectors-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  border-radius: 6px;
  border: none;
  background: transparent;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color 0.15s;
}

.connectors-add-btn:hover {
  color: var(--text-primary);
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
