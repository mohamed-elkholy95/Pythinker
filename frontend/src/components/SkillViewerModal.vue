<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="isOpen" class="modal-backdrop" @click.self="closeModal">
        <div class="skill-viewer-container">
          <!-- Header -->
          <div class="viewer-header">
            <div class="header-left">
              <div class="skill-icon">
                <component :is="iconComponent" :size="20" />
              </div>
              <div class="skill-meta">
                <h2 class="skill-name">{{ skill?.name }}</h2>
                <span class="skill-version">v{{ skill?.version }}</span>
              </div>
            </div>

            <div class="header-actions">
              <!-- Download button -->
              <button
                class="action-btn"
                @click="handleDownload"
                :disabled="isDownloading"
                title="Download .skill file"
              >
                <Loader2 v-if="isDownloading" :size="16" class="animate-spin" />
                <Download v-else :size="16" />
                <span>Download</span>
              </button>

              <!-- Menu dropdown -->
              <div class="menu-dropdown" ref="menuRef">
                <button class="menu-btn" @click="toggleMenu">
                  <MoreVertical :size="18" />
                </button>
                <Transition name="dropdown">
                  <div v-if="showMenu" class="dropdown-content">
                    <button @click="handleCopyToClipboard">
                      <Copy :size="14" />
                      <span>Copy contents</span>
                    </button>
                    <button @click="handleAddToSkills">
                      <Plus :size="14" />
                      <span>Add to my skills</span>
                    </button>
                  </div>
                </Transition>
              </div>

              <!-- Close button -->
              <button class="close-btn" @click="closeModal">
                <X :size="20" />
              </button>
            </div>
          </div>

          <!-- Body -->
          <div class="viewer-body">
            <!-- Left panel: File tree -->
            <div class="file-tree-panel">
              <div class="panel-header">
                <span>Files</span>
                <span class="file-count">{{ skill?.files.length || 0 }}</span>
              </div>
              <SkillFileTree
                v-if="skill"
                :tree="skill.file_tree"
                :selected-path="selectedFilePath"
                @select="selectFile"
              />
            </div>

            <!-- Right panel: File preview -->
            <div class="file-preview-panel">
              <div class="panel-header">
                <span>{{ selectedFilePath || 'Preview' }}</span>
              </div>
              <SkillFilePreview :file="selectedFile" />
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  X,
  Download,
  MoreVertical,
  Copy,
  Plus,
  Loader2,
  Puzzle,
  Sparkles,
  Wand2,
  Code,
  FileText,
  Search,
  Globe,
  Zap,
  Bot,
  Terminal,
  Database,
  Image as ImageIcon,
} from 'lucide-vue-next'
import SkillFileTree from './skill/SkillFileTree.vue'
import SkillFilePreview from './skill/SkillFilePreview.vue'
import type { SkillDeliveryContent, SkillPackageFile } from '@/types/message'

interface Props {
  modelValue: boolean
  skill?: SkillDeliveryContent
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  download: [packageId: string]
  install: [packageId: string]
}>()

const isOpen = ref(props.modelValue)
const showMenu = ref(false)
const menuRef = ref<HTMLElement | null>(null)
const selectedFilePath = ref<string>('')
const isDownloading = ref(false)

// Icon mapping
const iconMap: Record<string, any> = {
  puzzle: Puzzle,
  sparkles: Sparkles,
  'wand-2': Wand2,
  code: Code,
  'file-text': FileText,
  search: Search,
  globe: Globe,
  zap: Zap,
  bot: Bot,
  terminal: Terminal,
  database: Database,
  image: ImageIcon,
}

const iconComponent = computed(() => {
  if (!props.skill) return Puzzle
  return iconMap[props.skill.icon] || Puzzle
})

const selectedFile = computed<SkillPackageFile | undefined>(() => {
  if (!props.skill || !selectedFilePath.value) return undefined
  return props.skill.files.find(f => f.path === selectedFilePath.value)
})

watch(() => props.modelValue, (value) => {
  isOpen.value = value
  if (value) {
    document.body.style.overflow = 'hidden'
    // Auto-select SKILL.md if available
    if (props.skill) {
      const skillMd = props.skill.files.find(f => f.path === 'SKILL.md')
      if (skillMd) {
        selectedFilePath.value = 'SKILL.md'
      } else if (props.skill.files.length > 0) {
        selectedFilePath.value = props.skill.files[0].path
      }
    }
  } else {
    document.body.style.overflow = ''
    showMenu.value = false
  }
})

const closeModal = () => {
  isOpen.value = false
  emit('update:modelValue', false)
  document.body.style.overflow = ''
}

const toggleMenu = () => {
  showMenu.value = !showMenu.value
}

const selectFile = (path: string) => {
  selectedFilePath.value = path
}

const handleDownload = () => {
  if (!props.skill) return
  isDownloading.value = true
  emit('download', props.skill.package_id)
  setTimeout(() => {
    isDownloading.value = false
  }, 1500)
}

const handleCopyToClipboard = async () => {
  if (!selectedFile.value) return
  try {
    await navigator.clipboard.writeText(selectedFile.value.content)
    showMenu.value = false
  } catch (err) {
    console.error('Failed to copy:', err)
  }
}

const handleAddToSkills = () => {
  if (!props.skill) return
  emit('install', props.skill.package_id)
  showMenu.value = false
}

// Handle escape key and click outside
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isOpen.value) {
    closeModal()
  }
}

const handleClickOutside = (e: MouseEvent) => {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    showMenu.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('click', handleClickOutside)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 40px;
}

.skill-viewer-container {
  width: 100%;
  max-width: 1200px;
  height: calc(100vh - 80px);
  max-height: 800px;
  background: var(--bolt-elements-bg-depth-1);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
}

/* Header */
.viewer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.skill-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.skill-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  margin: 0;
}

.skill-version {
  font-size: 12px;
  color: var(--bolt-elements-textSecondary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bolt-elements-bg-depth-3);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 8px;
  color: var(--bolt-elements-textPrimary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.action-btn:hover:not(:disabled) {
  background: var(--bolt-elements-bg-depth-4);
  border-color: var(--bolt-elements-borderColorActive);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.menu-dropdown {
  position: relative;
}

.menu-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bolt-elements-bg-depth-3);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 8px;
  color: var(--bolt-elements-textSecondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.menu-btn:hover {
  background: var(--bolt-elements-bg-depth-4);
  color: var(--bolt-elements-textPrimary);
}

.dropdown-content {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  min-width: 180px;
  background: var(--bolt-elements-bg-depth-2);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
  z-index: 10;
}

.dropdown-content button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--bolt-elements-textPrimary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.dropdown-content button:hover {
  background: var(--bolt-elements-bg-depth-3);
}

.close-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--bolt-elements-textSecondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.close-btn:hover {
  background: var(--bolt-elements-bg-depth-3);
  color: var(--bolt-elements-textPrimary);
}

/* Body */
.viewer-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.file-tree-panel {
  width: 260px;
  border-right: 1px solid var(--bolt-elements-borderColor);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--bolt-elements-borderColor);
  background: var(--bolt-elements-bg-depth-2);
  font-size: 12px;
  font-weight: 600;
  color: var(--bolt-elements-textSecondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.file-count {
  background: var(--bolt-elements-bg-depth-4);
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

/* Transitions */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-active .skill-viewer-container,
.modal-fade-leave-active .skill-viewer-container {
  transition: transform 0.3s ease;
}

.modal-fade-enter-from .skill-viewer-container,
.modal-fade-leave-to .skill-viewer-container {
  transform: scale(0.95);
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.15s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Spin animation */
.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
