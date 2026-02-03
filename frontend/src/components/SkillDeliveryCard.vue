<template>
  <div class="skill-delivery-card" @click="openViewer">
    <!-- Header -->
    <div class="skill-header">
      <div class="skill-icon">
        <component :is="iconComponent" :size="18" />
      </div>

      <div class="skill-info">
        <span class="skill-name">{{ content.name }}</span>
        <span class="skill-label">Skill</span>
      </div>

      <!-- Action Buttons -->
      <div class="skill-actions" @click.stop>
        <button
          class="action-btn download-btn"
          @click="handleDownload"
          :disabled="isDownloading"
          title="Download .skill file"
        >
          <Loader2 v-if="isDownloading" :size="16" class="animate-spin" />
          <Download v-else :size="16" />
        </button>

        <button
          class="action-btn add-btn"
          @click="handleAddToSkills"
          :disabled="isInstalling || isInstalled"
        >
          <Loader2 v-if="isInstalling" :size="14" class="animate-spin" />
          <Check v-else-if="isInstalled" :size="14" />
          <Plus v-else :size="14" />
          <span>{{ addButtonText }}</span>
        </button>
      </div>
    </div>

    <!-- Description Preview -->
    <p class="skill-description">{{ content.description }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  Download,
  Loader2,
  Plus,
  Check,
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
import type { SkillDeliveryContent } from '@/types/message'

interface Props {
  content: SkillDeliveryContent
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'open-viewer', packageId: string): void
  (e: 'download', packageId: string): void
  (e: 'install', packageId: string): void
}>()

const isDownloading = ref(false)
const isInstalling = ref(false)
const isInstalled = ref(false)

// Map icon names to components
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
  return iconMap[props.content.icon] || Puzzle
})

const addButtonText = computed(() => {
  if (isInstalled.value) return 'Added'
  if (isInstalling.value) return 'Adding...'
  return 'Add to my skills'
})

const openViewer = () => {
  emit('open-viewer', props.content.package_id)
}

const handleDownload = async () => {
  isDownloading.value = true
  try {
    emit('download', props.content.package_id)
  } finally {
    // Reset after short delay for visual feedback
    setTimeout(() => {
      isDownloading.value = false
    }, 1000)
  }
}

const handleAddToSkills = async () => {
  if (isInstalled.value) return

  isInstalling.value = true
  try {
    emit('install', props.content.package_id)
    // Assume success - the parent will handle errors
    isInstalled.value = true
  } finally {
    isInstalling.value = false
  }
}
</script>

<style scoped>
.skill-delivery-card {
  background: var(--bolt-elements-bg-depth-1);
  border: 1px solid var(--bolt-elements-borderColor);
  border-radius: 14px;
  overflow: hidden;
  transition: all 0.2s ease;
  cursor: pointer;
  padding: 16px;
}

.skill-delivery-card:hover {
  border-color: var(--bolt-elements-borderColorActive);
  background: var(--bolt-elements-bg-depth-2);
}

/* Header */
.skill-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.skill-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.skill-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--bolt-elements-textPrimary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-label {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  color: #9333ea;
  background: rgba(147, 51, 234, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
  width: fit-content;
}

/* Actions */
.skill-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
}

.download-btn {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--bolt-elements-bg-depth-3);
  color: var(--bolt-elements-textSecondary);
}

.download-btn:hover:not(:disabled) {
  background: var(--bolt-elements-bg-depth-4);
  color: var(--bolt-elements-textPrimary);
}

.add-btn {
  height: 36px;
  padding: 0 16px;
  border-radius: 10px;
  background: var(--bolt-elements-textPrimary);
  color: var(--bolt-elements-bg-depth-1);
  font-size: 13px;
  font-weight: 500;
}

.add-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.add-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Description */
.skill-description {
  margin-top: 12px;
  font-size: 13px;
  color: var(--bolt-elements-textSecondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
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
